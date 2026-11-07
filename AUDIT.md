# Audit technique et sécurité

Date : 7 novembre 2026
Périmètre : backend FastAPI, gestion des enchères, achats, configuration Docker et dépôt visible.

## Correctifs appliqués

| Sévérité | Constat | Correctif |
| --- | --- | --- |
| Élevée | `Dockerfile` copie tout le contexte dans l’image; `.env` n’était pas exclu et pouvait donc exposer des identifiants dans les couches de l’image. | `.dockerignore` exclut `.env` et ses variantes tout en conservant `.env.example`. |
| Élevée | La validation Apple créditait un achat après un simple HTTP 200, sans vérifier le JWS signé ni ses claims. | App Store Server Library vérifie la chaîne X.509 et le JWS; transaction, produit, bundle et révocation doivent concorder. Les crédits restent refusés sans configuration valide. |
| Moyenne | Le plafond de parties actives comptait seulement les enchères en cours, pas les salons en attente; deux créations concurrentes pouvaient dépasser le plafond. | Les salons en attente/en cours sont comptés et le compte hôte est verrouillé pendant le contrôle et la création. |
| Élevée | Les récompenses publicitaires utilisaient un HMAC privé au lieu de vérifier les callbacks SSV AdMob. | Le serveur valide la signature ECDSA sur la query brute, les claims attendus, la fraîcheur et l’unité; le transaction ID rend le crédit idempotent. |
| Moyenne | Des valeurs fournisseur étaient insérées directement dans les segments d’URL Google Play; les jetons étaient statiques et les achats consommables n’étaient pas consommés. | Les segments d’URL sont encodés; produit, token, ordre et état sont comparés; le compte de service peut renouveler les jetons, puis l’achat est consommé après crédit. |
| Moyenne | Les refresh tokens pouvaient être rejoués jusqu’à expiration et les URI contenant des caractères réservés pouvaient être mal formées. | Ajout d’une rotation persistée via `jti` et construction des URL PostgreSQL/Redis par les helpers SQLAlchemy. |
| Moyenne | Les limites de débit retombaient en mémoire multi-instance et Redis n’était pas exigé au démarrage production. | Redis est vérifié au démarrage production et les dépendances de quotas échouent fermées sans stockage partagé. |

## Prérequis opérationnels

- **Identifiants externes :** Apple nécessite les racines PKI, le bundle ID, l’identifiant d’application en production et les clés App Store Connect; Google Play nécessite un compte de service Android Publisher; AdMob nécessite l’URL SSV et l’UUID utilisateur. Ces identifiants ne viennent pas du dépôt; leur présence dans l’environnement déployé n’a pas été vérifiée. Sans eux, les crédits restent fail-closed.
- **Réplicas hors Compose :** le service Compose applique les migrations avant l’API. Un déploiement multi-réplicas distinct doit appliquer `alembic upgrade head` dans une étape unique avant le rollout.

## État du dépôt et vérification

Les changements locaux préexistants sur `.gitignore`, la migration 0002, `app/core/database.py`, `frontend/src/services/synergyHelper.ts`, `tests/test_token_ledger.py` et la base SQLite non suivie ont été laissés intacts.

Vérifications : 48 tests backend réussis; `npm run build` réussi; `npm run lint` réussi avec trois avertissements React; une seule tête Alembic (`0006_refresh_token_rotation`); `git diff --check` sans erreur. Les tests async ont été exécutés hors sandbox, car le sandbox bloque `socketpair()` sur Windows.
