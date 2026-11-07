"""Fail-closed verification for Apple/Google purchases and AdMob SSV callbacks."""
import asyncio
import base64
import json
import logging
import time
from urllib.parse import parse_qsl, quote
from uuid import UUID

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_SECONDS = 8.0
_ADMOB_KEYS_URL = "https://www.gstatic.com/admob/reward/verifier-keys.json"
_ADMOB_KEYS_TTL_SECONDS = 23 * 60 * 60
_ADMOB_TIMESTAMP_TOLERANCE_MS = 24 * 60 * 60 * 1000
_admob_keys: dict[int, ec.EllipticCurvePublicKey] = {}
_admob_keys_expiry = 0.0
_admob_keys_lock = asyncio.Lock()
_google_credentials = None
_google_credentials_lock = asyncio.Lock()


def _reject_unconfigured(what: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Vérification serveur de {what} non configurée : crédit refusé",
    )


def _apple_environment():
    from appstoreserverlibrary.models.Environment import Environment

    if settings.APPLE_ENVIRONMENT.lower() == "production":
        return Environment.PRODUCTION
    if settings.APPLE_ENVIRONMENT.lower() == "sandbox":
        return Environment.SANDBOX
    raise ValueError("APPLE_ENVIRONMENT doit être Production ou Sandbox")


def _apple_api_token() -> str:
    # A short-lived, externally generated token remains supported for deployments
    # that rotate it through a secret manager.
    if settings.APPLE_IAP_BEARER_TOKEN:
        return settings.APPLE_IAP_BEARER_TOKEN
    if not all((settings.APPLE_IAP_PRIVATE_KEY, settings.APPLE_IAP_KEY_ID,
                settings.APPLE_IAP_ISSUER_ID, settings.APPLE_BUNDLE_ID)):
        _reject_unconfigured("l'achat Apple")

    now = int(time.time())
    return jwt.encode(
        {
            "iss": settings.APPLE_IAP_ISSUER_ID,
            "iat": now,
            "exp": now + 5 * 60,
            "aud": "appstoreconnect-v1",
            "bid": settings.APPLE_BUNDLE_ID,
        },
        settings.APPLE_IAP_PRIVATE_KEY.replace("\\n", "\n"),
        algorithm="ES256",
        headers={"kid": settings.APPLE_IAP_KEY_ID, "typ": "JWT"},
    )


def _apple_verifier():
    from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier

    if not settings.APPLE_BUNDLE_ID or not settings.APPLE_ROOT_CERTIFICATES_B64:
        _reject_unconfigured("la validation de signature Apple")
    roots = [
        base64.b64decode(value.strip(), validate=True)
        for value in settings.APPLE_ROOT_CERTIFICATES_B64.split(",")
        if value.strip()
    ]
    if not roots:
        _reject_unconfigured("la validation de signature Apple")
    return SignedDataVerifier(
        roots,
        True,
        _apple_environment(),
        settings.APPLE_BUNDLE_ID,
        int(settings.APPLE_APP_ID) if settings.APPLE_APP_ID else None,
    )


async def _google_access_token() -> str:
    global _google_credentials
    if settings.GOOGLE_PLAY_ACCESS_TOKEN:
        return settings.GOOGLE_PLAY_ACCESS_TOKEN
    if not settings.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON:
        _reject_unconfigured("l'achat Google")
    async with _google_credentials_lock:
        if _google_credentials is None:
            from google.oauth2 import service_account

            info = json.loads(settings.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON)
            _google_credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/androidpublisher"],
            )
        if not _google_credentials.valid or _google_credentials.expired:
            from google.auth.transport.requests import Request

            await asyncio.to_thread(_google_credentials.refresh, Request())
        return _google_credentials.token


