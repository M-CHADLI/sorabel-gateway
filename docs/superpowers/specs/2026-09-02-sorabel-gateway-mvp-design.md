# Sorabel Data Gateway — MVP complet (RAG + SQL + gouvernance + serveur MCP + front de test)

Date : 2026-09-02
Statut : validé par l'utilisateur, prêt pour plan d'implémentation.

## 0. Contexte et objectif de cette itération

Le dépôt contient une conception aboutie des trois chantiers (`docs/conception_rag.md`,
`docs/conception_sql.md`, `docs/conception_mcp.md`) et une implémentation partielle du
chantier 1 (`sorabel_rag/` : extraction, chunking, index, recherche hybride — non testée sur
les données réelles, jamais exécutée). Rien d'autre n'existe : pas de génération de réponse
RAG, pas de Text-to-SQL, pas de gouvernance, pas de serveur MCP, aucun commit git.

Cette itération construit le système complet — les trois chantiers et un serveur MCP réel —
plus un front Streamlit qui sert de **client de test** pour valider chaque brique
indépendamment pendant le développement. Elle ne couvre pas : l'authentification OAuth réelle
(le profil reste déclaré par l'appelant, limite documentée dans `conception_mcp.md`), la
rotation des journaux, le déploiement.

## 1. Décisions actées pendant le brainstorming

- **LLM de génération** (RAG et SQL) : Azure AI Foundry, déploiement **GPT-5.4-mini**, appelé
  via un client partagé `sorabel_llm/client.py`. Clé et endpoint dans `.env` (jamais committé).
- **Matrice d'accès complète**, 4 profils (`support`, `commercial`, `dev`, `admin`), conforme à
  `docs/conception_mcp.md` §2 : stockage `gouvernance/gouvernance.db`, validation Pydantic au
  démarrage, objet `Perimetre` propagé au retrieval et au SQL.
- **Vrai serveur MCP** (transport stdio, SDK `mcp`), pas un raccourci par appels Python directs.
- **L'extracteur de notes doit être modifié** pour produire `sous_type` et
  `diffusion_restreinte` — sans quoi les collections `notes_operationnelles` /
  `notes_confidentielles` ne sont pas séparables et E5 ne peut pas s'appliquer au RAG.
- Le front Streamlit est un **client MCP** (comme `scripts/mcp_client.py`), pas un accès direct
  aux fonctions Python — il doit démontrer le système réel, profil compris.

## 2. Architecture cible

```
sorabel_llm/
  client.py            AzureOpenAI, lit AZURE_OPENAI_ENDPOINT / _API_KEY / _DEPLOYMENT
                        depuis .env (python-dotenv). Une fonction completer(messages) -> str.

sorabel_rag/            (existant, à valider puis étendre)
  extraction.py          MODIFIÉ : ajoute sous_type + diffusion_restreinte pour les notes
  chunking.py            MODIFIÉ : propage ces deux champs dans les métadonnées de chunk
  index.py                (inchangé)
  recherche.py            MODIFIÉ : rechercher() accepte des collections autorisées, les
                          ajoute au filtre Chroma existant (pas de post-filtrage)
  generation.py           NOUVEAU : repondre(question, collections_autorisees, k=5) -> dict
                          - seuil de refus AVANT génération (E1, sans appel LLM)
                          - citations reconstruites en code depuis les métadonnées des chunks
                            réellement utilisés (titre, référence, date) — jamais demandées au LLM

sorabel_sql/             NOUVEAU (chantier 2)
  schema.py               schéma commenté + valeurs types, filtré par Perimetre
  lexique_sensible.py      détection d'intention sensible avant génération
  generation.py            generer_sql(question, perimetre) -> str | refus, few-shot
  validation.py            4 barrières : 1 instruction, SELECT/WITH, mots-clés interdits,
                          tables/colonnes ⊆ perimetre
  execution.py             connexion sqlite mode=ro, LIMIT par défaut, timeout
  tools.py                 ask_database, get_schema, check_stock, order_status

gouvernance/              NOUVEAU (chantier 3, partie données)
  schema.sql               profils, tools, collections, profil_tool, profil_collection,
                          profil_table, colonne_interdite, identites (cf. conception_mcp §2)
  seed.py                  peuple gouvernance.db avec les matrices exactes du document de
                          conception (4 profils × 8 tools × 5 collections × 5 tables)
  modeles.py               Pydantic : CodeTool/CodeCollection/TableSql (Literal),
                          DroitsProfil (validateur E5 bloquant), MatriceAcces
  perimetre.py             classe Perimetre (peut_appeler, collections_autorisees,
                          tables_autorisees, colonnes_interdites, schema_pour_prompt)
  journal.py               journaliser(...) -> écrit une ligne JSON dans logs/appels.jsonl

mcp_server/               NOUVEAU (chantier 3, partie protocole)
  serveur.py               serveur MCP stdio (SDK officiel `mcp`) ; au démarrage : charge et
                          valide la matrice (Pydantic) ; résoud le profil via
                          SORABEL_PROFIL ; filtre tools/list par profil ; journalise chaque
                          appel (autorisé ou refusé)
  tools/
    answer_question.py, search_docs.py, get_document.py, list_sources.py,
    ask_database.py, get_schema.py, check_stock.py, order_status.py
    — chacun reçoit (arguments, perimetre) et retourne un dict avec `statut`

scripts/
  mcp_client.py            NOUVEAU : client CLI unique --profil {support,commercial,dev,admin},
                          rejoue la séquence de démonstration de conception_mcp.md §6
  ingerer.py / indexer.py  (existants, réutilisés tels quels après modif extracteur)

front/
  app.py                   NOUVEAU : Streamlit, client MCP (SDK mcp), relance le serveur en
                          sous-processus stdio au changement de profil (sélecteur en barre
                          latérale), un onglet par tool + un onglet "Extraction/Chunking"
                          qui appelle directement sorabel_rag (lecture seule, pas de risque
                          de contournement de la matrice) pour l'inspection bas niveau

.env                      AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT
                          — ajouté à .gitignore
logs/appels.jsonl          journal d'appels, ajout seul
```

## 3. Flux de données

### RAG — `answer_question`
```
question, profil
  → Perimetre.collections_autorisees()
  → rechercher(question, config="hybride_rerank", collections=...)
  → meilleur score < SEUIL_REFUS ? → statut: hors_corpus (aucun appel LLM)
  → sinon : prompt construit à partir des chunks → sorabel_llm.completer()
  → citations reconstruites depuis les métadonnées des chunks utilisés
  → { statut: ok, reponse, sources: [...] }
```

### SQL — `ask_database`
Reprend exactement le schéma §6 de `docs/conception_sql.md` (intention sensible → schéma
filtré par `Perimetre` → génération → 4 barrières de validation → LIMIT → exécution ro sous
timeout), avec `perimetre.tables_autorisees()` / `colonnes_interdites()` remplaçant les règles
en dur.

### Appel de tool, bout en bout
```
client (mcp_client.py ou front/app.py)
  → serveur MCP stdio, profil résolu depuis SORABEL_PROFIL
  → intercepteur d'entrée : perimetre.peut_appeler(tool) ? sinon statut: non_autorise (journalisé)
  → tool exécuté avec perimetre → statut ok/hors_corpus/hors_schema/ambigu/non_autorise/refuse_ecriture
  → journal.journaliser(...) — toujours, autorisé ou refusé
  → retour au client
```

## 4. Gestion des erreurs

Aucune exception de protocole pour un refus métier. Statuts normalisés :
`ok`, `hors_corpus`, `hors_schema`, `ambigu`, `non_autorise`, `refuse_ecriture`, `erreur`
(cette dernière réservée aux pannes techniques réelles : base injoignable, index corrompu).
Chaque refus porte `code` + `message` + (si pertinent) `alternative`, conforme à
`docs/conception_mcp.md` §4.

## 5. Plan de tests (validation manuelle, pas de suite automatisée dans cette itération)

1. **Extraction/chunking** : `python scripts/ingerer.py --forcer` sur le corpus réel, vérifier
   le rapport qualité (`_rapport.md`) et que les notes portent `sous_type` +
   `diffusion_restreinte`.
2. **Index** : `python scripts/indexer.py`, vérifier le compte de chunks et les dimensions.
3. **Recherche** : quelques questions de `eval/questions_rag.jsonl` en CLI, comparer
   `dense`/`hybride`/`hybride_rerank`.
4. **Génération RAG** : une question dans le corpus (statut `ok` + citations), une hors corpus
   (statut `hors_corpus`, zéro appel LLM vérifiable par absence de coût/latence LLM).
5. **SQL** : `combien de commandes en avril ?` (support et commercial → 27 tous les deux),
   `quelle est la marge sur REF-1024 ?` (support → `non_autorise`, commercial → `ok`).
6. **Gouvernance** : test que Pydantic **refuse de démarrer** si on retire l'exclusion de
   `marge_pct` pour `support` dans `gouvernance/seed.py` (vérifie que le validateur E5 est
   réellement bloquant).
7. **Serveur MCP** : `scripts/mcp_client.py --profil support` puis `--profil commercial`,
   comparer aux 6 lignes de `conception_mcp.md` §6, puis lire `logs/appels.jsonl`.
8. **Front Streamlit** : une fois 1-7 validés en CLI, brancher chaque onglet et rejouer les
   mêmes cas visuellement.

## 6. Hors périmètre (explicite)

- Authentification OAuth réelle (le profil reste déclaré par l'appelant : `SORABEL_PROFIL`).
- Rotation/purge de `logs/appels.jsonl`.
- Transport HTTP du serveur MCP (stdio uniquement).
- Suite de tests automatisée (pytest) — validation manuelle uniquement pour cette itération.
- Calibration fine du seuil de refus RAG sur `eval/questions_rag.jsonl` (E6) et mesure
  formelle du gain hybride — le seuil provisoire `SEUIL_REFUS = 1e-4` du code existant est
  conservé tel quel.
