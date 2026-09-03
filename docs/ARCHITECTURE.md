# Architecture Sorabel Data Gateway

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│                     Clients MCP                             │
│        (Bot Support, Poste Commercial, IDE)                 │
└────────────────┬────────────────────────────────────────────┘
                 │
         ┌───────▼─────────┐
         │   MCP Server    │
         │  (Phase 5)      │
         └───────┬─────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
    ▼            ▼            ▼
┌────────┐  ┌───────────┐  ┌──────────┐
│  RAG   │  │Text-to-SQL│  │Governance│
│Phase 2 │  │ Phase 3   │  │ Phase 4  │
└────────┘  └───────────┘  └──────────┘
    │            │              │
    └────────────┼──────────────┘
                 │
      ┌──────────▼──────────┐
      │  Frontend Streamlit │
      │    (Phase 6)        │
      └─────────────────────┘
```

## Phases et composants

### Phase 1 : Extracteur Notes ✅
- **Entrée** : 80 fichiers Markdown (corpus/notes/)
- **Sortie** : Chunks avec métadonnées (titre, date, auteur, type, version)
- **Code** : `sorabel_rag/extraction.py`, `sorabel_rag/chunking.py`
- **Tests** : 10 tests d'ingestion et chunking

### Phase 2 : Client LLM + Génération RAG ✅
```
Question → Retrieval (Dense + BM25 + RRF) → Reranking → LLM
         ↓
      Citations (métadonnées chunks) + Réponse
```
- **Code** : 
  - `sorabel_llm/client.py` — Azure OpenAI (GPT-5.4-mini)
  - `sorabel_rag/generation.py` — Prompt construction, citations, refus déterministe
- **Tests** : 2 tests LLM, 8 tests génération
- **Refus hors corpus** : Score < SEUIL_REFUS → pas de génération

### Phase 3 : Text-to-SQL (En cours)
```
Question SQL (langage naturel)
    ↓
Schéma filtré par profil (colonnes interdites masquées)
    ↓
LLM génère SQL (instructions, validation)
    ↓
4 barrières : read-only + validation + LIMIT + timeout
    ↓
Résultat ou refus
```
- **Task 1** ✅ : `sorabel_sql/schema.py` — Schéma commenté avec périmètre
- **Task 2-6** : Lexique sensible, validation, execution, generation, composition

### Phase 4 : Governance (Matrice d'accès)
```
Profil (support, commercial, dev, admin)
    ↓
Perimetre : tables_autorisees() + colonnes_interdites(table)
    ↓
Appliqué partout : RAG filtering + SQL schema + outils MCP
    ↓
Journalisation complète (qui, quoi, quand, accès autorisé/refusé)
```
- 6 tasks : schéma DB, seed données, validation Pydantic, Perimetre, filtering, journalisation

### Phase 5 : MCP Server
```
4 tools RAG :
  ├─ answer_question(q, profile)    → réponse + citations
  ├─ search_docs(q, profile)        → top-K chunks
  ├─ get_document(ref + version?)   → document entier
  └─ list_sources(profile)          → corpus metadata

4 tools SQL :
  ├─ ask_database(q, profile)       → résultat requête
  ├─ get_schema(profile)            → schéma filtré
  ├─ check_stock(ref, profile)      → niveau stock
  └─ order_status(cmd_id, profile)  → statut commande
```
- Serveur MCP exposant ces 8 tools
- Chaque appel : auth profil → périmètre → filtrage → résultat + log

### Phase 6 : Frontend Streamlit
```
Utilisateur (pose une question)
    ↓
Sélecteur profil (support, commercial, dev, admin)
    ↓
Onglets :
  ├─ RAG (search_docs, answer_question, get_document)
  ├─ SQL (ask_database, schema, check_stock, order_status)
  └─ Logs (audit trail)
    ↓
Affichage résultats + citations + métadonnées
```
- 3 tasks : bridge MCP client, interface Streamlit, tests manuels

## Données

### Corpus (230 PDF + Markdown + HTML)
| Type | Nb | Format | Métadonnées | Versions |
|------|-----|--------|-------------|----------|
| Fiches | 150 | PDF | Dans nom (REF-XXXX-vM.m) | Multiples |
| Notices | 80 | PDF | Dans nom (notice-REF-XXXX) | Multiples |
| Notes | 80 | MD | Front-matter YAML | Une seule |
| SAV | 90 | HTML | `<meta>`, sections `<h2>` | Multiples |

Pivot : `produits.ref` = REF-XXXX du corpus

### Base SQLite (sorabel.db)
```
produits(ref PK, nom, catégorie, prix_vente_ht, prix_achat_ht*, marge_pct*, ...)
stocks(id PK, ref FK, entrepôt, quantité, ...)
clients(id PK, raison_sociale, segment, ville, ...)
commandes(id PK, client_id FK, date, statut, montant_ht, ...)
ventes(id PK, commande_id FK, ref FK, quantité, marge_ht*, ...)
  * = colonnes sensibles (profil support ne les voit pas)
