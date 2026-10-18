from fastapi import APIRouter
from app.api.v1.endpoints import auth, home, creation_ai, auction, auction_ws, results, shop

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["00 - Authentification"])
api_router.include_router(home.router, prefix="/home", tags=["01 - Accueil & Decks"])
api_router.include_router(creation_ai.router, prefix="/creation-ai", tags=["02 - Création IA"])
api_router.include_router(auction.router, prefix="/auction", tags=["03 - Enchères en Direct"])
api_router.include_router(auction_ws.router, prefix="/auction", tags=["03 - WebSocket Live Enchères"])
api_router.include_router(results.router, prefix="/results", tags=["04 - Résultats & Composition"])
api_router.include_router(shop.router, prefix="/shop", tags=["05 - Boutique & Jetons"])
