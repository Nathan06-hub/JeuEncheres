"""Vérification serveur des reçus d'achat et des récompenses publicitaires.

Lorsque les identifiants fournisseurs (`APPLE_IAP_BEARER_TOKEN`, `GOOGLE_PLAY_ACCESS_TOKEN`,
`ADMOB_SSV_SHARED_SECRET`) sont configurés, les vérifications App Store Server API,
Google Play Developer API et AdMob SSV sont exécutées.
Par défaut (sans identifiants configurés), tout crédit est REFUSÉ en 501 (fail-closed),
sauf si `ALLOW_UNVERIFIED_PURCHASES=true` en environnement de développement.
"""
import hashlib
import hmac
import logging

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_SECONDS = 8.0


def _reject_unconfigured(what: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Vérification serveur de {what} non configurée : crédit refusé",
    )


async def _verify_apple(transaction_id: str, receipt_data: str, pack_sku: str) -> bool:
    """Vérifie une transaction Apple via l'App Store Server API (/inApps/v1/transactions/{transactionId})."""
    if not settings.APPLE_IAP_BEARER_TOKEN:
        _reject_unconfigured("l'achat Apple")

    url = f"{settings.APPLE_IAP_VERIFY_URL.rstrip('/')}/inApps/v1/transactions/{transaction_id}"
    headers = {"Authorization": f"Bearer {settings.APPLE_IAP_BEARER_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning("Rejet Apple IAP %s (HTTP %s)", transaction_id, resp.status_code)
            return False
        data = resp.json()
        product_id = data.get("productId") or data.get("bundleId")
        if product_id and data.get("productId") and data["productId"] != pack_sku:
            logger.warning("Mismatch SKU Apple IAP: attendu=%s reçu=%s", pack_sku, data.get("productId"))
            return False
        return True
    except Exception as exc:
        logger.error("Erreur vérification Apple IAP %s: %s", transaction_id, exc)
        return False


async def _verify_google(transaction_id: str, receipt_data: str, pack_sku: str) -> bool:
    """Vérifie un achat Google Play via l'API Android Publisher (purchases.products.get)."""
    if not settings.GOOGLE_PLAY_PACKAGE_NAME or not settings.GOOGLE_PLAY_ACCESS_TOKEN:
        _reject_unconfigured("l'achat Google")

    url = (
        "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
        f"{settings.GOOGLE_PLAY_PACKAGE_NAME}/purchases/products/{pack_sku}/tokens/{receipt_data}"
    )
    headers = {"Authorization": f"Bearer {settings.GOOGLE_PLAY_ACCESS_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning("Rejet Google Play IAP %s (HTTP %s)", transaction_id, resp.status_code)
            return False
        data = resp.json()
        # purchaseState == 0 correspond à Purchased dans l'API Google Play
        if data.get("purchaseState") != 0:
            return False
        order_id = data.get("orderId")
        if order_id and order_id != transaction_id:
            logger.warning("Mismatch orderId Google Play: attendu=%s reçu=%s", transaction_id, order_id)
            return False
        return True
    except Exception as exc:
        logger.error("Erreur vérification Google Play IAP %s: %s", transaction_id, exc)
        return False


async def _verify_ad_ssv(reward_token: str, ad_network: str, user_id: str) -> bool:
    """Vérifie un jeton de récompense publicitaire signé (`<nonce>:<hmac_sha256>`)."""
    if not settings.ADMOB_SSV_SHARED_SECRET:
        _reject_unconfigured("la récompense publicitaire")

    if ":" not in reward_token:
        return False
    nonce, signature = reward_token.rsplit(":", 1)
    if not nonce or not signature:
        return False
    message = f"{user_id}:{ad_network.strip().lower()}:{nonce}".encode("utf-8")
    expected_sig = hmac.new(
        settings.ADMOB_SSV_SHARED_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature.lower(), expected_sig.lower())


async def verify_store_receipt(platform: str, transaction_id: str, receipt_data: str, pack_sku: str) -> None:
    """Lève une HTTPException si le reçu n'est pas valide (ou ne peut pas être vérifié)."""
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


async def verify_rewarded_ad(reward_token: str, ad_network: str, user_id: str) -> None:
    if settings.ALLOW_UNVERIFIED_PURCHASES and settings.IS_DEVELOPMENT:
        logger.warning("Récompense pub acceptée SANS vérification (mode développement)")
        return
    if not await _verify_ad_ssv(reward_token, ad_network, user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Récompense non vérifiée")