```

## Sécurité & Gouvernance

### Matrice d'accès (4 profils)
| Profil | Tables | Colonnes masquées | Outils MCP |
|--------|--------|-------------------|-----------|
| support | produits, stocks, clients, commandes, ventes | prix_achat_ht, marge_pct, marge_ht | search_docs, answer_question, check_stock, order_status |
| commercial | tous | (aucune) | tous RAG + SQL |
| dev | tous | (aucune) | tous |
| admin | tous | (aucune) | tous + logs |

### 4 barrières Text-to-SQL
1. **Connexion** : SQLite en read-only
2. **Validation** : Schéma + instruction validée avant exécution
3. **Colonnes** : Périmètre filtre CREATE TABLE
4. **Exécution** : LIMIT + timeout + pas de mutations

### Citations RAG
Construites par le code, jamais demandées au LLM :
```python
{
  "titre": "REF-1024-v2.1.pdf",
  "reference": "REF-1024",
  "date": "2025-01-15",
  "type_document": "fiche produit"
}
```

## Workflows

### RAG complet
1. **Ingestion** (Phase 1) → chunks + métadonnées → Chroma
2. **Retrieval** (Phase 2) → Dense (embeddings) + BM25 + RRF fusion
3. **Reranking** → Cross-encoder (score pertinence)
4. **Filtrage** (Phase 4) → Profil masque certains chunks
5. **Prompt** → Instructions + schéma + top-K chunks + question
6. **Génération** → LLM répond OU refus déterministe si score < seuil
7. **Citations** → Métadonnées chunks réellement utilisés

### SQL complet
1. **Question** (langage naturel) + profil
2. **Schéma filtré** (Phase 3 Task 1) → colonnes interdites masquées
3. **Prompt** → Instructions + schéma + question
4. **Génération SQL** (Phase 3 Task 5) → LLM produit SQL
5. **Validation** (Phase 3 Task 4) → Parsing, LIMIT, mutation check
6. **Exécution** (Phase 3 Task 6) → Connexion read-only + timeout
7. **Résultat** → Données retournées (logs audit)

## Tests

### TDD appliqué à chaque phase
```
RED (test échoue)
  ↓
GREEN (code implémente)
  ↓
SUITE COMPLÈTE (aucune régression)
  ↓
COMMIT (avec message normalisé)
```

### Métrique d'évaluation E6
**Hybrid RAG** validé sur `eval/questions_rag.jsonl` :
- Questions par **référence exacte** (lexique connu)
- Questions en **langage naturel** (découverte)
- Métriques : Recall@5, MRR, Hit@1 (rapportées séparément)

## Fichiers clés

```
sorabel/
├── sorabel_rag/
│   ├── ingestion.py      (extraction + chunking Phase 1)
│   ├── generation.py     (LLM + citations + refus Phase 2)
│   └── retrieval.py      (dense + BM25 + RRF)
├── sorabel_llm/
│   └── client.py         (Azure OpenAI client Phase 2)
├── sorabel_sql/
│   └── schema.py         (schéma filtré Phase 3 Task 1)
├── gouvernance/
│   ├── perimetre.py      (Perimetre duck-typed Phase 4)
│   └── audit.py          (journalisation Phase 4)
├── mcp_server/
│   └── server.py         (exposition tools Phase 5)
├── streamlit_app.py      (interface Phase 6)
└── tests/
    ├── test_*.py         (TDD pour chaque phase)
    └── eval/
        └── run_eval.py   (E6 : évaluation RAG hybride)
