# Enchères & Drafts IA - Backend API

Backend REST & Real-time pour jeu mobile d'enchères et de drafts de culture générale par indices progressifs, alimenté par **FastAPI**, **SQLAlchemy 2.0 (Async)**, **PostgreSQL (pgvector)**, **Redis** et l'**API Google Gemini**.

---

## 🏗️ Architecture du Projet

Le projet suit les principes de la **Clean Architecture** et du **Domain-Driven Design (DDD)** :

```
├── alembic/                      # Migrations de schéma (avec support async & pgvector)
│   ├── env.py
│   └── versions/
├── alembic.ini                   # Configuration Alembic
├── app/
│   ├── main.py                   # Point d'entrée FastAPI, middlewares CORS et lifespans
│   ├── api/
│   │   ├── deps.py               # Injections de dépendances (DB async, CurrentUser, Redis)
│   │   └── v1/
│   │       ├── api.py            # Routeur principal API v1
│   │       └── endpoints/        # Endpoints alignés sur les 5 écrans Figma
│   │           ├── auth.py       # JWT & Onboarding rapide via device_id (Guest mobile)
│   │           ├── home.py       # 📱 Écran 01 : Accueil, jetons, chips catégories, decks
│   │           ├── creation_ai.py# 📱 Écran 02 : Création IA, 3 indices & score 1-100
│   │           ├── auction.py    # 📱 Écran 03 : Enchères aveugles, rounds & timers
│   │           ├── results.py    # 📱 Écran 04 : Calcul des synergies IA, ROI & podium
│   │           └── shop.py       # 📱 Écran 05 : Packs payants, pubs vidéo & historique
│   ├── core/
│   │   ├── config.py             # Variables d'environnement (Pydantic Settings v2)
│   │   ├── database.py           # Async SQLAlchemy Engine, pool & init extensions
│   │   ├── redis.py              # Pool Redis asynchrone (Cache & Real-time)
│   │   └── security.py           # Chiffrement bcrypt & JWT
│   ├── models/                   # Modèles SQLAlchemy 2.0 (Mapped / mapped_column)
│   │   ├── base.py               # Base déclarative, mixins UUID v4 et Timestamps UTC
│   │   ├── user.py               # Utilisateur, guest device_id & solde jetons
│   │   ├── token.py              # Grand livre TokenTransaction & catalogue TokenPack
│   │   ├── deck.py               # Deck & DeckItem (3 indices, score 1-100, pgvector)
│   │   ├── game.py               # GameSession & GameSessionPlayer
│   │   └── bid.py                # Bid (enchères) & DraftedItem (compo d'équipe)
│   ├── schemas/                  # Schémas de validation Pydantic v2
│   │   ├── common.py, user.py, token.py, deck.py, game.py, bid.py
│   └── services/                 # Logique métier pure et orchestration
│       ├── token_service.py      # Débit/crédit atomique, traçabilité IAP et Ad rewards
│       ├── gemini_service.py     # Prompting structuré Gemini & embeddings 768-dim
│       ├── auction_engine.py     # Moteur d'enchères, gestion des manches et chronos
│       └── synergy_calculator.py # Évaluation des synergies d'équipe et ROI
├── tests/
│   ├── conftest.py               # Client HTTP de test Async
│   └── test_models.py            # Tests unitaires des modèles, sécurité et endpoints
├── .env.example
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 📱 Correspondance avec les 5 Écrans Frontend (Figma)

| Écran Figma | Endpoints Backend associés | Description / Fonctionnalités |
| :--- | :--- | :--- |
| **01_Accueil** | `GET /api/v1/home/summary`<br>`GET /api/v1/home/decks/popular`<br>`POST /api/v1/home/quick-game` | Solde jetons (⚡ 3), chips de catégories, grille des thèmes populaires et création instantanée de partie rapide. |
| **02_Creation_IA** | `GET /api/v1/creation-ai/suggestions`<br>`POST /api/v1/creation-ai/generate` | Chips de suggestions, saisie libre d'un sujet, déduction atomique d'1 jeton et génération Gemini (3 indices + scores 1-100 + embeddings). |
| **03_Enchere** | `GET /api/v1/auction/sessions/{id}/live-state`<br>`POST /api/v1/auction/sessions/{id}/bid`<br>`POST /api/v1/auction/sessions/{id}/advance` | Timer en direct, manche active, révélation progressive des indices (1->2->3), soumission des enchères et passage. |
| **04_Resultats** | `GET /api/v1/results/sessions/{id}/results` | Podium des vainqueurs, composition d'équipe de chaque joueur, calcul des bonus de synergie IA et indicateur de ROI. |
| **05_Boutique** | `GET /api/v1/shop/packs`<br>`POST /api/v1/shop/verify-iap`<br>`POST /api/v1/shop/claim-rewarded-ad`<br>`GET /api/v1/shop/transactions` | Grille des packs ($0.99, $2.49 "Meilleure Valeur", $6.99), validation d'achat In-App, +1 jeton gratuit via vidéo publicitaire. |

---

## 🚀 Démarrage Rapide

### 1. Pré-requis
- Python 3.11+
- PostgreSQL 15+ avec extension `pgvector`
- Redis 7+

### 2. Installation
```bash
# Cloner le dépôt et créer l'environnement virtuel
python3 -m venv .venv
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt
```

### 3. Configuration de l'Environnement
```bash
cp .env.example .env
# Renseigner vos accès PostgreSQL, Redis et votre GEMINI_API_KEY dans .env
```

### 4. Lancement du Serveur de Développement
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Documentation Swagger UI** : [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **Documentation ReDoc** : [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc)
- **Sonde de santé** : [http://localhost:8000/health](http://localhost:8000/health)

### 5. Exécution des Tests
```bash
pytest -v tests/
```
