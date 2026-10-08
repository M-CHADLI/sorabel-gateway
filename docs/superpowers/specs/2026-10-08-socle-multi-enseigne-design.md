# Socle multi-enseigne de la Data Gateway — conception

**Date** : 8 octobre 2026
**Objectif** : faire de la Sorabel Data Gateway un moteur réutilisable, décliné par
enseigne, sans changer le comportement de Sorabel. Premier des quatre sous-chantiers de la
déclinaison Kiabi.

## 1. Contexte et découpage

La déclinaison Kiabi garde toutes les fonctionnalités (RAG hybride, Text-to-SQL, matrice
d'accès, journal, serveur MCP, front) et change trois choses : les données, les textes
métier, le branding du front. Décisions prises en amont :

| Question | Décision |
|---|---|
| Organisation | Un seul dépôt, un dossier par enseigne — pas de copie du code ni de branche dédiée |
| Modèle de données | Même structure (5 tables, mêmes colonnes, 4 types de documents), habillée mode |
| Génération des données Kiabi | Hybride : script déterministe + textes rédigés une fois par LLM, figés dans le dépôt |
| Déploiement | Local, puis un second déploiement GCP derrière IAP |
| Aiguillage | Une config par enseigne, lue par un seul module (approche A ci-dessous) |

Quatre sous-chantiers, chacun avec sa spec et son plan, livrés dans l'ordre :

1. **Socle multi-enseigne** — ce document.
2. **Générateur Kiabi** — base SQLite et corpus (PDF, Markdown, HTML), cohérents entre eux
   et reproduisant les pièges du corpus Sorabel (versions multiples, références exactes,
   notes à diffusion restreinte, colonnes sensibles E5).
3. **Branding du front** — thème, logo, textes et exemples par enseigne ; mode local du
   front, aujourd'hui inutilisable hors IAP (`front/app_client.py`, garde « Session non
   authentifiée »).
4. **Déploiement GCP Kiabi** — image paramétrée par enseigne, services `kiabi-mcp` et
   `kiabi-front` derrière IAP.

Hors périmètre de ce sous-chantier : tout fichier Kiabi, le front (hormis le chemin de
`gouvernance.db` codé en dur dans `front/depot.py`), `Dockerfile`,
`cloudbuild.yaml`, le seuil de refus par enseigne (à recalibrer au sous-chantier 2 si les
scores du reranker sur le corpus Kiabi le demandent).

## 2. Vocabulaire

**Enseigne** plutôt que « client » : le mot client désigne déjà la table SQL `clients`, les
clients MCP et `sorabel_llm/client.py`. « Sorabel Data Gateway » devient le nom du moteur ;
Sorabel en est la première enseigne. Les paquets `sorabel_*` gardent leur nom.

## 3. Approches considérées

- **A — Config par enseigne, un seul lecteur (retenue).** `SORABEL_ENSEIGNE` désigne
  l'enseigne ; `enseignes/<nom>/enseigne.toml` décrit ses chemins et ses textes ; un module
  unique le lit. Chaque commande dit pour quelle enseigne elle tourne, aucun état caché.
- **B — Recopie dans `data/`** (`make use ENSEIGNE=kiabi`). Aucun changement de code, mais
  état caché (quelle enseigne est active ?), risque d'écraser l'index Sorabel, liens
  symboliques soumis aux droits administrateur sous Windows. Écartée.
- **C — Chemins et textes passés en paramètres de bout en bout.** Explicite, mais touche
  toutes les signatures et tous les tests pour un gain nul par rapport à A. Écartée.

## 4. Le module `sorabel_enseigne`

```
enseignes/
  sorabel/enseigne.toml        déclare les chemins actuels : data/, gouvernance/, logs/
sorabel_enseigne/
  __init__.py                  enseigne_active(), charger_enseigne(chemin)
  __main__.py                  python -m sorabel_enseigne make  → variables Make
```

- `charger_enseigne(chemin_toml) -> Enseigne` : lit un `enseigne.toml` (`tomllib`, bibliothèque
  standard — aucune dépendance ajoutée) et renvoie un objet figé (`dataclass(frozen=True)`).
  Les chemins relatifs sont résolus depuis la racine du dépôt.
- `enseigne_active() -> Enseigne` : lit `SORABEL_ENSEIGNE` (défaut `sorabel`), charge
  `enseignes/<nom>/enseigne.toml`, met le résultat en cache pour la durée du processus.
- **Enseigne inconnue** : `ValueError` explicite listant les enseignes disponibles. Jamais de
  repli silencieux sur Sorabel — une démo sur les mauvaises données est pire qu'un échec.

### Contenu de `enseigne.toml`