```

## Détail des rôles et étapes

### sorabel_rag/ingestion.py — Phase 1 : Extraction corpus

**Rôle** : Lire corpus brut (PDF, MD, HTML) → chunks structurés + métadonnées.

**Étapes** :
1. **Extraction métadonnées** (avant lecture contenu)
   - PDF (fiches/notices) : regex sur nom `REF-XXXX-vM.m.pdf`
   - Markdown : parser YAML front-matter (titre, date, auteur, type, version)
   - HTML SAV : extraire `<title>`, `<meta name="version"|"date"|"type">`

2. **Lecture contenu**
   - PDF → OCR + nettoyage
   - Markdown → body (après front-matter)
   - HTML → sections `<h2>` (Conditions, Étapes, etc.)

3. **Chunking structurel**
   - Par section (pas taille fixe) pour cohérence sémantique
   - Fusion sections courtes (< 200 tokens)
   - Résultat : `[{chunk_text, reference, version, est_version_courante, date, type_document, titre, auteur}]`

**Sortie** : Chunks indexés dans Chroma + métadonnées pour citations.

---

### sorabel_rag/retrieval.py — Phase 2 : Hybrid search

**Rôle** : Récupérer K chunks pertinents (dense + sparse + fusion).

**Pipeline** :
```
Question
  ├─ 1. Dense (embeddings Chroma) → top-50 chunks
  ├─ 2. BM25 (TF-IDF sparse) → top-50 chunks
  └─ 3. RRF fusion (score = 1/(rank_dense+1) + 1/(rank_bm25+1)) → top-10 final
```

**Sortie** : Top-10 chunks avec scores, prêts pour reranking.

---

### sorabel_rag/generation.py — Phase 2 : LLM + Citations + Refus

**Rôle** : Répondre question ou refuser déterministe.

**Étapes** :
1. **Reranking** → Cross-encoder score chaque chunk (0-1)
2. **Filtrage profil** → Perimetre masque chunks sensibles
3. **Check refus** → Meilleur score < SEUIL_REFUS (ex: 0.5) ? Arrêt.
4. **Prompt construction** → Instructions + schéma chunks + question
5. **LLM appel** → Azure GPT-5.4-mini (temp=0.3)
6. **Citations** → Extraire titre/ref/date des chunks utilisés (jamais demander LLM)
7. **Retour JSON** :
   ```json
   {
     "statut": "succès|hors_corpus|erreur",
     "réponse": "La REF-1024...",
     "confiance": 0.87,
     "sources": [{"titre": "REF-1024-v2.1.pdf", "reference": "REF-1024", "date": "2025-01-15"}]
   }
   ```

**Clé** : Refus hors corpus = retour normal (pas d'exception), dépend score pas LLM.

---

### sorabel_llm/client.py — Phase 2 : Client LLM centralisé

**Rôle** : Interface unique vers Azure OpenAI.

**Méthodes** :
- `embed(text)` → Liste[float] (embeddings)
- `generate(prompt, system, temp)` → str (texte généré)
- `rerank_score(question, chunk)` → float (0-1, pertinence)

**Config** : Variables `.env` → `AZURE_API_KEY`, `AZURE_DEPLOYMENT_ID`, etc.

**Sortie** : Tous LLM calls centralisés (facile à logger, swapper modèle).

---

### sorabel_sql/schema.py — Phase 3 Task 1 : Schéma filtré

**Rôle** : Exposer schéma SQL commenté, masquant colonnes sensibles par profil.

**Étapes** :
1. **Introspection SQLite** → Tables, colonnes, types, contraintes
2. **Annotation commerciale** → Descriptions humaines, exemples
3. **Filtrage Perimetre** → Masquer colonnes interdites pour profil
   - Support : cache `prix_achat_ht`, `marge_pct`, `marge_ht`
   - Commercial/Dev/Admin : tout visible

**Sortie** : JSON schéma (`{tables: [{name, description, columns: [{name, type, hidden}]}]}`) pour LLM.

---

### sorabel_sql/sql_generator.py — Phase 3 Task 5 : Génération SQL

**Rôle** : Question naturelle → SQL SELECT.

**Étapes** :
1. Appel LLM avec schéma filtré + instructions SQL
2. Parser réponse JSON → extraire SQL brut
3. Ajouter `LIMIT 100` si absent
4. Validation (phase suivante)

**Sortie** : SQL SELECT validé ou erreur.

---

### sorabel_sql/sql_executor.py — Phase 3 Task 6 : Exécution safe

**Rôle** : Exécuter SQL avec 4 barrières de sécurité.

**Barrières** :
1. **Connexion read-only** → `PRAGMA query_only = ON` + fichier read-only OS
2. **Validation AST** → Rejeter INSERT/UPDATE/DELETE/EXEC
3. **Filtrage colonnes** → Vérifier colonnes ne sont pas interdites
4. **Exécution sandboxée** → `LIMIT 100` obligatoire + timeout 10s

**Sortie** : JSON `{statut, données: [], ligne_nb, temps_ms, sql_exécuté}`.

---

### gouvernance/perimetre.py — Phase 4 : Matrice d'accès

**Rôle** : Décider qui voit quoi (tables, colonnes, outils MCP).

**Méthodes** :
- `tables_autorisées(profil)` → Liste tables visibles
- `colonnes_interdites(profil, table)` → Liste colonnes masquées
- `chunks_autorisés(profil, chunks)` → Chunks filtrés
- `outils_autorisés(profil)` → Outils MCP accessibles

**Matrice** :
| Profil | Colonnes masquées | Outils RAG + SQL |
|--------|--|--|
| support | prix_achat_ht, marge_pct, marge_ht | search_docs, answer_question, check_stock, order_status |
| commercial | (aucune) | tous RAG + SQL |
| dev | (aucune) | tous |
| admin | (aucune) | tous + logs |

---

### gouvernance/audit.py — Phase 4 : Journalisation

**Rôle** : Logger toute interaction (qui, quoi, résultat).

**Log structure** :
```json
{
  "timestamp": "2026-09-03T14:35:00Z",
  "profil": "support",
  "action": "answer_question|search_docs|ask_database|...",
  "question": "REF-1024 compatible 220V ?",
  "statut": "succès|erreur_validation|hors_corpus",
  "autorité": true,
  "temps_ms": 127,
  "nb_résultats": 2
}
```

**Implémentation** : Append audit.jsonl pour chaque action (succès ou refus).

---

### mcp_server/server.py — Phase 5 : Exposition outils

**Rôle** : Exposer 8 outils MCP protégés par gouvernance.

**4 outils RAG** :
- `answer_question(q, profile)` → réponse + citations
- `search_docs(q, profile)` → top-K chunks
- `get_document(ref, version, profile)` → document complet
- `list_sources(profile)` → métadonnées corpus

**4 outils SQL** :
- `ask_database(q, profile)` → résultat requête
- `get_schema(profile)` → schéma filtré
- `check_stock(ref, profile)` → stock par ref
- `order_status(cmd_id, profile)` → statut commande

**Middleware gouvernance** :
```
Chaque outil :
  1. Valider profil (extraire de contexte MCP)
  2. Vérifier outil autorisé (Perimetre)
  3. Exécuter si OK, sinon erreur 403
  4. Logger audit (succès ou refus)
  5. Retourner JSON
