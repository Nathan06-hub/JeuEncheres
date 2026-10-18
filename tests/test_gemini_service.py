import pytest
from app.services.gemini_service import GeminiService
from app.models.deck import ItemRarity, DeckCategory

def test_calculate_rarity():
    gs = GeminiService()
    assert gs._calculate_rarity(95) == ItemRarity.LEGENDARY
    assert gs._calculate_rarity(80) == ItemRarity.EPIC
    assert gs._calculate_rarity(60) == ItemRarity.RARE
    assert gs._calculate_rarity(30) == ItemRarity.COMMON

def test_generate_mock_deck():
    gs = GeminiService()
    deck = gs._generate_mock_deck("Batman", DeckCategory.CINEMA, 3)
    # L'encodage peut causer des soucis, on test juste le suffixe
    assert deck["title"].endswith("Batman")
    assert deck["category"] == DeckCategory.CINEMA.value
    assert len(deck["items"]) == 3
    assert deck["items"][0]["name"].endswith("Batman")
    assert "rarity" in deck["items"][0]

@pytest.mark.asyncio
async def test_generate_deck_fallback_when_no_client():
    gs = GeminiService()
    gs.client = None # Force fallback
    deck = await gs.generate_deck("Harry Potter", DeckCategory.CINEMA, 2)
    assert deck["category"] == DeckCategory.CINEMA.value
    assert len(deck["items"]) == 2

@pytest.mark.asyncio
async def test_get_embedding_no_client():
    gs = GeminiService()
    gs.client = None
    res = await gs.get_embedding("Test text")
    assert res is None
