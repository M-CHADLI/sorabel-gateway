# Sorabel Data Gateway — dossier technique

Point d'entrée unique pour reprendre le code. Ce fichier décrit **ce qui est en place**, où
ça vit et quels contrats lient les paquets entre eux. Les décisions de conception et leurs
alternatives écartées restent dans `docs/conception.md` ; le cahier des charges dans
`BRIEF.md`.

État au 10 septembre 2026 : chantiers RAG, Text-to-SQL, gouvernance, serveur MCP et front
livrés, puis mis en état de production sur GCP (transport HTTP, authentification OAuth 2.1,
identités Firestore, Docker, CI/CD — chantier `gcp-vitrine`, voir §14) — **453 tests** au
vert. La vitrine a depuis été **provisionnée et vérifiée sur un projet GCP réel**
(`sorabel-vitrine-2026`) : les deux services tournent, le parcours de démonstration complet
fonctionne derrière IAP, et un client MCP tiers authentifié par OAuth Google obtient
effectivement les 8 tools (`scripts/mcp_client_oauth.py`) — voir `docs/EXPLOITATION.md` pour
le détail des correctifs qu'un déploiement réel a révélés. L'évaluation E6 n'est pas écrite
(§11).

---

## 1. Le grand schéma

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  CLIENTS                                                                     │
│  front/app_client.py (Streamlit, via front/passerelle.py en HTTP)            │
│  scripts/mcp_client.py (CLI, stdio)   client MCP tiers (OIDC)   IDE, bots    │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │  stdio (dev)  ou  HTTP streamable (prod)
                                │  SORABEL_TRANSPORT choisit le mode
┌───────────────────────────────▼──────────────────────────────────────────────┐
│  mcp_server/serveur.py                                                       │
│    stdio : resoudre_profil_stdio()  SORABEL_PROFIL, profil figé au           │
│            démarrage (développement, tests, scripts/mcp_client.py)           │
│    http  : VerificateurJeton (Resource Server OAuth 2.1 ; IAP +              │
│            Identity Platform), puis resoudre_profil_http() : lit le          │
│            profil dans le dépôt d'identités, À CHAQUE REQUÊTE, depuis        │
│            le sujet du jeton vérifié                                         │
│    charger_matrice()  valide la matrice AVANT d'exposer quoi que ce soit     │
│                                                                              │
│  mcp_server/tools.py                                                         │
│    enregistrer_tools()  enregistre TOUJOURS les 8 tools, quel que            │
│                         soit le transport ou le profil appelant              │
│    @_gouverne  point de passage unique : résout le Perimetre,                │
│                vérifie le droit, journalise — À CHAQUE APPEL, refus          │
│                compris. C'est désormais lui l'intercepteur d'entrée,         │
│                plus tools/list.                                              │
└──────┬─────────────────────────────────────────────┬─────────────────────────┘
       │ 4 tools documentaires                       │ 4 tools données
┌──────▼───────────────────────────────┐  ┌──────────▼─────────────────────────┐
│  sorabel_rag                         │  │  sorabel_sql                       │
│                                      │  │                                    │
│  ingestion → canonique JSON          │  │  schema.py      schéma filtré      │
│  chunking  → chunks par section      │  │  generation.py  question → SQL     │
│  index     → Chroma + BM25           │  │  validation.py  barrières 2 et 3   │
│  recherche → RRF + rerank LLM        │  │  execution.py   barrières 1 et 4   │
│  generation→ réponse + citations     │  │  tools.py       routage des statuts│
│  documents → get_document/list       │  │                                    │
└──────┬─────────────────┬─────────────┘  └──────────┬─────────────────────────┘
       │                 │                           │
