"""Vérification serveur des reçus d'achat et des récompenses publicitaires.

Aucune vérification réelle (App Store Server API, Google Play Developer API, AdMob SSV)
n'est encore branchée : par défaut, tout crédit est REFUSÉ (fail-closed). Le mode
`ALLOW_UNVERIFIED_PURCHASES=true` n'est accepté qu'en développement (voir config.py).
Pour brancher un vrai fournisseur, implémenter `_verify_apple`, `_verify_google`, `_verify_ad_ssv`.
"""
import logging

from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


def _reject_unconfigured(what: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Vérification serveur de {what} non configurée : crédit refusé",
    )


async def _verify_apple(transaction_id: str, receipt_data: str, pack_sku: str) -> bool:
    _reject_unconfigured("l'achat Apple")
    return False


async def _verify_google(transaction_id: str, receipt_data: str, pack_sku: str) -> bool:
    _reject_unconfigured("l'achat Google")
    return False


async def _verify_ad_ssv(reward_token: str, ad_network: str, user_id: str) -> bool:
    _reject_unconfigured("la récompense publicitaire")
    return False


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
        logger.warning("Récompense pub accepté SANS vérification (mode développement)")
        return
    if not await _verify_ad_ssv(reward_token, ad_network, user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Récompense non vérifiée")
