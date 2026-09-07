# CLAUDE.md

Guide pour Claude Code (claude.ai/code) sur ce dépôt.

## Le projet

**Sorabel Data Gateway** : un serveur MCP unique exposant, à des clients internes, un RAG
hybride et un Text-to-SQL en lecture seule sur les données d'un distributeur B2B de matériel
électrique — le tout gouverné par une matrice d'accès et journalisé.

**Lire `docs/DOSSIER_TECHNIQUE.md` avant toute intervention.** Il porte le schéma applicatif,
l'arborescence commentée, les contrats entre paquets et les limites connues. Ce fichier-ci ne
répète pas son contenu : il donne les conventions de travail.

| Document | Contenu |
|---|---|
| `docs/DOSSIER_TECHNIQUE.md` | État du code, contrats, commandes, traçabilité E1–E6 |
| `docs/conception.md` | Décisions et alternatives écartées, par chantier |
| `docs/schemas.md` | Diagrammes Mermaid des trois chantiers |
| `BRIEF.md` | Cahier des charges — **les tests d'acceptance sont la spécification** |

## État

Les six phases applicatives sont livrées : ingestion, RAG hybride, Text-to-SQL, gouvernance,
serveur MCP, front Streamlit. Le chantier `gcp-vitrine` les a ensuite mises en état de
production sur GCP : transport HTTP, authentification OAuth 2.1, identités Firestore, image
Docker, CI/CD Cloud Build (détails dans `docs/EXPLOITATION.md`). **182 tests** passent
(`python -m pytest -q`).

Reste ouvert : l'évaluation E6 (`eval/run_eval.py` n'existe pas — voir §12 du dossier
technique).

## Commandes

```bash
uv sync                                   # Python 3.12, voir .python-version
python -m pytest -q                       # 182 tests

python scripts/seed_gouvernance.py        # gouvernance.db
python scripts/ingerer.py                 # corpus → data/canonique/
python scripts/indexer.py                 # canoniques → Chroma + BM25

SORABEL_PROFIL=commercial python -m mcp_server.serveur   # serveur MCP, stdio (développement)
streamlit run front/app_client.py
```

Il n'y a ni linter ni formateur configuré : suivre le style du fichier voisin.

## Contraintes non négociables

Elles viennent des exigences DSI et des tests d'acceptance ; les enfreindre invalide le
projet.

- **Vector store : Chroma** (imposé par le brief).
- **Citations construites par le code**, jamais demandées au LLM : elles dérivent des
  métadonnées des chunks réellement passés au prompt.
- **Refus hors corpus déterministe** : sous le seuil calibré, on ne génère pas du tout. Le
  refus est un retour normal (`{"statut": "hors_corpus"}`), pas une exception — et une panne
  technique ne doit jamais se présenter comme un refus documentaire.
- **SQL en lecture seule à barrières multiples** : connexion `mode=ro` *et* validation de la
  requête *et* périmètre *et* `LIMIT`. Une seule barrière ne suffit pas. Le joker `SELECT *`
  est un contournement d'E5 déjà rencontré : `_contient_selection_generique()` doit continuer
  de distinguer le joker, `COUNT(*)` et la multiplication.
- **Matrice d'accès appliquée à chaque appel de tool, refus compris dans le journal.** Le
  décorateur `_gouverne` (`mcp_server/tools.py`) résout le périmètre et vérifie le droit à
  chaque requête. En HTTP (production), c'est lui l'intercepteur d'entrée : les 8 tools sont
  toujours enregistrés, et le profil se lit dans le jeton à chaque appel — `tools/list` ne
  filtre plus rien. En stdio (développement local), le comportement historique subsiste : un
  processus sert un seul profil figé au démarrage (`SORABEL_PROFIL`), et un tool hors
  périmètre n'est jamais enregistré. Dans les deux cas, tout appel — autorisé ou refusé —
  est journalisé.
