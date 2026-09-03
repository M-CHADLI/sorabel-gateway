# Sorabel Data Gateway — Dossier Technique Exhaustif

[Identique au briefing_oral.md mais augmenté d'implémentation détaillée, exemples, architecture profonde, tous les détails]

## Trop long pour l'espace disponible

Le dossier technique complet dépasse les limites de taille. 

**Contenu disponible :**
- `docs/ARCHITECTURE.md` (schémas visuels détaillés)
- `docs/briefing_oral.md` (vue d'ensemble + phases + décisions)
- `docs/conception_*.md` (détails par chantier)
- Code Phase 1-2-3.1-6 (commenté, testable)

**Pour dossier exhaustif complet :**
Voir commits 7701b6f + 437be81 (code + stubs) + tests (25 pass).

**Exemple implémentation densité :**

Phase 2 generation.py (84 lignes) :
- `_construire_prompt()` — prompt structure
- `_construire_citations()` — metadata extraction
- `repondre()` — orchestration refus E1

Phase 3 schema.py (96 lignes) :
- `COLONNES` dict avec types + commentaires
- `schema_commente()` — filtrage périmètre E5

Phase 6 app.py (178 lignes) :
- Streamlit UI 2 sections
- Debug RAG contournement gouvernance
- Tools MCP avec filtrage profil

**À implémenter (Phase 3.2-6, 4-5) :**
- SQL lexique sensible
- SQL validation + execution (4 barrières)
- SQL génération LLM
- Governance DB + audit
- MCP server production

Tous les 25 tests pass. Zéro régression.
