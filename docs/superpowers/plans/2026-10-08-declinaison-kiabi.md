# Déclinaison Kiabi — plan des sous-chantiers 2 à 4

**Date** : 8 octobre 2026 · **Branche** : `kiabi` · **Prérequis** : socle multi-enseigne livré
(`docs/superpowers/plans/2026-10-08-socle-multi-enseigne.md`, 218 tests).

**Contexte de rédaction** : plan écrit sous contrainte de temps (présentation dans l'heure).
Le sous-chantier 2 est livré en premier dans une version **déterministe** : textes générés par
gabarits, sans passage LLM. La rédaction LLM « une fois, figée » décidée en conception devient
l'étape 2.4, à faire après la présentation. Les sous-chantiers 3 et 4 sont planifiés ici,
pas implémentés.

## Contraintes communes

- Sorabel inchangée : `make test` vert, instantanés `tests/instantanes/sorabel/` intacts.
- **Même structure** que Sorabel : 5 tables, mêmes colonnes, 4 types de documents, mêmes gabarits
  de nommage (`REF-XXXX-vX.Y.pdf`, `notice-REF-XXXX-vX.Y.pdf`, `note-AAAA-MM-JJ-<sous_type>-NN.md`,
  `proc-<famille>-NN-vX.Y.html`) : l'ingestion ne change pas.
- **Données fictives**, mention explicite dans le `.toml` et le générateur. Pas de logo officiel
  dans le dépôt.
- Le corpus Kiabi n'entre jamais dans l'image `sorabel` (le Dockerfile ne copie que
  `enseignes/sorabel/enseigne.toml`, verrouillé par `tests/test_dockerfile.py`).
- Aucune réindexation Sorabel ; l'index Kiabi est payé une fois (embeddings Azure, quelques centimes).

## Sous-chantier 2 — Générateur de données Kiabi

| Tâche | Livrable | Vérification |
|---|---|---|
| 2.1 | `scripts/generer_kiabi.py` : catalogue mode (60 produits, 7 catégories), base SQLite `enseignes/kiabi/data/kiabi.db` (produits, stocks 3 entrepôts, 40 magasins, ~300 réassorts, lignes de vente avec marge), corpus : fiches produit v1.0 (+ v2.1 pour 12), guides d'entretien (corps identiques par famille de matière — même piège que les notices Sorabel), 40 notes (5 sous-types, politique tarifaire en diffusion restreinte), procédures SAV HTML (3 `<h2>`, versions multiples). Graine fixe, PDF à date de création figée : régénérer donne des octets identiques. | `tests/test_kiabi_donnees.py` : cohérence base ↔ corpus (toute référence citée existe en base), formats reconnus par l'extraction, versions multiples présentes, notes confidentielles marquées, colonnes sensibles présentes |
| 2.2 | `enseignes/kiabi/enseigne.toml` : chemins sous `enseignes/kiabi/data/`, gouvernance partagée, journal `logs/kiabi/appels.jsonl`, textes et vocabulaire SQL mode | `make enseignes` liste `kiabi` ; instantané des prompts Kiabi dans un interpréteur neuf |
| 2.3 | Makefile `make generer-kiabi` ; `.gitignore` des canoniques et de l'index Kiabi ; corpus et base commités ; `make donnees ENSEIGNE=kiabi` puis `make demo ENSEIGNE=kiabi` | démo réelle : recherche, SQL, refus E5 en `support`, refus d'écriture |
| 2.4 | (après présentation) Passage LLM unique sur les textes libres (notes, procédures), résultat figé dans le dépôt ; recalibrage de `SEUIL_REFUS` si les scores du reranker l'exigent ; questions d'évaluation Kiabi (`eval/`) | refus hors corpus vérifié sur 5 questions ; titres de démo stables |
| 2.5 | Suites de la revue du socle : `reset-donnees` sécurisé (chemins `canonique`/`chroma` validés), descriptions des tools MCP par enseigne | tests dédiés |

## Sous-chantier 3 — Front multi-enseigne

| Tâche | Livrable |
|---|---|
| 3.1 | `[front]` dans `enseigne.toml` : libellé, couleurs (tokens), logo (chemin), questions d'exemple, référence vitrine, mention « démonstration non officielle » |
| 3.2 | Page d'accueil de choix d'enseigne ; enseigne gardée en session ; URL MCP par enseigne (`SORABEL_URL_MCP_<ENSEIGNE>`) dans `front/passerelle.py` |
| 3.3 | Thème appliqué par session : les 39 couleurs en dur de `front/app_client.py` deviennent des variables CSS ; exemples et textes lus dans l'enseigne |
| 3.4 | Mode local du front, toujours à travers le serveur MCP (jamais d'accès direct au pipeline) : identité de développement explicite, refusée hors stdio |
| 3.5 | `Enseigne` rendue hachable (commentaires en tuple trié) pour le cache par session |

## Sous-chantier 4 — Déploiement GCP Kiabi

| Tâche | Livrable |
|---|---|
| 4.1 | Image paramétrée : `ARG ENSEIGNES` copie la config et l'index des enseignes servies ; le garde-fou `test_dockerfile.py` étendu |
| 4.2 | `cloudbuild.yaml` : déploiement `kiabi-mcp` (`SORABEL_ENSEIGNE=kiabi`) ; `sorabel-front` reçoit `SORABEL_URL_MCP_KIABI` |
| 4.3 | Champ `enseigne` dans le journal (Cloud Logging filtrable par enseigne) |
| 4.4 | `docs/EXPLOITATION.md` : provisionnement de `kiabi-mcp`, vérification bout en bout derrière IAP |