- **Le front n'applique aucune règle d'accès.** Il reflète ce que le serveur lui a laissé
  voir : `front/depot.py::tools_accordes()` lit la matrice directement, plus jamais
  `tools/list`. Ne pas réintroduire de chemin d'accès direct au pipeline : une page de debug
  qui contournait la gouvernance a existé et a été retirée.
- **Le gain de l'hybride doit être mesuré** (E6) sur `eval/questions_rag.jsonl`, questions par
  référence exacte et en langage naturel **rapportées séparément** — une moyenne globale
  masque ce qu'on cherche à démontrer. Métriques : Recall@5, MRR, Hit@1.

## Conventions

**Langue** — corpus, conception et échanges sont en français. Le code de domaine suit :
`reference`, `est_version_courante`, `statut`, `sources`. Les commentaires expliquent
*pourquoi*, pas *quoi*.

**Modèles** — toute inférence passe par Azure AI Foundry via `sorabel_llm/client.py` (API v1,
client `OpenAI` avec `base_url`, pas `AzureOpenAI`). Rien ne tourne en local sur CPU. Changer
le déploiement d'embeddings **impose de réindexer** ; changer celui de reranking impose de
recalibrer `SEUIL_REFUS`.

**Périmètre duck-typé** — `sorabel_rag` et `sorabel_sql` n'importent rien de `gouvernance` :
ils reçoivent un objet à quatre méthodes (`peut_appeler`, `collections_autorisees`,
`tables_autorisees`, `colonnes_interdites`). Toute méthode ajoutée doit l'être aux doublures
de test.

**Variables d'environnement** — `SORABEL_TRANSPORT` : `stdio` par défaut (développement,
tests, `scripts/mcp_client.py`) ou `http` (streamable, production). `SORABEL_JOURNAL` :
`stdout` bascule le journal vers Cloud Logging au lieu de `logs/appels.jsonl` (production).
`SORABEL_DEPOT` : `firestore` choisit `gouvernance/identites_firestore.py` (production),
toute autre valeur (ou absence) reste sur `gouvernance/identites.py` (SQLite). Front :
`SORABEL_URL_MCP`, où joindre le serveur MCP déployé (`front/passerelle.py`).
Authentification HTTP (`mcp_server/authentification.py`) : `SORABEL_OIDC_ISSUER` /
`SORABEL_OIDC_AUDIENCE` / `SORABEL_OIDC_JWKS` pour les clients MCP tiers (Google Identity
Platform), `SORABEL_IAP_AUDIENCE` pour l'assertion relayée par le front derrière
Identity-Aware Proxy, `SORABEL_URL_PUBLIQUE` pour les métadonnées de ressource protégée du
serveur lui-même.

**Windows** — deux pièges déjà payés dans `front/mcp_client.py`, à ne pas réintroduire : la
politique `WindowsProactorEventLoopPolicy` est nécessaire pour lancer un sous-processus, et
l'environnement du serveur doit **hériter** de `os.environ` (sinon `WinError 10106`).

**Streamlit** — le style de `front/app_client.py` dépend de la structure interne du DOM. En
cas de règle CSS sans effet, vérifier les `data-testid` réels dans le bundle installé plutôt
que de supposer une profondeur.

## Données

`data/corpus/` : 150 fiches PDF, 80 notices PDF, 80 notes Markdown, 90 procédures SAV HTML.
Pour les 230 PDF, **référence et version viennent du nom de fichier**, jamais du contenu. Le
corpus contient volontairement plusieurs versions d'un même document : tout est indexé, la
version courante est marquée, la recherche filtre dessus par défaut.

`data/sorabel.db` : `produits` (120), `stocks` (312), `clients` (60), `commandes` (340),
`ventes` (993). `produits.ref` est le pivot entre les deux mondes.

**Colonnes sensibles (E5)** : `produits.prix_achat_ht`, `produits.marge_pct`,
`ventes.marge_ht` — hors périmètre pour `support` et `dev`.