| Clé | Sorabel (valeur actuelle, à l'identique) | Consommateur |
|---|---|---|
| `nom`, `libelle` | `sorabel`, `Sorabel` | journal, messages |
| `chemins.corpus` | `data/corpus` | `sorabel_rag/ingestion.py` (`CORPUS`) |
| `chemins.canonique` | `data/canonique` | `sorabel_rag/ingestion.py` (`SORTIE`) |
| `chemins.chroma` | `data/chroma` | `sorabel_rag/index.py` (`DOSSIER_CHROMA`, `CHEMIN_BM25`) |
| `chemins.base_sql` | `data/sorabel.db` | `sorabel_sql/execution.py` (`CHEMIN_DB`) |
| `chemins.gouvernance` | `gouvernance/gouvernance.db` | `mcp_server/serveur.py`, `front/depot.py`, `scripts/seed_gouvernance.py`, `scripts/demo_mcp_http.py` |
| `chemins.journal` | `logs/appels.jsonl` | `gouvernance/journal.py` (`CHEMIN_JOURNAL`) |
| `rag.collection` | `sorabel_docs` | `sorabel_rag/index.py` (`NOM_COLLECTION`) |
| `rag.presentation` | « l'assistant documentaire de Sorabel, distributeur B2B de matériel électrique » | `sorabel_rag/generation.py` (`PROMPT_SYSTEME`) |
| `extraction.pied_de_page` | `Document Sorabel` | `sorabel_rag/extraction.py` |
| `sql.nom_base` | `Sorabel` | `sorabel_sql/generation.py` (`PROMPT_SYSTEME`), `sorabel_sql/tools.py` (message hors schéma) |
| `sql.commentaires` | commentaires de colonnes porteurs de domaine : catégories, entrepôts, segments, exemples d'identifiants | `sorabel_sql/schema.py` (`COLONNES`) |

`sql.commentaires` ne surcharge que les commentaires : noms de tables, noms et types de
colonnes restent dans `schema.py`, communs à toutes les enseignes — c'est la décision
« même structure ». Le lexique sensible (`sorabel_sql/lexique_sensible.py`) porte sur ces
colonnes communes et ne bouge pas.

### Raccordement sans changement de signature

Les constantes de module existantes gardent leur nom ; seule leur valeur vient de
`enseigne_active()` (ex. `CORPUS = enseigne_active().chemins.corpus`). Conséquences :
aucune signature publique ne change, et les tests qui surchargent ces constantes par
`monkeypatch.setattr` (`CHEMIN_JOURNAL` dans `test_gouvernance_journal.py` et
`test_mcp_tools.py`) continuent de fonctionner tels quels.

La règle de `CLAUDE.md` « `sorabel_rag` et `sorabel_sql` n'importent rien de `gouvernance` »
est préservée : `sorabel_enseigne` ne dépend d'aucun paquet du projet, tous peuvent
l'importer.

## 5. Makefile

- `ENSEIGNE ?= sorabel`, exportée en `SORABEL_ENSEIGNE` pour toutes les recettes. Toutes les
  cibles existantes la suivent (`make demo ENSEIGNE=kiabi`, `make journal ENSEIGNE=kiabi`…).
- **Une seule source de vérité pour les chemins.** Le Makefile ne recopie pas les chemins :
  `python -m sorabel_enseigne make` écrit `GOUVERNANCE_DB`, `MANIFESTE`, `INDEX`, `CORPUS_DIR`,
  `JOURNAL` dans `.make/<enseigne>.mk`, inclus par le Makefile. Une règle
  `.make/%.mk: enseignes/%/enseigne.toml` le régénère quand le `.toml` change — sans quoi
  chaque `make` paierait un `uv run`. `.make/` est ignoré par git.
- Nouvelle cible `make enseignes` : liste les dossiers `enseignes/*/enseigne.toml`.
- `make help` affiche l'enseigne active.
- Les textes des recettes restent sans accents (piège de page de code ANSI déjà documenté en
  tête du Makefile).

## 6. Tests

**`tests/conftest.py`** (nouveau) : fixe `SORABEL_ENSEIGNE=sorabel` avant tout import. Les
182 tests existants portent sur le moteur avec Sorabel pour jeu de données ; un
`ENSEIGNE=kiabi` resté dans le shell ne doit pas les faire échouer.

**`tests/test_enseigne.py`** (nouveau) :

- sans variable d'environnement, l'enseigne active est `sorabel` ;
- une enseigne inconnue lève `ValueError` et la liste des enseignes disponibles ;
- une seconde enseigne décrite par un `.toml` temporaire (`charger_enseigne`) résout ses
  propres chemins, sans effet sur ceux de Sorabel ;
- la sortie de `python -m sorabel_enseigne make` reprend exactement les chemins du `.toml`.

**`tests/test_enseigne_sorabel_inchangee.py`** (nouveau) — instantanés de référence,
**capturés sur le code actuel, avant toute modification**, puis comparés après :

- les deux `PROMPT_SYSTEME` (RAG et SQL), à l'octet près ;
- `schema_commente()` pour chacun des 4 profils ;
- `CORPUS`, `SORTIE`, `DOSSIER_CHROMA`, `CHEMIN_BM25`, `CHEMIN_DB`, `CHEMIN_GOUVERNANCE_DB`,
  `CHEMIN_JOURNAL`, `NOM_COLLECTION`.

Capturés après coup, ces instantanés figeraient le comportement refactoré, défauts compris ;
capturés avant, ils font de « rien n'a changé pour Sorabel » une assertion vérifiable.

## 7. Documentation

- `CLAUDE.md` : `SORABEL_ENSEIGNE` dans la section Variables d'environnement ; le dossier
  `enseignes/` dans la section Données.
- `docs/DOSSIER_TECHNIQUE.md` : `sorabel_enseigne/` et `enseignes/` dans l'arborescence (§2),
  le contrat `enseigne_active()` dans les contrats entre paquets (§3).

## 8. Critères de fin

1. `make test` vert : les 182 tests existants, inchangés, plus les nouveaux.
2. Instantanés Sorabel identiques avant et après.
3. `make demo` renvoie les mêmes titres pour `search_docs('politique tarifaire')` qu'avant.
4. `Dockerfile` et `cloudbuild.yaml` non modifiés : la production tourne sur l'enseigne par
   défaut, la CI construit la même image.
5. Aucun fichier Kiabi dans le dépôt — il arrive au sous-chantier 2.