┌──────▼──────┐  ┌───────▼────────┐  ┌───────────────▼──────┐  ┌───────────────┐
│ data/chroma │  │ sorabel_llm    │  │ data/sorabel.db      │  │ gouvernance   │
│  + bm25.pkl │  │  Azure Foundry │  │  SQLite, mode=ro     │  │  .db + journal│
│ 400 docs    │  │  embeddings,   │  │  5 tables            │  │  logs/*.jsonl │
│             │  │  génération,   │  │                      │  │               │
│             │  │  reranking     │  │                      │  │               │
└─────────────┘  └────────────────┘  └──────────────────────┘  └───────────────┘
```

Deux principes qui expliquent la forme du reste :

- **Le périmètre est résolu par requête, pas au démarrage.** En stdio (développement, tests,
  `scripts/mcp_client.py`), `SORABEL_PROFIL` fige un profil pour toute la durée du processus —
  le comportement historique subsiste, inchangé, pour cet usage local. En HTTP (production),
  un même processus sert tous les profils : les 8 tools sont donc **toujours** enregistrés, et
  c'est le décorateur `_gouverne` (`mcp_server/tools.py`) qui résout le `Perimetre` à chaque
  appel — depuis le sujet du jeton vérifié par `VerificateurJeton` — vérifie le droit et
  journalise, refus compris. `tools/list` filtré n'est donc plus l'intercepteur d'entrée : il
  renvoie les mêmes 8 tools à tout appelant HTTP, autorisé ou non.
- **Le front n'applique aucune règle d'accès.** Il affiche ce que le serveur lui a laissé
  voir : `front/depot.py::tools_accordes()` lit la matrice directement (plus jamais
  `tools/list`, qui ne dit plus rien de ce qu'un profil peut appeler depuis que le contrôle
  est descendu dans le décorateur). Toute la gouvernance reste côté serveur.

---

## 2. Arborescence

```
sorabel_rag/         chaîne documentaire
  modeles.py         DocumentCanonique, Section, Qualite, hachage, tri de versions
  extraction.py      PDF (pypdf) · Markdown+YAML · HTML (bs4) → DocumentCanonique
  ingestion.py       parcours du corpus, cache par hash, manifeste, rapport qualité
  chunking.py        découpe par section, fusion des courtes (100–500 tokens)
  index.py           embeddings Foundry + Chroma, BM25 pickle, tokenisation
  recherche.py       dense + BM25 → RRF → rerank LLM → seuil de refus
  generation.py      prompt, appel LLM, citations construites par le code
  documents.py       get_document / list_sources, filtrage par collection

sorabel_sql/         chaîne données, lecture seule
  schema.py          schéma commenté, amputé des colonnes hors périmètre
  generation.py      question → SQL (LLM), garde-fou question sensible
  validation.py      barrières 2 et 3 : forme SQL, tables, colonnes, SELECT *
  execution.py       barrières 1 et 4 : connexion ro, LIMIT 200, timeout 5 s
  tools.py           ask_database, get_schema, check_stock, order_status
  lexique_sensible.py  vocabulaire déclencheur du garde-fou

sorabel_enseigne/    une enseigne par processus, sans dépendance vers le reste du projet
  __init__.py        enseigne_active(), enseigne(nom), enseignes_disponibles(),
                     charger_enseigne(chemin)
  __main__.py        python -m sorabel_enseigne liste | make <nom> (variables du Makefile)

enseignes/
  sorabel/enseigne.toml  chemins historiques (data/, gouvernance/, logs/), prompts,
                     pied de page PDF, vocabulaire du schéma SQL

sorabel_llm/
  client.py          client unique Azure AI Foundry (API v1), completer()

gouvernance/
  schema.sql         profils, tools, collections, tables, colonnes interdites
  seed.py            peuple gouvernance.db — la matrice est ici, en clair
  modeles.py         validation Pydantic de la matrice (E5 bloquante)
  perimetre.py       Perimetre : les droits sous la forme que les tools consomment
  journal.py         journaliser() → logs/appels.jsonl, ou stdout si SORABEL_JOURNAL=stdout
  identites.py       DepotIdentitesSqlite : sujet → profil, développement et tests
  identites_firestore.py  DepotIdentitesFirestore : sujet → profil, production
  depots.py          choisir_depot() : SQLite ou Firestore selon SORABEL_DEPOT — point de
                     passage unique partagé par mcp_server/serveur.py et front/depot.py

mcp_server/
  serveur.py         construction du serveur ; résolution du profil (stdio au démarrage,
                     HTTP par requête) ; run stdio ou HTTP streamable selon SORABEL_TRANSPORT
  tools.py           enregistrement inconditionnel des 8 tools ; décorateur `_gouverne` :
                     résolution du périmètre, contrôle et journalisation à chaque appel
  authentification.py  VerificateurJeton : Resource Server OAuth 2.1, IAP + Google Identity
                     Platform, audience vérifiée par émetteur (transport HTTP uniquement)

front/
  app_client.py      poste de travail (navigation 2 niveaux, 8 écrans, choix d'enseigne si
                     plusieurs sont servies, inscription et changement de profil de démonstration)
  couleurs.py        palette dérivée de la couleur d'accent d'une enseigne (stdlib seule)
  routage.py         quel serveur MCP répond pour une enseigne : HTTP via passerelle.py
                     (production), ou stdio via mcp_client.py en mode local (SORABEL_FRONT_LOCAL=1)
  passerelle.py      pont HTTP vers le serveur MCP déployé : relaie l'assertion IAP sans la
                     vérifier, traduit les pannes de transport en `{"statut": "erreur"}`
  depot.py           choix du dépôt d'identités (via gouvernance.depots) et calcul des tools
                     accordés à un profil, lus directement dans la matrice
  mcp_client.py      pont stdio : un serveur MCP par (profil, enseigne), utilisé par le mode local

scripts/
  ingerer.py         corpus → data/canonique/*.json
  indexer.py         canoniques → Chroma + BM25
  seed_gouvernance.py  (re)construit gouvernance.db
  mcp_client.py       client CLI, un appel de tool par exécution, stdio
  mcp_client_oauth.py client MCP tiers authentifié par un vrai flux OAuth Google — preuve
                     du Resource Server contre un serveur déployé, voir §14 et EXPLOITATION.md
  demo_mcp_http.py    serveur MCP HTTP de démonstration SANS authentification — hors
                     périmètre de production, voir §14

tests/               50 fichiers, 453 tests
data/                corpus, sorabel.db, canonique/, chroma/  (hors git)
logs/appels.jsonl    journal d'appels en stdio (hors git) ; en HTTP, voir SORABEL_JOURNAL
```

---

## 3. Contrats entre paquets

Les quatre interfaces à ne pas casser.

### `Perimetre` — duck-typé, volontairement

`sorabel_sql` et `sorabel_rag` n'importent **rien** de `gouvernance`. Ils reçoivent un objet
qui répond à quatre méthodes :

```python
perimetre.peut_appeler(tool: str) -> bool
perimetre.collections_autorisees() -> frozenset[str]
perimetre.tables_autorisees() -> frozenset[str]
perimetre.colonnes_interdites(table: str) -> frozenset[str]
```

Les tests fabriquent des périmètres factices avec ces quatre méthodes, sans base de données.
Toute méthode ajoutée ici doit l'être aux doublures de test.

### `sorabel_enseigne` — une enseigne par processus

Le moteur lit ses chemins et ses textes métier dans `enseigne_active()`, jamais en dur :

```python
enseigne_active() -> Enseigne        # SORABEL_ENSEIGNE, « sorabel » par défaut
enseigne(nom: str) -> Enseigne       # par nom, en cache — pour le front mutualisé
enseignes_disponibles() -> list[str]
```

`Enseigne.chemins` porte `corpus`, `canonique`, `chroma`, `base_sql`, `gouvernance`,
`journal` ; `Enseigne` porte aussi `collection`, `presentation`, `pied_de_page`, `nom_base`,
`commentaires_sql`, `libelles_types` (libellé affiché pour chaque type de document, table
`[rag.libelles_types]` facultative : « Guide d'entretien » pour Kiabi, « Notice
d'installation » par défaut ; ils entrent dans le texte embeddé, donc **les changer impose de
réindexer**) et `front` (textes et couleurs du poste de travail, table `[front]` facultative —
voir §9). Les constantes de module (`CORPUS`, `CHEMIN_DB`, `PROMPT_SYSTEME`…)
gardent leur nom mais sont évaluées à l'import depuis l'enseigne active : changer
d'enseigne, c'est changer de processus. Une enseigne inconnue lève `ValueError` à l'import —
jamais de repli silencieux sur Sorabel ; `enseigne_active()` fige l'enseigne à son premier
appel, et tout changement de `SORABEL_ENSEIGNE` en cours de processus lève `ValueError`
(un `.env` chargé après les imports ne doit pas produire un processus mi-une, mi-l'autre
enseigne).

`Enseigne.seuil_refus` est optionnel : `None` (Sorabel) garde le `SEUIL_REFUS` du moteur.
`generation.SEUIL_REFUS_ENSEIGNE` porte le seuil de l'enseigne active, figé à l'import.
Kiabi déclare 0.75, mesuré dans `docs/calibrage-kiabi.md`. Une enseigne qui déclare son
seuil le lit sur la **meilleure note brute** des résultats (`generation.score_de_decision`) ;
Sorabel garde la lecture du premier résultat : le tri place en tête le document dont la
référence est citée, même moins bien noté, ce qui refusait à tort les questions mixtes
« référence + langage naturel ».

### Forme de retour des tools

Tout tool renvoie un `dict` avec une clé `statut`. Un refus **est un retour normal**, jamais
une exception : un client doit pouvoir distinguer « pas de réponse » de « panne ».

| `statut` | Sens | Émis par |
|---|---|---|
| `ok` | Résultat exploitable | tous |
| `hors_corpus` | Rien d'assez pertinent dans le corpus (E1) | `answer_question` |
| `hors_schema` | Aucune table ne correspond, ou format d'identifiant invalide | tools SQL, `get_document` |
| `non_autorise` | Table, colonne ou collection hors périmètre (E5) | tools SQL, `get_document` |
| `refuse_ecriture` | SQL non-lecture, ou multi-instruction (E3) | `ask_database` |

Les tools SQL renvoient en plus `sql` (la requête **exécutée ou rejetée** — E3 exige qu'elle
soit toujours visible), `colonnes`, `lignes`, `n_lignes`, `tronque`.

### `sorabel_llm.completer`

Un seul point d'appel LLM pour la génération RAG, la génération SQL et le reranking. Bascule
de modèle ou de fournisseur : ce fichier seul.

---

## 4. Les 8 tools

| Tool | Arguments | Renvoie | Implémenté dans |
|---|---|---|---|
| `answer_question` | `question` | `reponse`, `citations[]` | `sorabel_rag/generation.repondre` |
| `search_docs` | `requete`, `k=5`, `type_document` | `resultats[]` (`chunk_id`, `texte`, `score`, `titre`, `reference`) | `sorabel_rag/recherche.rechercher` |
| `get_document` | `doc_id` **ou** `reference` (+ `version`) | `document` (`sections[]`, `references_citees`, …) | `sorabel_rag/documents.obtenir_document` |
| `list_sources` | `type_document` | `sources[]` (`versions`, `version_courante`) | `sorabel_rag/documents.lister_sources` |
| `ask_database` | `question` | `sql`, `colonnes`, `lignes`, `n_lignes`, `tronque` | `sorabel_sql/tools.ask_database` |
| `get_schema` | — | `schema` (DDL commentée, filtrée) | `sorabel_sql/schema.schema_commente` |
| `check_stock` | `ref` (`REF-XXXX`) | lignes par entrepôt + `sous_seuil_reappro` | `sorabel_sql/tools.check_stock` |
| `order_status` | `order_id` (`CMD-AAAA-NNNN`) | statut, date, montant | `sorabel_sql/tools.order_status` |

`check_stock` et `order_status` n'appellent **aucun LLM** : SQL paramétré en dur. C'est
voulu — une question à réponse déterministe ne doit pas dépendre d'une génération.

Les docstrings des tools sont l'unique documentation qu'un client LLM verra : elles disent
explicitement quand **ne pas** utiliser un tool (« n'utilisez pas `answer_question` pour des
extraits bruts : voyez `search_docs` »). Les modifier, c'est modifier le comportement des
clients.

---

## 5. Chaîne RAG

```
data/corpus/{fiches,notices,notes,sav}
        │  extraction.py — la référence et la version viennent du NOM DE FICHIER
        │                   pour les 230 PDF, jamais du contenu
        ▼
DocumentCanonique  ──►  data/canonique/*.json  + _manifeste.json
        │  (cache par hash de fichier : réingérer ne recalcule que ce qui a changé)
        ▼
chunking.py — découpe par section structurelle, fusion des sections courtes
              100 à 500 tokens ; en-tête (titre + référence + type) préfixée au texte
        ▼
   ┌────────────────────┬────────────────────┐
   │ Chroma (dense)     │ BM25 (lexical)     │   deux index séparés, volontairement :
   │ text-embedding-    │ rank_bm25, pickle  │   un modèle unique rendrait impossible
   │ 3-small, 1536 dim  │ « ref-8842 » reste │   de mesurer l'apport de chacun (E6)
   │ cosinus, lots 128  │ UN token           │
   └─────────┬──────────┴──────────┬─────────┘
             │  30 candidats       │  30 candidats
             └──────────┬──────────┘
                        ▼
              fusion RRF (k = 60)
              + bonus référence détectée dans la question
                        ▼
              rerank LLM listwise (barème 1.0 / 0.5 / 0.0)
              3 tentatives, puis RerankIndisponible — une panne technique
              ne doit JAMAIS se présenter comme un « hors_corpus »
                        ▼
              meilleur score < seuil de l'enseigne (SEUIL_REFUS = 0.3 par défaut) ?
                 oui → {"statut": "hors_corpus"}   ← aucun appel de génération
                 non → génération + citations
```

**Trois points structurants :**

1. **Les citations sont construites par le code**, depuis les métadonnées des chunks
   réellement passés au prompt. Le prompt système interdit au LLM de citer lui-même. Un
   modèle qui hallucine une source ne peut donc pas en fabriquer une.
2. **Le refus est déterministe et antérieur à la génération.** Sous le seuil, aucun token
   n'est dépensé.
3. **Le périmètre s'applique DANS le retrieval**, pas en post-filtrage : une note
   confidentielle hors périmètre n'entre jamais dans les candidats, donc ne peut pas
   influencer un score ni fuiter par une reformulation.

Le corpus contient plusieurs versions d'un même document. **Tout est indexé** ; la version
courante est marquée (`est_version_courante`) et la recherche filtre dessus par défaut
(`inclure_versions_anciennes=False`). Pour le SAV, la clé de regroupement est la famille de
procédure, pas le fichier.

---

## 6. Chaîne Text-to-SQL — les 4 barrières

```
question ──► generation.generer(question, perimetre)
             │
             ├─ garde-fou : question sensible ET profil restreint sur le sensible
             │              → QuestionSensible, AVANT tout appel LLM
             │              (un profil non restreint passe : le commercial a droit
             │               aux marges, la matrice fait foi)
             ├─ hors schéma → None → statut hors_schema
             ▼
        SQL candidat
             │
   ╔═════════▼═══════════════════════════════════════════════════════╗
   ║ BARRIÈRE 2 — validation.valider() : forme                       ║
   ║   une seule instruction · commence par SELECT ou WITH           ║
   ║   liste blanche, pas liste noire seule                          ║
   ║   aucun mot-clé d'écriture (insert, drop, pragma, attach…)      ║
   ╠═════════════════════════════════════════════════════════════════╣
   ║ BARRIÈRE 3 — validation.valider() : périmètre                   ║
   ║   tables existantes · tables autorisées (CTE exclues)           ║
   ║   colonnes interdites absentes                                  ║
   ║   SELECT * / t.* refusé si une table citée a des colonnes       ║
   ║   interdites  ← sans quoi E5 tombe par le joker                 ║
   ╠═════════════════════════════════════════════════════════════════╣
   ║ BARRIÈRE 1 — execution.executer() : SQLite mode=ro              ║
   ║   la seule infranchissable : appliquée par SQLite, pas par nous ║
   ╠═════════════════════════════════════════════════════════════════╣
   ║ BARRIÈRE 4 — execution.executer() : volume et temps             ║
   ║   LIMIT 200 ajouté si absent · timeout 5 s par progress_handler ║
   ╚═════════════════════════════════════════════════════════════════╝
             ▼
     {"statut": "ok", "sql": …, "colonnes": …, "lignes": …, "tronque": …}
```

Aucune barrière n'est suffisante seule, et c'est le point : la connexion `mode=ro` empêche
l'écriture mais pas la lecture d'une colonne interdite ; la validation attrape la colonne
mais peut être contournée par un `SELECT *` ; le `LIMIT` ne protège que du volume.

**Le piège `SELECT *` a été une vraie faille**, corrigée : `_contient_selection_generique()`
distingue le joker (`*` suivi d'une virgule, de `FROM` ou de la fin) de `COUNT(*)` (précédé
d'une parenthèse) et de la multiplication (`quantite * prix`). Toute évolution de cette
fonction doit garder les trois cas couverts — `tests/test_sql_validation.py` les vérifie.

---

## 7. Gouvernance

**La matrice vit dans `gouvernance/seed.py`**, en clair, et est semée dans `gouvernance.db`.
État actuel :

| Profil | Tools | Collections | Colonnes interdites |
|---|---|---|---|
| `support` | 8 | fiches, notices, sav, notes_operationnelles | `produits.prix_achat_ht`, `produits.marge_pct`, `ventes.marge_ht` |
| `commercial` | 8 | toutes, y compris notes_confidentielles | — |
| `admin` | 8 | toutes | — |
| `dev` | 4 (`search_docs`, `get_document`, `list_sources`, `get_schema`) | fiches, notices, sav | les trois colonnes sensibles |

Le profil `dev` est le contraste le plus lisible pour une démonstration : il peut chercher et
lire des documents, mais ni générer une réponse ni interroger la base.

**Trois niveaux d'application :**

1. **Au chargement** — `gouvernance/modeles.py` valide la matrice avec Pydantic. Un code de
   tool inconnu (faute de frappe en base) fait échouer le **démarrage**, jamais l'appel. Et
   un validateur rend **E5 bloquante** : si un profil restreint voit une table sensible sans
   exclure les colonnes qui vont avec, le chargement lève. L'invariant est vérifié, pas
   espéré.
2. **À la résolution du profil** — dépend du transport. En stdio, `SORABEL_PROFIL` fige le
   profil au démarrage, comme avant. En HTTP, `authentification.VerificateurJeton` valide le
   jeton (signature, émetteur, audience, expiration) puis `resoudre_profil_http()` interroge
   le **dépôt d'identités** — `gouvernance/identites.py` (SQLite, développement) ou
   `gouvernance/identites_firestore.py` (Firestore, production), choisi par
   `gouvernance/depots.py::choisir_depot()` selon `SORABEL_DEPOT` — pour obtenir le profil
   associé au sujet du jeton. Un sujet authentifié mais inconnu du dépôt n'obtient **aucun**
   profil par défaut (fail-closed) : c'est au front de proposer l'inscription, jamais au
   serveur d'en attribuer un. `DepotIdentitesFirestore` ajoute une garantie : construit sans
   `profils_valides`, il refuserait tout, pas l'inverse.
3. **À chaque appel de tool** — le décorateur `_gouverne` (`mcp_server/tools.py`) résout le
   `Perimetre` (via le résolveur ci-dessus), vérifie `peut_appeler()` et journalise, refus
   compris — c'est le point de passage unique, appelé sur les 8 tools qui sont désormais
   **toujours** enregistrés. À l'intérieur des fonctions métier, ce même `Perimetre` filtre
   encore collections, tables et colonnes.

**Journal** — `logs/appels.jsonl` par défaut, ou la sortie standard (Cloud Logging) si
`SORABEL_JOURNAL=stdout` (`gouvernance/journal.py`) ; une ligne JSON par appel dans les deux
cas. Le décorateur `_gouverne` est le point de passage unique : durée, statut, entrées, SQL,
nombre de lignes, motif, et **`autorise` : un refus est journalisé au même titre qu'un appel
abouti**, avec `autorise=False`. On trace **la question et la requête, jamais le contenu des
résultats** : un journal ne doit pas devenir une copie de la base sans les contrôles d'accès
de la base.

---

## 8. Les données

**Corpus** — `data/corpus/` (attention au double niveau `data/data/` selon la copie utilisée).

| Dossier | Volume | Format | Métadonnées |
|---|---|---|---|
| `fiches/` | 150 | PDF | nom de fichier `REF-XXXX-vM.m.pdf` |
| `notices/` | 80 | PDF | nom de fichier `notice-REF-XXXX-vM.m.pdf` |
| `notes/` | 80 | Markdown | front-matter YAML ; la référence n'est que dans le corps |
| `sav/` | 90 | HTML | `<title>` + `<meta>` ; sections en `<h2>` |

**Base** — `data/sorabel.db`, 5 tables : `produits` (120), `stocks` (312), `clients` (60),
`commandes` (340), `ventes` (993).

`produits.ref` est **le pivot entre les deux mondes** : la même référence `REF-XXXX` porte
les chunks du corpus et les lignes de la base. C'est ce qui permet à un écran « fiche
produit » de composer stock, tarif et documentation.

`date_commande` est stockée en TEXT ISO : les agrégations temporelles passent par les
fonctions de date SQLite sur du texte.

---

## 9. Front

`front/app_client.py` — poste de travail. Navigation à deux niveaux : 4 thèmes, 8 écrans,
un écran par capacité, plus un écran d'inscription pour un sujet encore inconnu du dépôt
d'identités. Une entrée n'apparaît que si la matrice accorde le tool correspondant au profil
courant. Un bandeau « mode démonstration » rappelle explicitement qu'un visiteur choisit
lui-même son profil — ce que la production réelle ne ferait jamais.

**Plusieurs enseignes.** Le front ne détient aucune donnée : il choisit seulement *quel*
serveur MCP interroger, chaque serveur ne servant qu'une enseigne (figée par processus).
L'enseigne de la session vit dans `st.session_state["enseigne"]`.

- **Une seule enseigne servie** (la production Sorabel, dont l'image ne contient que
  `enseignes/sorabel/enseigne.toml`) : elle est choisie d'office, **aucune page de choix**,
  et le rendu est celui d'avant le multi-enseigne, à la chaîne et à la couleur près.
- **Plusieurs enseignes servies** : une page d'accueil propose une carte par enseigne
  (libellé, nom du produit, mention éventuelle), avant la page d'inscription ; la barre
  latérale porte un bouton « Changer d'enseigne ». Le profil est conservé : la matrice est
  commune à toutes les enseignes.

En HTTP, une enseigne est servie si elle est Sorabel (URL historique `SORABEL_URL_MCP`) ou si
`SORABEL_URL_MCP_<ENSEIGNE>` est définie (`SORABEL_URL_MCP_KIABI`…). Jamais de repli sur
l'URL Sorabel pour une autre enseigne : une question Kiabi partirait vers les données
Sorabel, sous l'apparence d'une réponse normale.

**Textes et couleurs par enseigne** — table facultative `[front]` de
`enseignes/<nom>/enseigne.toml`, exposée par `Enseigne.front` (mapping immuable, listes
converties en tuples). Clés : `titre_page`, `nom_produit`, `mention` (bandeau
d'avertissement, vide = aucun), `resume_corpus` (ligne « Corpus » du rappel, ex.
« 175 documents indexés »), `couleur_accent` et `couleur_fond` (`#RRGGBB`),
`references_exemple`, `questions_exemple`, `question_sql_exemple`, `commande_exemple`,
`document_exemple`. Les valeurs par défaut sont les textes Sorabel, définis une seule fois
dans `DEFAUTS_FRONT` (`front/app_client.py`, dont les clés égalent `CLES_FRONT`) ; Sorabel
ne déclare pas de table `[front]`. Une clé inconnue, un type inattendu (chaîne à la place
d'une liste, texte vide hors `mention`), un doublon dans une liste d'exemples, une liste
vide ou une couleur hors `#RRGGBB` lèvent `ValueError` au chargement, en nommant la clé :
une faute de frappe afficherait sinon les textes Sorabel dans une démonstration Kiabi, sans
la moindre erreur.

**Habillage.** `front/couleurs.py` dérive de `couleur_accent` les teintes voisines de la
feuille de style (accent foncé, voile, bordure, début de dégradé des boutons, composantes
RVB des ombres et de l'anneau de focus) ; `couleur_fond` ouvre le dégradé de la barre
latérale. Les coefficients sont calibrés pour que l'accent Sorabel redonne la feuille du tag
`sorabel-v1` à l'octet (`tests/test_front_couleurs.py`). `STYLE` ne porte donc plus aucune
teinte Sorabel en dur : des marqueurs `__ACCENT_…__` y sont remplacés par
`feuille_de_style()`.

**Mode local** (`SORABEL_FRONT_LOCAL=1`, `make front`) — démonstration sur poste, sans
Identity-Aware Proxy. Le sujet est l'identité de développement `local:developpeur`
(`front.routage.SUJET_LOCAL`), le profil se choisit à l'écran comme en démonstration, et
toutes les enseignes disponibles sont servies. Chaque appel de tool **passe toujours par un
serveur MCP** : `front/mcp_client.py` lance un serveur stdio par couple (profil, enseigne),
avec `SORABEL_PROFIL` et `SORABEL_ENSEIGNE`, qui applique la matrice et journalise comme en
production. Ce mode est **interdit sur Cloud Run** : `front.routage.mode_local()` lève
`RuntimeError` si `K_SERVICE` est définie (Cloud Run la positionne toujours) — actif en
production, il laisserait n'importe quel visiteur choisir son profil sans authentification.
Pour la même raison, le poste ne doit pas écouter sur le réseau : `make front` lance
Streamlit avec `--server.address=127.0.0.1`, et `app_client.py` affiche une erreur et
s'arrête (`st.stop()`) si, en mode local, `server.address` n'est ni `127.0.0.1`, ni
`localhost`, ni `::1` — ce qui inclut une option non posée, Streamlit écoutant alors sur
toutes les interfaces.

`front/routage.py` — le seul chemin d'appel de `app_client.py` : `appeler(enseigne, tool,
arguments, *, assertion, profil)` choisit le transport (HTTP via `front/passerelle.py` avec
l'URL de l'enseigne, ou stdio en mode local) ; une enseigne non servie, ou un serveur
local qui ne démarre pas ou meurt (« Serveur MCP local indisponible. », le détail sur la
sortie du front seulement), renvoie `{"statut": "erreur", ...}`, jamais une exception
vers l'écran. Les vues de `app_client.py`
appellent une fonction `appeler(assertion, tool, arguments)` du module, qui délègue à
`routage.appeler` avec l'enseigne et le profil de session.

`front/passerelle.py` — le pont vers le serveur MCP déployé, emprunté par `front/routage.py`
hors mode local. Identity-Aware Proxy authentifie la personne avant que la
requête n'atteigne Streamlit et dépose une assertion signée dans un en-tête ;
`assertion_iap()` la lit, `sujet_du_jeton()` en extrait le `sub` **sans vérifier la
signature** — le front n'est pas juge, c'est le serveur MCP qui valide et décide. La
passerelle recopie l'assertion telle quelle vers le serveur (`Authorization: Bearer …`) :
Streamlit ne fabrique et ne manipule jamais de secret d'identité. `_executer()` traduit les
pannes de transport (délai dépassé, connexion refusée, statut HTTP d'erreur, erreur MCP) en
`{"statut": "erreur", ...}`, jamais confondu avec `{"statut": "non_autorise", ...}`
réservé à l'absence d'identité. Avec le client MCP, une panne de transport arrive enveloppée
dans un `ExceptionGroup` : `_executer()` la traduit si le groupe en contient une, et laisse
remonter tout autre groupe (un bogue ne doit pas passer pour une panne réseau). Une URL
vide passée en paramètre ne retombe pas sur `SORABEL_URL_MCP` : seul `None` le fait.

`front/depot.py` — choisit le dépôt d'identités via `gouvernance.depots.choisir_depot()`
(mis en cache par process, `SORABEL_DEPOT` déjà résolu une fois) et calcule
`tools_accordes(profil)` **en lisant la matrice directement**, plus jamais via `tools/list` :
depuis que le périmètre est résolu par requête (§1, §7), `tools/list` renvoie les 8 tools à
tout appelant HTTP et ne dit donc plus rien de ce qu'un profil peut réellement appeler.

`front/mcp_client.py` — le pont stdio, emprunté par `front/routage.py` en mode local
(`app_client.py` ne l'importe pas directement). Les sessions sont indexées par
`(profil, enseigne)` : un serveur fige son enseigne au démarrage, changer d'enseigne à
l'écran ouvre donc un autre processus. Une session qui lève (au démarrage ou à l'appel) est
retirée du cache sous verrou et sa boucle arrêtée : « Réessayer » relance un serveur neuf
au lieu de retomber sur la session morte jusqu'au redémarrage de Streamlit. Streamlit ré-exécute le script à chaque interaction : une session MCP
ouverte dans le fil du script ne survivrait pas au clic suivant. La session y est donc tenue
par un **thread dédié avec sa propre boucle asyncio**, ouverte via une `AsyncExitStack`
conservée en attribut. Deux pièges Windows déjà payés, à ne pas réintroduire dans ce fichier :

- `WindowsProactorEventLoopPolicy` est imposée : la politique Selector ne sait pas créer de
  sous-processus, et le serveur meurt silencieusement.
- L'environnement du sous-processus **hérite** de `os.environ` (`{**os.environ, …}`). Un env
  réduit au seul `SORABEL_PROFIL` prive le processus de `SYSTEMROOT`, et Winsock ne s'initialise
  plus (`OSError: [WinError 10106]`).

Il n'existe **aucun chemin d'accès au pipeline qui contourne le serveur MCP** : tout ce que
le front affiche est passé par la matrice, via `front/routage.py` (HTTP ou stdio), et
`front/` n'importe rien de `sorabel_rag`, `sorabel_sql`, `sorabel_llm` ni `mcp_server` —
`tests/test_front_coherence.py` le vérifie par AST sur chaque `front/*.py`. Une page de debug
appelant les modules en direct a existé (`front/app.py`) et a été retirée — dans un projet
dont l'argument est la gouvernance, un contournement disponible finit par servir.

---

## 10. Faire tourner

```bash
uv sync                                   # Python 3.12 (voir .python-version)

# .env — voir .env.example pour la liste complète
#   AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT
#   AZURE_OPENAI_EMBEDDING_DEPLOYMENT
#   (AZURE_EMBEDDING_ENDPOINT / _API_KEY si l'embedding est servi à part)

python scripts/seed_gouvernance.py        # construit gouvernance.db
python scripts/ingerer.py                 # corpus → data/canonique/
python scripts/indexer.py                 # canoniques → Chroma + BM25

SORABEL_PROFIL=commercial python -m mcp_server.serveur   # serveur MCP, stdio (développement)
streamlit run front/app_client.py                        # poste de travail (derrière IAP)
SORABEL_FRONT_LOCAL=1 streamlit run front/app_client.py --server.address=127.0.0.1
                                         # poste local, sans IAP, boucle locale seulement (make front)
python scripts/mcp_client.py support answer_question '{"question": "..."}'

python -m pytest -q                       # 453 tests
```

**Poste local multi-enseigne (`make front`).** La cible construit d'abord, enseigne par
enseigne, ce qui manque des données de chaque enseigne présente dans `enseignes/`
(l'équivalent de `make donnees ENSEIGNE=<nom>` pour chacune, qui appelle Azure pour
l'indexation), puis lance Streamlit sur `127.0.0.1`. Préparer seulement Kiabi :
`make donnees ENSEIGNE=kiabi`, avant `make front`. Deux pièges :

- le profil choisi à l'écran (`local:developpeur`) vit dans `gouvernance/gouvernance.db`,
  que `make test` réinitialise (`gouvernance.seed.peupler` supprime le fichier, et
  `tests/test_front_mcp_client.py` le repeuple) : après une suite de tests, le premier
  écran redemande le profil ;
- sans index, un serveur Kiabi répondrait sans corpus : `make front` évite ce cas en
  construisant les données d'abord, mais un `streamlit run` direct, lui, ne le fait pas.

Changer `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` **impose de réindexer tout le corpus** : des
vecteurs de deux modèles ne se comparent pas. Changer le modèle de reranking impose de
recalibrer `SEUIL_REFUS` et les `seuil_refus` déclarés par les enseignes.

En transport HTTP (production), le serveur exige en plus l'authentification et le dépôt
d'identités — `SORABEL_TRANSPORT=http`, `SORABEL_OIDC_ISSUER`/`_AUDIENCE`/`_JWKS`,
`SORABEL_IAP_AUDIENCE`, `SORABEL_URL_PUBLIQUE`, `SORABEL_DEPOT=firestore` — voir `CLAUDE.md`
pour la liste complète des variables et `docs/EXPLOITATION.md` pour le provisionnement GCP et
les commandes de vérification.

---

## 11. Traçabilité des exigences

| | Exigence | Où | Vérifié par |
|---|---|---|---|
| **E1** | Refus hors corpus déterministe, citations non hallucinées | `recherche.SEUIL_REFUS`, `generation.SEUIL_REFUS_ENSEIGNE`, `generation._construire_citations` | `test_generation.py`, `test_enseigne_seuil_refus.py` |
| **E2** | RAG hybride dense + BM25 + rerank | `index.py`, `recherche.rechercher` | `test_recherche_collections.py` |
| **E3** | SQL lecture seule, barrières multiples, SQL toujours visible | `validation.py`, `execution.py` | `test_sql_validation.py`, `test_sql_execution.py` |
| **E4** | Matrice d'accès appliquée et journalisée, refus compris | `perimetre.py`, `tools.enregistrer_tools` (décorateur `_gouverne`), `authentification.py`, `journal.py` | `test_gouvernance_*.py`, `test_mcp_tools.py`, `test_mcp_authentification.py` |
| **E5** | Colonnes sensibles jamais exposées au profil restreint | validateur Pydantic, `valider()`, `schema_commente()` | `test_gouvernance_modeles.py`, `test_sql_validation.py` |
| **E6** | Gain de l'hybride mesuré et documenté | **non fait** | — |

---

## 12. Limites connues et reste à faire

Un point qu'un repreneur doit connaître, plutôt que le redécouvrir :

1. **E6 n'est pas implémentée.** `eval/questions_rag.jsonl` et `eval/questions_sql.jsonl`
   existent, `eval/run_eval.py` non. Il faut mesurer Recall@5, MRR et Hit@1 sur les trois
   configurations (`dense`, `hybride`, `hybride_rerank` — déjà prévues en paramètre de
   `rechercher()`), avec les questions **par référence exacte et en langage naturel
   rapportées séparément** : une moyenne globale masque précisément ce qu'on cherche à
   démontrer.

**Comblé pendant le chantier `gcp-vitrine`** — le point qui figurait ici avant lui :

- **Le journal trace désormais les refus.** Le décorateur `_gouverne` journalise
  `autorise=False` avant même de résoudre le `Perimetre`, et sur tout appel qui échoue à
  `peut_appeler()` — possible depuis que les 8 tools sont toujours enregistrés (§1, §7) :
  en stdio, un tool non accordé n'existait pas et son appel n'atteignait donc jamais de code
  journalisant ; ce n'est plus le cas en HTTP.

Un bug bloquant, sans rapport avec les limites listées ci-dessus, a par ailleurs été trouvé
et corrigé pendant la vérification finale du chantier (hors des tâches planifiées, découvert
en confrontant le code à la conception) : `construire_serveur()` n'appelait jamais
`choisir_depot()` malgré `SORABEL_DEPOT=firestore` — le serveur serait resté sur
l'implémentation SQLite en production, où le fichier `gouvernance.db` n'est pas accessible en
écriture, rendant l'auto-inscription du front inopérante (refus indéfini pour tout nouveau
sujet). Corrigé ; `tests/test_mcp_serveur.py` couvre désormais les deux dépôts.

**Ce que le premier provisionnement réel a révélé (2026-09-09/10)** — aucun de ces points
n'était détectable par les tests, qui tournent sans réseau ni GCP réel ; tous sont désormais
corrigés dans `cloudbuild.yaml` et documentés dans `docs/EXPLOITATION.md` :

- `deploy-mcp` et `deploy-front` tournaient sans `--async` : `gcloud run deploy` attend par
  défaut qu'une révision devienne saine avant de rendre la main, ce que `sorabel-mcp` ne peut
  pas faire au tout premier passage (son URL, nécessaire à sa propre configuration, n'existe
  qu'une fois déployé). Sans `--async`, ce premier build échouait et n'atteignait jamais
  `deploy-front`.
- L'étape `tests` de `cloudbuild.yaml` ne régénérait pas `data/canonique/` (gitignorée,
  régénérable) avant `pytest` : 14 tests qui lisent les documents canoniques
  (`get_document`, `list_sources`) échouaient sur un checkout Cloud Build frais, alors qu'ils
  passent toujours en local où ce dossier existe déjà.
- L'étape `build` n'avait pas de `set -e` : un `docker build` en échec ne faisait pas échouer
  le script (le dernier `rm` réussissait et masquait le code de sortie), donc `push` échouait
  ensuite avec un message qui ne disait rien de la cause réelle.
- `sorabel-mcp` était déployé sans `--allow-unauthenticated` : l'IAM de Cloud Run rejetait
  alors la requête du front *avant* qu'elle n'atteigne `VerificateurJeton` (401 sans aucune
  trace applicative) — `front/passerelle.py` ne relaie qu'un seul jeton (l'assertion IAP),
  qui ne peut pas aussi être l'identité IAM que l'ancien binding `run.invoker` attendait.
  `sorabel-mcp` est un vrai Resource Server OAuth : c'est lui, seul, qui doit authentifier.
- Sur un projet créé après le 19 janvier 2026, IAP ne peut plus provisionner automatiquement
  son client OAuth (API dépréciée par Google) : activer IAP échoue à l'exécution avec
  « Empty Google Account OAuth client ID(s)/secret(s) », indépendamment de toute
  configuration correcte par ailleurs. Contournement documenté en `docs/EXPLOITATION.md` §6.2.
- Un client OAuth générique (dont MCP Inspector) envoie l'`access_token` opaque de Google
  comme jeton porteur, jamais l'`id_token` (le vrai JWT que `VerificateurJeton` sait
  décoder) — un décalage de convention, pas un bug du serveur. `scripts/mcp_client_oauth.py`
  le contourne en envoyant explicitement l'`id_token`, et sert de preuve que le serveur valide
  correctement un jeton bien formé.

---

## 13. Démonstration en 5 minutes

La séquence qui montre le plus en le moins de temps, chaque étape s'appuyant sur la
précédente. Décrite ici avec `scripts/mcp_client.py --profil …` contre un serveur stdio
local ; pour le parcours de démonstration sur le poste de travail Streamlit du déploiement
GCP réel (IAP, inscription, Firestore), voir `docs/EXPLOITATION.md` §9.

1. **Le même échange, deux profils.** Appeler `search_docs` en `commercial`, puis en `dev` :
   les tools de la base de données (`ask_database`, `get_schema`, `check_stock`,
   `order_status`) ne sont plus accordés en `dev`. Dans le poste de travail, cela se traduit
   par quatre entrées de menu qui disparaissent — la matrice les a retirées, la page ne
   masque rien elle-même.
2. **Chercher sans générer.** Documentation → « Rechercher un extrait » sur `REF-8842` :
   extraits bruts et scores, sans LLM. Puis « Ouvrir un document » sur le `chunk_id` obtenu.
   Les briques du RAG fonctionnent séparément du tool de haut niveau.
3. **Une réponse et ses sources.** « Poser une question » : la réponse cite ses documents, et
   les citations viennent des métadonnées des chunks — pas du modèle.
4. **Le refus.** Poser une question hors corpus (« quelle est la capitale de l'Australie ? ») :
   `hors_corpus`, sans qu'aucune génération n'ait lieu. Le distinguer d'une panne à l'écran.
5. **E5 en direct.** En `support`, Données → « Périmètre accessible » : `prix_achat_ht`,
   `marge_pct` et `marge_ht` sont **absentes du schéma**. Puis demander les marges : refus,
   et le SQL rejeté reste affiché. Rebasculer en `commercial` : la même question aboutit.
6. **La trace.** `logs/appels.jsonl` (ou Cloud Logging si `SORABEL_JOURNAL=stdout`) : une
   ligne par appel, avec profil, statut, SQL et durée — refus compris (`autorise=false`).

---

## 14. Déploiement

La mise en production sur GCP (deux services Cloud Run, image Docker à deux étapes, CI/CD
Cloud Build, Firestore, OAuth 2.1) est **déployée et vérifiée** sur `sorabel-vitrine-2026`
(europe-west1) : `docs/EXPLOITATION.md` documente le provisionnement pas à pas, les variables
à renseigner, les coûts, et le parcours de démonstration tel qu'il a effectivement été
déroulé — y compris les correctifs que ce premier déploiement réel a rendus nécessaires
(§12). Ce fichier-ci ne la duplique pas ; il ne décrit que le code et ses contrats.

L'image copie le paquet `sorabel_enseigne/` et le seul `enseignes/sorabel/enseigne.toml` —
jamais le dossier `enseignes/` entier, pour que le corpus d'une autre enseigne n'y entre pas ;
`tests/test_dockerfile.py` vérifie statiquement que chaque étape copie les paquets que le code
importe.

---

## Pour aller plus loin

| Sujet | Fichier |
|---|---|
| Cahier des charges, tests d'acceptance | `BRIEF.md` |
| Décisions de conception et alternatives écartées | `docs/conception.md` |
| Diagrammes Mermaid des trois chantiers | `docs/schemas.md` |
| Provisionnement GCP et parcours de démonstration en production | `docs/EXPLOITATION.md` |
| Plans d'exécution par phase (archive datée) | `docs/superpowers/` |
| Croquis de travail | `docs/croquis/` |