async def _verify_apple(transaction_id: str, receipt_data: str, pack_sku: str) -> bool:
    """Fetch Apple's signed transaction then validate certificate chain, JWS and claims."""
    try:
        token = _apple_api_token()
        verifier = _apple_verifier()
        environment = settings.APPLE_ENVIRONMENT.lower()
        base_url = (
            "https://api.storekit-sandbox.itunes.apple.com"
            if environment == "sandbox"
            else settings.APPLE_IAP_VERIFY_URL.rstrip("/")
        )
        url = f"{base_url}/inApps/v1/transactions/{quote(transaction_id, safe='')}"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if response.status_code != 200:
            logger.warning("Rejet Apple IAP %s (HTTP %s)", transaction_id, response.status_code)
            return False
        signed_data = response.json().get("signedTransactionInfo")
        if not isinstance(signed_data, str) or not signed_data:
            return False
        transaction = await asyncio.to_thread(verifier.verify_and_decode_signed_transaction, signed_data)
        return (
            str(transaction.transactionId) == transaction_id
            and transaction.productId == pack_sku
            and transaction.bundleId == settings.APPLE_BUNDLE_ID
            and transaction.revocationDate is None
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Échec de vérification Apple IAP %s: %s", transaction_id, exc)
        return False


def _google_purchase_url(pack_sku: str, purchase_token: str) -> str:
    return (
        "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
        f"{quote(settings.GOOGLE_PLAY_PACKAGE_NAME, safe='')}/purchases/products/"
        f"{quote(pack_sku, safe='')}/tokens/{quote(purchase_token, safe='')}"
    )


async def _verify_google(transaction_id: str, receipt_data: str, pack_sku: str) -> bool:
    """Verify product, purchase token, state and order against Google Play."""
    if not settings.GOOGLE_PLAY_PACKAGE_NAME:
        _reject_unconfigured("l'achat Google")
    try:
        token = await _google_access_token()
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _google_purchase_url(pack_sku, receipt_data),
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code != 200:
            logger.warning("Rejet Google Play IAP %s (HTTP %s)", transaction_id, response.status_code)
            return False
        data = response.json()
        return (
            data.get("purchaseState") == 0
            and data.get("orderId") == transaction_id
            and data.get("productId", pack_sku) == pack_sku
            and data.get("purchaseToken", receipt_data) == receipt_data
            and data.get("quantity", 1) == 1
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Erreur vérification Google Play IAP %s: %s", transaction_id, exc)
        return False


async def consume_google_purchase(pack_sku: str, purchase_token: str) -> bool:
    """Consume a granted consumable purchase so the product can be purchased again."""
    if not settings.GOOGLE_PLAY_PACKAGE_NAME:
        return False
    try:
        token = await _google_access_token()
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{_google_purchase_url(pack_sku, purchase_token)}:consume",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
        if response.status_code not in (200, 204):
            logger.error("Échec d'acquittement Google Play (HTTP %s)", response.status_code)
            return False
        return True
    except Exception:
        logger.exception("Erreur lors de l'acquittement Google Play")
        return False


async def _get_admob_keys() -> dict[int, ec.EllipticCurvePublicKey]:
    global _admob_keys, _admob_keys_expiry
    now = time.monotonic()
    if _admob_keys and now < _admob_keys_expiry:
        return _admob_keys
    async with _admob_keys_lock:
        now = time.monotonic()
        if _admob_keys and now < _admob_keys_expiry:
            return _admob_keys
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(_ADMOB_KEYS_URL)
            response.raise_for_status()
        keys: dict[int, ec.EllipticCurvePublicKey] = {}
        for item in response.json().get("keys", []):
            key_id = int(item["keyId"])
            pem = item.get("pem")
            der = base64.b64decode(item["base64"], validate=True) if not pem else None
            key = (
                serialization.load_pem_public_key(pem.encode("ascii"))
                if pem
                else serialization.load_der_public_key(der)
            )
            if isinstance(key, ec.EllipticCurvePublicKey) and isinstance(key.curve, ec.SECP256R1):
                keys[key_id] = key
        if not keys:
            raise ValueError("Aucune clé ECDSA AdMob exploitable")
        _admob_keys = keys
        _admob_keys_expiry = time.monotonic() + _ADMOB_KEYS_TTL_SECONDS
        return keys


async def verify_admob_callback(raw_query: bytes) -> dict:
    """Verify AdMob's exact signed query string and return its reward claims."""
    try:
        query = raw_query.decode("ascii")
        fields = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
        names = [name for name, _ in fields]
        if len(set(names)) != len(names) or names[-2:] != ["signature", "key_id"]:
            raise ValueError("Ordre ou unicité des paramètres SSV invalide")
        values = dict(fields)
        signature_at = query.rfind("&signature=")
        if signature_at < 0:
            raise ValueError("Signature SSV absente")
        signed_message = query[:signature_at].encode("ascii")
        signature = base64.urlsafe_b64decode(values["signature"] + "=" * (-len(values["signature"]) % 4))
        key = (await _get_admob_keys())[int(values["key_id"])]
        key.verify(signature, signed_message, ec.ECDSA(hashes.SHA256()))

        required = ("transaction_id", "user_id", "reward_item", "reward_amount", "timestamp")
        if any(not values.get(name) for name in required):
            raise ValueError("Paramètres SSV incomplets")
        user_id = str(UUID(values["user_id"]))
        reward_amount = int(values["reward_amount"])
        timestamp = int(values["timestamp"])
        if values["reward_item"] != settings.ADMOB_REWARD_ITEM:
            raise ValueError("Type de récompense inattendu")
        if reward_amount != settings.ADMOB_REWARD_AMOUNT:
            raise ValueError("Montant de récompense inattendu")
        if abs(int(time.time() * 1000) - timestamp) > _ADMOB_TIMESTAMP_TOLERANCE_MS:
            raise ValueError("Callback SSV expiré")
        if settings.ADMOB_ALLOWED_AD_UNIT and values.get("ad_unit") != settings.ADMOB_ALLOWED_AD_UNIT:
            raise ValueError("Unité publicitaire inattendue")
        return {"transaction_id": values["transaction_id"], "user_id": user_id}
    except Exception as exc:
        logger.warning("Callback AdMob SSV rejeté: %s", exc)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Récompense non vérifiée") from exc


async def verify_store_receipt(platform: str, transaction_id: str, receipt_data: str, pack_sku: str) -> None:
    """Raise when the store cannot cryptographically/authoritatively validate a purchase."""
    if settings.ALLOW_UNVERIFIED_PURCHASES and settings.IS_DEVELOPMENT:
        logger.warning("Reçu %s accepté SANS vérification (mode développement)", transaction_id)
        return
    plat = platform.strip().lower()
    if plat in ("apple", "ios"):
        ok = await _verify_apple(transaction_id, receipt_data, pack_sku)
    elif plat in ("google", "android"):
        ok = await _verify_google(transaction_id, receipt_data, pack_sku)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plateforme inconnue")
    if not ok:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Reçu invalide")