```

---

### streamlit_app.py — Phase 6 : Frontend

**Rôle** : Interface utilisateur pour interroger système.

**Structure** :
- **Sélecteur profil** (radio : support, commercial, dev, admin)
- **Onglet 1 : RAG**
  - Recherche docs (search_docs)
  - Génération réponse (answer_question)
  - Consultation doc complet (get_document)
- **Onglet 2 : SQL**
  - Question naturelle → Requête
  - Schéma consultatif (bouton toggle)
  - Exécution (ask_database)
  - Cas spéciaux (check_stock, order_status)
- **Onglet 3 : Audit**
  - Logs filtrable (date, profil, action)
  - Tableau + détail par clic

**Intégration** : Client MCP Python vers serveur Phase 5.

---

## Flux exemple : "REF-1024 compatible 220V ?"

```
1. Utilisateur → Streamlit (profil=support, question)
   ↓
2. MCP Server : answer_question(q, profile="support")
   ├─ Auth ✓
   ├─ Périmètre ✓ (outil autorisé)
   ↓
3. retrieval.hybrid_search(q) → [chunk_42, chunk_7, chunk_19, ...]  (top-10)
   ↓
4. generation.rerank_and_filter(chunks, profile)
   ├─ Cross-encoder score
   ├─ Perimetre masque sensible
   ├─ Check refus (meilleur score >= seuil) ✓
   ↓
5. generation.prompt_and_generate(q, chunks)
   ├─ LLM : "La REF-1024 supporte 220-240V..."
   ├─ Citations = métadonnées chunks
   ↓
6. audit.log("answer_question", profil="support", statut="succès")
   ↓
7. Retour JSON : {statut, réponse, confiance, sources}
   ↓
8. Streamlit affiche réponse + sources + pas de prix_achat (masqué support)
```

## Prochaines étapes

- **Phase 3 Tasks 2-6** : Lexique sensible → Composition SQL
- **Phase 4** : Gouvernance et audit complets
- **Phase 5** : Serveur MCP + CLI client
- **Phase 6** : Interface Streamlit (EN COURS)
