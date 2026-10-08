# Socle multi-enseigne — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire lire au moteur ses chemins et ses textes métier dans une config par enseigne (`enseignes/<nom>/enseigne.toml`), Sorabel restant l'enseigne par défaut au comportement strictement inchangé.

**Architecture:** Un module sans dépendance, `sorabel_enseigne`, est le seul lecteur de `SORABEL_ENSEIGNE` et des `.toml`. Les constantes de module existantes (`CORPUS`, `CHEMIN_DB`, `PROMPT_SYSTEME`…) gardent leur nom mais prennent leur valeur dans `enseigne_active()` — une enseigne par processus. Des instantanés capturés sur le code actuel, avant toute modification, prouvent que Sorabel n'a pas bougé. Le Makefile tire ses chemins d'un `.make/<enseigne>.mk` généré depuis le `.toml`.

**Tech Stack:** Python 3.12 (`tomllib`, `dataclasses`, `functools.lru_cache`), pytest, GNU Make 4.4 (ezwinports) piloté par le `sh` de Git for Windows, `uv`.

## Global Constraints

- **Spécification de référence** : `docs/superpowers/specs/2026-10-08-socle-multi-enseigne-design.md`. En cas de contradiction, la spec fait foi — signaler l'écart plutôt que trancher seul.
- **Branche** : `kiabi`. Ne rien pousser.
- **Les 182 tests existants ne sont pas modifiés** et passent à chaque tâche. Tout nouveau test va dans un **nouveau fichier**. Aucun test n'appelle le réseau (Azure, Google, Firestore).
- **Sans `SORABEL_ENSEIGNE`, l'enseigne est `sorabel`**, et son comportement est identique à l'octet près au tag `sorabel-v1` : chemins, nom de collection Chroma, prompts, schéma commenté, messages.
- **Enseigne inconnue → `ValueError` explicite**, jamais de repli silencieux sur Sorabel.
- **`sorabel_enseigne` n'importe aucun paquet du projet.** `sorabel_rag` et `sorabel_sql` n'importent toujours rien de `gouvernance`. Le contrat duck-typé de `Perimetre` (4 méthodes) ne change pas.
- **Aucune dépendance ajoutée** (`tomllib` est dans la bibliothèque standard).
- **Ne pas toucher** `cloudbuild.yaml`, `front/app_client.py`, `front/passerelle.py`. Aucun fichier Kiabi. Le `Dockerfile` ne change que par les `COPY` de `sorabel_enseigne/` et de `enseignes/sorabel/enseigne.toml` (le moteur en dépend à l'import) — amendé après la revue finale (2026-10-08).
- **Makefile** : aucun accent dans le texte des recettes (page de code ANSI sous Windows, cf. commentaire en tête du Makefile) ; uniquement des chemins **relatifs** à la racine (le chemin du dépôt contient des espaces et une apostrophe).
- **Langue** : identifiants de domaine, messages et commentaires en français. Les commentaires expliquent *pourquoi*.
- **Commandes** : toutes lancées depuis la racine du dépôt, dans le shell Bash (Git Bash), via `uv run`.

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `sorabel_enseigne/__init__.py` | **Créer.** `Enseigne`, `Chemins`, `charger_enseigne`, `enseigne`, `enseigne_active`, `enseignes_disponibles` |
| `sorabel_enseigne/__main__.py` | **Créer.** CLI `liste` / `make <nom>` pour le Makefile |
| `enseignes/sorabel/enseigne.toml` | **Créer.** Chemins et textes historiques de Sorabel |
| `tests/conftest.py` | **Créer.** Fige `SORABEL_ENSEIGNE=sorabel` ; fixture `ecrire_enseigne` |
| `tests/instantanes/sorabel/*` | **Créer.** Instantanés capturés sur le code d'avant |
| `tests/test_enseigne_sorabel_inchangee.py` | **Créer.** Compare le code aux instantanés |
| `tests/test_enseigne.py` | **Créer.** Chargement, cache, erreurs |
| `tests/test_enseigne_raccordement.py` | **Créer.** Chaque module lit l'enseigne (interpréteur neuf) |
| `tests/test_sql_schema_enseigne.py` | **Créer.** Commentaires de schéma par enseigne |
| `tests/test_enseigne_cli.py` | **Créer.** CLI et fins de ligne |
| `sorabel_rag/ingestion.py`, `sorabel_rag/index.py`, `sorabel_sql/execution.py`, `gouvernance/journal.py`, `mcp_server/serveur.py`, `front/depot.py`, `scripts/seed_gouvernance.py`, `scripts/demo_mcp_http.py` | **Modifier.** Chemins lus dans l'enseigne |
| `sorabel_rag/generation.py`, `sorabel_rag/extraction.py`, `sorabel_sql/generation.py`, `sorabel_sql/tools.py`, `sorabel_sql/schema.py` | **Modifier.** Textes métier lus dans l'enseigne |
| `Makefile`, `.gitignore` | **Modifier.** `ENSEIGNE`, include généré, `make enseignes` |
| `CLAUDE.md`, `docs/DOSSIER_TECHNIQUE.md` | **Modifier.** Variable, arborescence, contrat |

Décompte des tests attendu : 182 → 191 (Task 1) → 202 (Task 2) → 203 (Task 3) → 207 (Task 4) → 212 (Task 5).

---

### Task 1: Instantanés de référence de Sorabel

Tests de caractérisation : ils passent sur le code actuel **par construction**. Leur valeur vient de l'ordre — capturés avant toute modification, ils figent l'existant, pas le refactoré.

**Files:**
- Create: `tests/instantanes/sorabel/prompt_rag.txt`, `prompt_sql.txt`, `schema_support.txt`, `schema_commercial.txt`, `schema_dev.txt`, `schema_admin.txt`, `fiche_REF-1024-v2.1.json` (générés à l'étape 1)
- Test: `tests/test_enseigne_sorabel_inchangee.py`

**Interfaces:**
- Consumes: `sorabel_rag.generation.PROMPT_SYSTEME`, `sorabel_sql.generation.PROMPT_SYSTEME`, `sorabel_sql.schema.schema_commente(perimetre)`, `sorabel_sql.tools.ask_database(question, perimetre)`, `sorabel_rag.extraction.extraire_fiche(chemin)`, `gouvernance.seed.peupler(chemin)`, `gouvernance.modeles.charger_matrice(chemin)`, `gouvernance.perimetre.Perimetre(profil, matrice)`.
- Produces: les fichiers d'instantanés, relus par ce seul test. Aucune tâche ne doit les régénérer.

- [ ] **Step 1: Capturer les instantanés depuis le code actuel**

Vérifier d'abord que l'arbre est propre sur le code (aucun fichier `.py` modifié) : `git status --short` ne doit lister aucun `.py`. Puis :

```bash
uv run python - <<'EOF'
import json
import tempfile
from pathlib import Path

from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre
from gouvernance.seed import peupler
from sorabel_rag.extraction import extraire_fiche
from sorabel_rag.generation import PROMPT_SYSTEME as PROMPT_RAG
from sorabel_sql.generation import PROMPT_SYSTEME as PROMPT_SQL
from sorabel_sql.schema import schema_commente

sortie = Path("tests/instantanes/sorabel")
sortie.mkdir(parents=True, exist_ok=True)


def ecrire(nom, texte):
    (sortie / nom).write_text(texte, encoding="utf-8", newline="\n")


ecrire("prompt_rag.txt", PROMPT_RAG)
ecrire("prompt_sql.txt", PROMPT_SQL)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as dossier:
    chemin = Path(dossier) / "gouvernance.db"
    peupler(chemin)
    matrice = charger_matrice(chemin)
    for profil in ["support", "commercial", "dev", "admin"]:
        ecrire(f"schema_{profil}.txt", schema_commente(Perimetre(profil, matrice)))
document = extraire_fiche(Path("data/corpus/fiches/REF-1024-v2.1.pdf"))
sections = [{"titre": s.titre, "contenu": s.contenu} for s in document.sections]
ecrire("fiche_REF-1024-v2.1.json", json.dumps(sections, ensure_ascii=False, indent=2) + "\n")
EOF
ls tests/instantanes/sorabel
```

Expected: 7 fichiers listés. Contrôle visuel : `grep -c "LILLE" tests/instantanes/sorabel/schema_commercial.txt` → `1` ; `grep -c "Document Sorabel" tests/instantanes/sorabel/fiche_REF-1024-v2.1.json` → `0` (le pied de page est bien filtré de la section Identification).

- [ ] **Step 2: Écrire le test qui compare le code aux instantanés**

```python
# tests/test_enseigne_sorabel_inchangee.py
"""Sorabel inchangée par le socle multi-enseigne.

Les instantanés de tests/instantanes/sorabel/ ont été capturés sur le code d'AVANT
sorabel_enseigne (tag sorabel-v1). S'ils divergent, c'est que enseignes/sorabel/enseigne.toml
ne reproduit pas exactement l'existant : on corrige la config, jamais l'instantané.
"""

import json
from pathlib import Path

import pytest

from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre
from gouvernance.seed import peupler

RACINE = Path(__file__).resolve().parent.parent
INSTANTANES = Path(__file__).resolve().parent / "instantanes" / "sorabel"
PROFILS = ["support", "commercial", "dev", "admin"]


def _lire(nom: str) -> str:
    return (INSTANTANES / nom).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def matrice(tmp_path_factory):
    chemin = tmp_path_factory.mktemp("gouvernance") / "gouvernance.db"
    peupler(chemin)
    return charger_matrice(chemin)


def test_prompt_rag_inchange():
    from sorabel_rag.generation import PROMPT_SYSTEME

    assert PROMPT_SYSTEME == _lire("prompt_rag.txt")


def test_prompt_sql_inchange():
    from sorabel_sql.generation import PROMPT_SYSTEME

    assert PROMPT_SYSTEME == _lire("prompt_sql.txt")


@pytest.mark.parametrize("profil", PROFILS)
def test_schema_commente_inchange(matrice, profil):
    from sorabel_sql.schema import schema_commente

    assert schema_commente(Perimetre(profil, matrice)) == _lire(f"schema_{profil}.txt")


def test_message_hors_schema_inchange(monkeypatch, matrice):
    from sorabel_sql import tools

    monkeypatch.setattr(tools, "generer", lambda question, perimetre: None)
    reponse = tools.ask_database("question quelconque", Perimetre("commercial", matrice))
    assert reponse["message"] == "Cette question ne correspond à aucune table de la base Sorabel."


def test_extraction_fiche_inchangee():
    from sorabel_rag.extraction import extraire_fiche

    document = extraire_fiche(RACINE / "data" / "corpus" / "fiches" / "REF-1024-v2.1.pdf")
    sections = [{"titre": s.titre, "contenu": s.contenu} for s in document.sections]
    assert sections == json.loads(_lire("fiche_REF-1024-v2.1.json"))


def test_chemins_et_collection_inchanges():
    from gouvernance import journal
    from mcp_server import serveur
    from sorabel_rag import index, ingestion
    from sorabel_sql import execution

    assert ingestion.CORPUS == RACINE / "data" / "corpus"
    assert ingestion.SORTIE == RACINE / "data" / "canonique"
    assert index.DOSSIER_CHROMA == RACINE / "data" / "chroma"
    assert index.CHEMIN_BM25 == RACINE / "data" / "chroma" / "bm25.pkl"
    assert index.NOM_COLLECTION == "sorabel_docs"
    assert execution.CHEMIN_DB == RACINE / "data" / "sorabel.db"
    assert serveur.CHEMIN_GOUVERNANCE_DB == RACINE / "gouvernance" / "gouvernance.db"
    assert journal.CHEMIN_JOURNAL == RACINE / "logs" / "appels.jsonl"
```

- [ ] **Step 3: Lancer le test**

Run: `uv run python -m pytest tests/test_enseigne_sorabel_inchangee.py -v`
Expected: `9 passed`.

- [ ] **Step 4: Lancer toute la suite**

Run: `uv run python -m pytest -q`
Expected: `191 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/instantanes tests/test_enseigne_sorabel_inchangee.py
git commit -m "test: instantanes de reference de Sorabel avant le socle multi-enseigne

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Module `sorabel_enseigne` et enseigne Sorabel

**Files:**
- Create: `sorabel_enseigne/__init__.py`
- Create: `enseignes/sorabel/enseigne.toml`
- Create: `tests/conftest.py`
- Test: `tests/test_enseigne.py`

**Interfaces:**
- Consumes: rien du projet (contrainte globale).
- Produces :
  - `sorabel_enseigne.RACINE: Path` — racine du dépôt.
  - `sorabel_enseigne.DOSSIER_ENSEIGNES: Path` — `RACINE / "enseignes"`, lu à chaque appel (remplaçable par `monkeypatch`).
  - `Chemins` (dataclass figée) : `corpus`, `canonique`, `chroma`, `base_sql`, `gouvernance`, `journal`, tous `Path` absolus.
  - `Enseigne` (dataclass figée) : `nom: str`, `libelle: str`, `chemins: Chemins`, `collection: str`, `presentation: str`, `pied_de_page: str`, `nom_base: str`, `commentaires_sql: Mapping[str, str]` (clés `"table.colonne"`).
  - `charger_enseigne(chemin_toml: Path) -> Enseigne` — lève `ValueError` si une clé manque ou si `pied_de_page` est vide.
  - `enseignes_disponibles() -> list[str]` — triée.
  - `enseigne(nom: str) -> Enseigne` — mise en cache par nom (`enseigne.cache_clear()` disponible) ; `ValueError` si inconnue ou si le `nom` du `.toml` contredit son dossier.
  - `enseigne_active() -> Enseigne` — `enseigne(SORABEL_ENSEIGNE)`, `sorabel` si la variable est absente ou vide.
  - Fixture pytest `ecrire_enseigne(dossier, nom, donnees, nom_declare=None) -> Path`, définie dans `tests/conftest.py`.

- [ ] **Step 1: Écrire `tests/conftest.py`**

```python
# tests/conftest.py
"""Les tests portent sur le moteur, avec Sorabel pour jeu de données (références, corpus et
base réels). Un `ENSEIGNE=kiabi` resté dans le shell ne doit pas les faire échouer : on
fixe l'enseigne avant que pytest n'importe le moindre module du projet."""

import os
from pathlib import Path

import pytest

os.environ["SORABEL_ENSEIGNE"] = "sorabel"

GABARIT_ENSEIGNE = """nom = "{nom_declare}"
libelle = "Essai {nom}"

[chemins]
corpus = "{donnees}/corpus"
canonique = "{donnees}/canonique"
chroma = "{donnees}/chroma"
base_sql = "{donnees}/{nom}.db"
gouvernance = "{donnees}/gouvernance.db"
journal = "{donnees}/appels.jsonl"

[rag]
collection = "{nom}_docs"
presentation = "l'assistant documentaire de {nom}"

[extraction]
pied_de_page = "Document {nom}"

[sql]
nom_base = "{nom}"

[sql.commentaires]
"stocks.entrepot" = "ENTREPOT-{nom}"
"""


@pytest.fixture
def ecrire_enseigne():
    """Écrit `<dossier>/<nom>/enseigne.toml` et renvoie son chemin.

    `donnees` préfixe tous les chemins : relatif à la racine du dépôt, ou absolu — mais
    alors en `as_posix()`, une barre oblique inverse étant un échappement en TOML.
    """

    def _ecrire(dossier: Path, nom: str, donnees: str, nom_declare: str | None = None) -> Path:
        chemin = dossier / nom / "enseigne.toml"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(
            GABARIT_ENSEIGNE.format(nom=nom, nom_declare=nom_declare or nom, donnees=donnees),
            encoding="utf-8",
        )
        return chemin

    return _ecrire
```

- [ ] **Step 2: Écrire les tests qui échouent**

```python
# tests/test_enseigne.py
"""sorabel_enseigne : une enseigne par processus, jamais de repli silencieux."""

from pathlib import Path

import pytest

import sorabel_enseigne
from sorabel_enseigne import charger_enseigne, enseigne, enseigne_active, enseignes_disponibles

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def dossier_essai(tmp_path, monkeypatch):
    """`enseignes/` remplacé par un dossier temporaire. Le cache est vidé avant et après :
    sinon une enseigne d'essai survivrait au test dans `enseigne()`."""
    monkeypatch.setattr(sorabel_enseigne, "DOSSIER_ENSEIGNES", tmp_path)
    enseigne.cache_clear()
    yield tmp_path
    enseigne.cache_clear()


def test_sans_variable_l_enseigne_active_est_sorabel(monkeypatch):
    monkeypatch.delenv("SORABEL_ENSEIGNE", raising=False)
    assert enseigne_active().nom == "sorabel"


def test_variable_vide_retombe_sur_sorabel(monkeypatch):
    monkeypatch.setenv("SORABEL_ENSEIGNE", "")
    assert enseigne_active().nom == "sorabel"


def test_enseigne_inconnue_leve_une_erreur_qui_liste_les_disponibles(monkeypatch):
    monkeypatch.setenv("SORABEL_ENSEIGNE", "inexistante")
    with pytest.raises(ValueError, match=r"inexistante.*disponibles : .*sorabel"):
        enseigne_active()


def test_sorabel_declare_les_chemins_historiques():
    sorabel = enseigne("sorabel")
    assert sorabel.chemins.corpus == RACINE / "data" / "corpus"
    assert sorabel.chemins.canonique == RACINE / "data" / "canonique"
    assert sorabel.chemins.chroma == RACINE / "data" / "chroma"
    assert sorabel.chemins.base_sql == RACINE / "data" / "sorabel.db"
    assert sorabel.chemins.gouvernance == RACINE / "gouvernance" / "gouvernance.db"
    assert sorabel.chemins.journal == RACINE / "logs" / "appels.jsonl"
    assert sorabel.collection == "sorabel_docs"


def test_une_seconde_enseigne_resout_ses_propres_chemins(tmp_path, ecrire_enseigne):
    essai = charger_enseigne(ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data"))
    assert essai.chemins.corpus == RACINE / "enseignes" / "essai" / "data" / "corpus"
    assert essai.chemins.base_sql == RACINE / "enseignes" / "essai" / "data" / "essai.db"
    assert essai.commentaires_sql["stocks.entrepot"] == "ENTREPOT-essai"
    assert enseigne("sorabel").chemins.corpus == RACINE / "data" / "corpus"


def test_un_chemin_absolu_est_conserve_tel_quel(tmp_path, ecrire_enseigne):
    essai = charger_enseigne(ecrire_enseigne(tmp_path, "essai", tmp_path.as_posix()))
    assert essai.chemins.corpus == tmp_path / "corpus"


def test_une_cle_manquante_est_signalee(tmp_path):
    chemin = tmp_path / "enseigne.toml"
    chemin.write_text('nom = "incomplete"\nlibelle = "Incomplète"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="clé manquante"):
        charger_enseigne(chemin)


def test_un_pied_de_page_vide_est_refuse(tmp_path, ecrire_enseigne):
    chemin = ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data")
    chemin.write_text(
        chemin.read_text(encoding="utf-8").replace('"Document essai"', '""'), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="pied_de_page"):
        charger_enseigne(chemin)


def test_meme_nom_meme_objet_noms_distincts_independants(dossier_essai, ecrire_enseigne):
    ecrire_enseigne(dossier_essai, "alpha", "enseignes/alpha/data")
    ecrire_enseigne(dossier_essai, "beta", "enseignes/beta/data")
    assert enseigne("alpha") is enseigne("alpha")
    assert enseigne("alpha").chemins.corpus != enseigne("beta").chemins.corpus
    assert enseigne("alpha").collection == "alpha_docs"
    assert enseigne("beta").collection == "beta_docs"


def test_un_nom_qui_contredit_son_dossier_est_refuse(dossier_essai, ecrire_enseigne):
    ecrire_enseigne(dossier_essai, "gamma", "enseignes/gamma/data", nom_declare="delta")
    with pytest.raises(ValueError, match="delta"):
        enseigne("gamma")


def test_enseignes_disponibles_contient_sorabel():
    assert "sorabel" in enseignes_disponibles()
```

- [ ] **Step 3: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run python -m pytest tests/test_enseigne.py -v`
Expected: erreur de collecte `ModuleNotFoundError: No module named 'sorabel_enseigne'`.

- [ ] **Step 4: Écrire `enseignes/sorabel/enseigne.toml`**

Les valeurs reprennent **exactement** le code actuel (`sorabel_rag/generation.py`, `sorabel_rag/extraction.py`, `sorabel_sql/generation.py`, `sorabel_sql/schema.py`, `sorabel_rag/index.py`). La catégorie produit est une seule chaîne, sans retour à la ligne.

```toml
# Enseigne historique. Chemins et textes identiques au code d'avant le socle multi-enseigne
# (tag sorabel-v1) — tests/test_enseigne_sorabel_inchangee.py le vérifie à l'octet près.
nom = "sorabel"
libelle = "Sorabel"

# Relatifs à la racine du dépôt, pas à ce dossier : Sorabel garde ses chemins d'origine.
[chemins]
corpus = "data/corpus"
canonique = "data/canonique"
chroma = "data/chroma"
base_sql = "data/sorabel.db"
gouvernance = "gouvernance/gouvernance.db"
journal = "logs/appels.jsonl"

[rag]
collection = "sorabel_docs"
presentation = "l'assistant documentaire de Sorabel, distributeur B2B de matériel électrique"

[extraction]
# Ligne de pied de page des fiches PDF, à écarter de la section Identification.
pied_de_page = "Document Sorabel"

[sql]
nom_base = "Sorabel"

# Commentaires de colonnes porteurs du vocabulaire métier. Les noms et types de colonnes,
# eux, sont communs à toutes les enseignes (sorabel_sql/schema.py).
[sql.commentaires]
"produits.categorie" = "Protection électrique | EPI | Câblage | Outillage électroportatif | Visserie | Outillage à main | Distribution | Éclairage | Mesure"
"produits.unite" = "pièce | conditionnement"
"stocks.entrepot" = "LILLE | LYON | NANTES"
"clients.id" = "ex. 'CLI-1000'"
"clients.segment" = "PME | artisan | collectivité | grand compte"
```

- [ ] **Step 5: Écrire `sorabel_enseigne/__init__.py`**

```python
"""Une enseigne : un jeu de données et des textes métier, servis par le même moteur.

Seul lecteur de `SORABEL_ENSEIGNE` et de `enseignes/<nom>/enseigne.toml`. Volontairement
sans dépendance vers les autres paquets du projet : `sorabel_rag` et `sorabel_sql`
l'importent sans rien tirer de `gouvernance`.

Le moteur lit `enseigne_active()` — une enseigne par processus, figée au démarrage : un
serveur MCP Kiabi n'a jamais les données Sorabel à portée. Le front mutualisé, qui ne
détient aucune donnée, choisit par session avec `enseigne(nom)`.
"""

from __future__ import annotations

import functools
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_ENSEIGNES = RACINE / "enseignes"
ENSEIGNE_PAR_DEFAUT = "sorabel"


@dataclass(frozen=True)
class Chemins:
    corpus: Path
    canonique: Path
    chroma: Path
    base_sql: Path
    gouvernance: Path
    journal: Path


@dataclass(frozen=True)
class Enseigne:
    nom: str
    libelle: str
    chemins: Chemins
    collection: str
    presentation: str
    pied_de_page: str
    nom_base: str
    commentaires_sql: Mapping[str, str]


def charger_enseigne(chemin_toml: Path) -> Enseigne:
    """Les chemins relatifs du `.toml` sont résolus depuis la racine du dépôt, pas depuis le
    dossier de l'enseigne : c'est ce qui permet à Sorabel de garder `data/` tel quel."""
    chemin_toml = Path(chemin_toml)
    with chemin_toml.open("rb") as fichier:
        brut = tomllib.load(fichier)
    try:
        chemins = brut["chemins"]
        resultat = Enseigne(
            nom=brut["nom"],
            libelle=brut["libelle"],
            chemins=Chemins(**{champ.name: RACINE / chemins[champ.name] for champ in fields(Chemins)}),
            collection=brut["rag"]["collection"],
            presentation=brut["rag"]["presentation"],
            pied_de_page=brut["extraction"]["pied_de_page"],
            nom_base=brut["sql"]["nom_base"],
            commentaires_sql=MappingProxyType(dict(brut["sql"].get("commentaires", {}))),
        )
    except KeyError as cle:
        raise ValueError(f"{chemin_toml} : clé manquante {cle}") from None
    if not resultat.pied_de_page.strip():
        # `ligne.startswith("")` est toujours vrai : un pied de page vide ferait écarter à
        # l'extraction toute la section Identification des fiches, sans aucune erreur.
        raise ValueError(f"{chemin_toml} : extraction.pied_de_page ne peut pas être vide")
    return resultat


def enseignes_disponibles() -> list[str]:
    return sorted(chemin.parent.name for chemin in DOSSIER_ENSEIGNES.glob("*/enseigne.toml"))


@functools.lru_cache(maxsize=None)
def enseigne(nom: str) -> Enseigne:
    disponibles = enseignes_disponibles()
    if nom not in disponibles:
        # Jamais de repli sur Sorabel : une démonstration sur les mauvaises données est
        # pire qu'un échec franc au démarrage.
        raise ValueError(f"enseigne inconnue : {nom!r} — disponibles : {', '.join(disponibles)}")
    resultat = charger_enseigne(DOSSIER_ENSEIGNES / nom / "enseigne.toml")
    if resultat.nom != nom:
        raise ValueError(f"enseignes/{nom}/enseigne.toml déclare nom = {resultat.nom!r}")
    return resultat


def enseigne_active() -> Enseigne:
    return enseigne(os.environ.get("SORABEL_ENSEIGNE") or ENSEIGNE_PAR_DEFAUT)
```

- [ ] **Step 6: Lancer les tests pour vérifier qu'ils passent**

Run: `uv run python -m pytest tests/test_enseigne.py -v`
Expected: `11 passed`.

- [ ] **Step 7: Lancer toute la suite**

Run: `uv run python -m pytest -q`
Expected: `202 passed`.

- [ ] **Step 8: Commit**

```bash
git add sorabel_enseigne/__init__.py enseignes/sorabel/enseigne.toml tests/conftest.py tests/test_enseigne.py
git commit -m "feat(enseigne): module sorabel_enseigne et config de l'enseigne Sorabel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Raccorder les chemins à l'enseigne active

**Files:**
- Modify: `sorabel_rag/ingestion.py:15-29`, `sorabel_rag/index.py:15-26`, `sorabel_sql/execution.py:13-15`, `gouvernance/journal.py:13-15`, `mcp_server/serveur.py:17-25`, `front/depot.py:14-41`, `scripts/seed_gouvernance.py:9-12`, `scripts/demo_mcp_http.py:26-33`
- Test: `tests/test_enseigne_raccordement.py`

**Interfaces:**
- Consumes: `sorabel_enseigne.enseigne_active()`, `Enseigne.chemins`, `Enseigne.collection`, `sorabel_enseigne.DOSSIER_ENSEIGNES` (Task 2) ; fixture `ecrire_enseigne` (Task 2).
- Produces: nouvelle constante `front.depot.CHEMIN_GOUVERNANCE_DB: Path`. Toutes les autres constantes gardent leur nom (`ingestion.CORPUS`, `ingestion.SORTIE`, `index.DOSSIER_CHROMA`, `index.CHEMIN_BM25`, `index.NOM_COLLECTION`, `execution.CHEMIN_DB`, `journal.CHEMIN_JOURNAL`, `serveur.CHEMIN_GOUVERNANCE_DB`).

- [ ] **Step 1: Écrire le test qui échoue**

Le raccordement se vérifie dans un **interpréteur neuf** : les constantes sont évaluées à l'import, et le processus pytest a déjà importé ces modules avec l'enseigne `sorabel`.

```python
# tests/test_enseigne_raccordement.py
"""Chaque module du moteur lit son enseigne dans sorabel_enseigne, et nulle part ailleurs.

Vérifié dans un interpréteur neuf : les constantes sont évaluées à l'import, et le
processus de test a déjà importé ces modules avec l'enseigne sorabel (tests/conftest.py).
"""

import json
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Remplace `enseignes/` par le dossier temporaire AVANT tout import du moteur.
PREAMBULE = """
import json, os, sys
from pathlib import Path
import sorabel_enseigne
sorabel_enseigne.DOSSIER_ENSEIGNES = Path(sys.argv[1])
os.environ["SORABEL_ENSEIGNE"] = "essai"
"""

SCRIPT_CHEMINS = PREAMBULE + """
from front import depot
from gouvernance import journal
from mcp_server import serveur
from sorabel_rag import index, ingestion
from sorabel_sql import execution
print(json.dumps({
    "corpus": str(ingestion.CORPUS),
    "canonique": str(ingestion.SORTIE),
    "chroma": str(index.DOSSIER_CHROMA),
    "bm25": str(index.CHEMIN_BM25),
    "collection": index.NOM_COLLECTION,
    "base_sql": str(execution.CHEMIN_DB),
    "gouvernance_serveur": str(serveur.CHEMIN_GOUVERNANCE_DB),
    "gouvernance_front": str(depot.CHEMIN_GOUVERNANCE_DB),
    "journal": str(journal.CHEMIN_JOURNAL),
}))
"""


def _executer(script: str, dossier: Path) -> dict:
    sortie = subprocess.run(
        [sys.executable, "-c", script, str(dossier)],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8",
    )
    assert sortie.returncode == 0, sortie.stderr
    return json.loads(sortie.stdout)


def test_chaque_module_lit_ses_chemins_dans_l_enseigne_active(tmp_path, ecrire_enseigne):
    donnees = tmp_path / "donnees"
    ecrire_enseigne(tmp_path, "essai", donnees.as_posix())
    assert _executer(SCRIPT_CHEMINS, tmp_path) == {
        "corpus": str(donnees / "corpus"),
        "canonique": str(donnees / "canonique"),
        "chroma": str(donnees / "chroma"),
        "bm25": str(donnees / "chroma" / "bm25.pkl"),
        "collection": "essai_docs",
        "base_sql": str(donnees / "essai.db"),
        "gouvernance_serveur": str(donnees / "gouvernance.db"),
        "gouvernance_front": str(donnees / "gouvernance.db"),
        "journal": str(donnees / "appels.jsonl"),
    }
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run python -m pytest tests/test_enseigne_raccordement.py -v`
Expected: FAIL — `AttributeError: module 'front.depot' has no attribute 'CHEMIN_GOUVERNANCE_DB'` dans le `stderr` affiché.

- [ ] **Step 3: `sorabel_rag/ingestion.py`**

`RACINE` n'y sert plus qu'aux deux chemins : la supprimer. `Path` reste utilisé (annotations).

Remplacer :

```python
from .extraction import EXTRACTEURS
from .modeles import (
    LIBELLES_ALERTES,
    SCHEMA_VERSION,
    DocumentCanonique,
    cle_de_tri_version,
    hacher_fichier,
)

RACINE = Path(__file__).resolve().parent.parent
CORPUS = RACINE / "data" / "corpus"
SORTIE = RACINE / "data" / "canonique"
```

par :

```python
from sorabel_enseigne import enseigne_active

from .extraction import EXTRACTEURS
from .modeles import (
    LIBELLES_ALERTES,
    SCHEMA_VERSION,
    DocumentCanonique,
    cle_de_tri_version,
    hacher_fichier,
)

CORPUS = enseigne_active().chemins.corpus
SORTIE = enseigne_active().chemins.canonique
```

- [ ] **Step 4: `sorabel_rag/index.py`**

`RACINE` et l'import de `Path` n'y servent qu'aux chemins : les supprimer.

Remplacer :

```python
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

from .chunking import Chunk

load_dotenv()

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CHROMA = RACINE / "data" / "chroma"
CHEMIN_BM25 = RACINE / "data" / "chroma" / "bm25.pkl"
NOM_COLLECTION = "sorabel_docs"
```

par :

```python
import unicodedata

from dotenv import load_dotenv

from sorabel_enseigne import enseigne_active

from .chunking import Chunk

load_dotenv()

DOSSIER_CHROMA = enseigne_active().chemins.chroma
CHEMIN_BM25 = DOSSIER_CHROMA / "bm25.pkl"
# Une collection par enseigne : deux index ne se mélangent pas même si un `.toml` faisait
# pointer deux enseignes vers le même dossier Chroma.
NOM_COLLECTION = enseigne_active().collection
```

- [ ] **Step 5: `sorabel_sql/execution.py`**

Remplacer :

```python
import time
from pathlib import Path

CHEMIN_DB = Path(__file__).resolve().parent.parent / "data" / "sorabel.db"
```

par :

```python
import time

from sorabel_enseigne import enseigne_active

CHEMIN_DB = enseigne_active().chemins.base_sql
```

- [ ] **Step 6: `gouvernance/journal.py`**

Remplacer :

```python
from datetime import datetime, timezone
from pathlib import Path

CHEMIN_JOURNAL = Path(__file__).resolve().parent.parent / "logs" / "appels.jsonl"
```

par :

```python
from datetime import datetime, timezone

from sorabel_enseigne import enseigne_active

# Un journal par enseigne en local ; en production (SORABEL_JOURNAL=stdout), chaque
# serveur MCP écrit sur sa propre sortie et Cloud Logging les distingue par service.
CHEMIN_JOURNAL = enseigne_active().chemins.journal
```

- [ ] **Step 7: `mcp_server/serveur.py`**

`Path` reste utilisé (annotation de `construire_serveur`) ; seule `RACINE` disparaît.

Remplacer :

```python
from gouvernance.perimetre import Perimetre

from .authentification import VerificateurJeton
from .tools import enregistrer_tools

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_GOUVERNANCE_DB = RACINE / "gouvernance" / "gouvernance.db"
```

par :

```python
from gouvernance.perimetre import Perimetre
from sorabel_enseigne import enseigne_active

from .authentification import VerificateurJeton
from .tools import enregistrer_tools

CHEMIN_GOUVERNANCE_DB = enseigne_active().chemins.gouvernance
```

- [ ] **Step 8: `front/depot.py`**

`RACINE` et l'import de `Path` disparaissent ; le chemin devient une constante nommée, lue dans l'enseigne du processus.

Remplacer :

```python
import functools
from pathlib import Path

from gouvernance.depots import choisir_depot
from gouvernance.modeles import CodeTool, charger_matrice
from gouvernance.perimetre import Perimetre

RACINE = Path(__file__).resolve().parent.parent


@functools.lru_cache(maxsize=1)
def _matrice():
    return charger_matrice(RACINE / "gouvernance" / "gouvernance.db")
```

par :

```python
import functools

from gouvernance.depots import choisir_depot
from gouvernance.modeles import CodeTool, charger_matrice
from gouvernance.perimetre import Perimetre
from sorabel_enseigne import enseigne_active

# La matrice est commune à toutes les enseignes (mêmes profils, tools, collections et
# colonnes sensibles) : le front mutualisé lit celle de son enseigne de processus, quelle
# que soit l'enseigne choisie en session.
CHEMIN_GOUVERNANCE_DB = enseigne_active().chemins.gouvernance


@functools.lru_cache(maxsize=1)
def _matrice():
    return charger_matrice(CHEMIN_GOUVERNANCE_DB)
```

Puis, dans `depot_identites()`, remplacer :

```python
    return choisir_depot(
        RACINE / "gouvernance" / "gouvernance.db",
        profils_valides=frozenset(_matrice().profils),
    )
```

par :

```python
    return choisir_depot(
        CHEMIN_GOUVERNANCE_DB,
        profils_valides=frozenset(_matrice().profils),
    )
```

- [ ] **Step 9: `scripts/seed_gouvernance.py`**

Remplacer :

```python
from gouvernance.seed import peupler

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_DB = RACINE / "gouvernance" / "gouvernance.db"
```

par :

```python
from gouvernance.seed import peupler
from sorabel_enseigne import enseigne_active

CHEMIN_DB = enseigne_active().chemins.gouvernance
```

- [ ] **Step 10: `scripts/demo_mcp_http.py`**

Remplacer :

```python
from mcp_server.tools import enregistrer_tools

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_GOUVERNANCE_DB = RACINE / "gouvernance" / "gouvernance.db"
```

par :

```python
from mcp_server.tools import enregistrer_tools
from sorabel_enseigne import enseigne_active

CHEMIN_GOUVERNANCE_DB = enseigne_active().chemins.gouvernance
```

- [ ] **Step 11: Vérifier qu'aucun chemin de données ne reste codé en dur**

Run: `grep -rn --include=*.py -E '"data"|"gouvernance" / "gouvernance.db"|"logs"' sorabel_rag sorabel_sql gouvernance mcp_server front scripts`
Expected: aucune ligne.

- [ ] **Step 12: Lancer le test de raccordement et les instantanés**

Run: `uv run python -m pytest tests/test_enseigne_raccordement.py tests/test_enseigne_sorabel_inchangee.py -v`
Expected: `10 passed`.

- [ ] **Step 13: Lancer toute la suite**

Run: `uv run python -m pytest -q`
Expected: `203 passed`.

- [ ] **Step 14: Commit**

```bash
git add sorabel_rag/ingestion.py sorabel_rag/index.py sorabel_sql/execution.py gouvernance/journal.py mcp_server/serveur.py front/depot.py scripts/seed_gouvernance.py scripts/demo_mcp_http.py tests/test_enseigne_raccordement.py
git commit -m "refactor(enseigne): chemins de donnees lus dans l'enseigne active

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Raccorder les textes métier à l'enseigne active

**Files:**
- Modify: `sorabel_rag/generation.py:9-19`, `sorabel_rag/extraction.py:12-53` et `:112`, `sorabel_sql/generation.py:9-24`, `sorabel_sql/tools.py:7-36`, `sorabel_sql/schema.py` (fichier complet)
- Test: `tests/test_sql_schema_enseigne.py` ; ajout dans `tests/test_enseigne_raccordement.py`

**Interfaces:**
- Consumes: `enseigne_active()`, `Enseigne.presentation`, `Enseigne.pied_de_page`, `Enseigne.nom_base`, `Enseigne.commentaires_sql` (Task 2) ; `PREAMBULE` et `_executer` de `tests/test_enseigne_raccordement.py` (Task 3).
- Produces :
  - `sorabel_rag.extraction.PIED_DE_PAGE: str`
  - `sorabel_sql.schema.valider_commentaires(commentaires: Mapping[str, str]) -> None` — `ValueError` sur une clé `"table.colonne"` inconnue.
  - `sorabel_sql.schema.COMMENTAIRES_ENSEIGNE: Mapping[str, str]`
  - `sorabel_sql.schema._table_commentee(table, colonnes_interdites, commentaires=None) -> str` — `commentaires=None` signifie ceux de l'enseigne active. `schema_commente(perimetre)` garde sa signature.

- [ ] **Step 1: Écrire les tests unitaires du schéma qui échouent**

```python
# tests/test_sql_schema_enseigne.py
"""Commentaires de schéma par enseigne : la structure SQL est commune, le vocabulaire
métier (catégories, entrepôts, segments) vient de enseigne.toml."""

import pytest

from sorabel_sql.schema import _table_commentee, valider_commentaires


def test_un_commentaire_d_enseigne_remplace_celui_du_moteur():
    table = _table_commentee("stocks", frozenset(), {"stocks.entrepot": "LAUWIN | MONTLUEL"})
    assert "  entrepot TEXT,  -- LAUWIN | MONTLUEL" in table


def test_sans_commentaire_d_enseigne_une_colonne_metier_reste_sans_vocabulaire():
    """Une enseigne qui oublie ses entrepôts ne doit pas hériter de ceux de Sorabel."""
    table = _table_commentee("stocks", frozenset(), {})
    assert "  entrepot TEXT," in table
    assert "LILLE" not in table


def test_une_cle_de_commentaire_inconnue_est_refusee():
    with pytest.raises(ValueError, match="produit.categorie"):
        valider_commentaires({"produit.categorie": "Femme | Homme"})
```

- [ ] **Step 2: Ajouter le test de raccordement des textes**

Ajouter à la fin de `tests/test_enseigne_raccordement.py` :

```python
SCRIPT_TEXTES = PREAMBULE + """
from sorabel_rag import extraction
from sorabel_rag import generation as generation_rag
from sorabel_sql import generation as generation_sql
from sorabel_sql import schema, tools
tools.generer = lambda question, perimetre: None
print(json.dumps({
    "prompt_rag": generation_rag.PROMPT_SYSTEME,
    "prompt_sql": generation_sql.PROMPT_SYSTEME,
    "pied_de_page": extraction.PIED_DE_PAGE,
    "schema_stocks": schema._table_commentee("stocks", frozenset()),
    "hors_schema": tools.ask_database("question quelconque", None)["message"],
}))
"""


def test_chaque_module_lit_ses_textes_dans_l_enseigne_active(tmp_path, ecrire_enseigne):
    ecrire_enseigne(tmp_path, "essai", (tmp_path / "donnees").as_posix())
    textes = _executer(SCRIPT_TEXTES, tmp_path)
    assert textes["prompt_rag"].startswith("Tu es l'assistant documentaire de essai. ")
    assert "LECTURE SEULE sur la base essai. Règles strictes" in textes["prompt_sql"]
    assert textes["pied_de_page"] == "Document essai"
    assert "  entrepot TEXT,  -- ENTREPOT-essai" in textes["schema_stocks"]
    assert textes["hors_schema"] == "Cette question ne correspond à aucune table de la base essai."
    assert "Sorabel" not in textes["prompt_rag"] + textes["prompt_sql"] + textes["schema_stocks"]
```

- [ ] **Step 3: Lancer les tests pour vérifier qu'ils échouent**

Deux lancements séparés : une erreur de collecte interrompt pytest avant tout autre test.

Run: `uv run python -m pytest tests/test_sql_schema_enseigne.py -v`
Expected: `Interrupted: 1 error during collection` — `ImportError: cannot import name 'valider_commentaires'`.

Run: `uv run python -m pytest tests/test_enseigne_raccordement.py -v`
Expected: `test_chaque_module_lit_ses_textes_dans_l_enseigne_active` FAIL (`AttributeError: module 'sorabel_rag.extraction' has no attribute 'PIED_DE_PAGE'` dans le `stderr` affiché) ; le test des chemins (Task 3) reste PASS.

- [ ] **Step 4: `sorabel_rag/generation.py`**

Remplacer :

```python
from sorabel_llm.client import completer
```

par :

```python
from sorabel_enseigne import enseigne_active
from sorabel_llm.client import completer
```

Puis remplacer la première ligne de `PROMPT_SYSTEME` :

```python
    "Tu es l'assistant documentaire de Sorabel, distributeur B2B de matériel électrique. "
```

par :

```python
    f"Tu es {enseigne_active().presentation}. "
```

Les trois lignes suivantes de `PROMPT_SYSTEME` ne changent pas.

- [ ] **Step 5: `sorabel_rag/extraction.py`**

Remplacer :

```python
from pypdf import PdfReader

from .modeles import (
```

par :

```python
from pypdf import PdfReader

from sorabel_enseigne import enseigne_active

from .modeles import (
```

Après la ligne `SEUILS_LONGUEUR = {TYPE_FICHE: 200, TYPE_NOTICE: 200, TYPE_NOTE: 100, TYPE_SAV: 200}`, ajouter :

```python

# Ligne de pied de page des fiches PDF (« Document Sorabel - diffusion interne… »), propre
# à l'enseigne : du bruit à écarter de la section Identification.
PIED_DE_PAGE = enseigne_active().pied_de_page
```

Dans `extraire_fiche`, remplacer :

```python
        and not ligne.startswith("Document Sorabel")
```

par :

```python
        and not ligne.startswith(PIED_DE_PAGE)
```

- [ ] **Step 6: `sorabel_sql/generation.py`**

Remplacer :

```python
from sorabel_llm.client import completer
```

par :

```python
from sorabel_enseigne import enseigne_active
from sorabel_llm.client import completer
```

Puis transformer `PROMPT_SYSTEME` en f-string, en ne changeant **que** le préfixe `f` et le nom de la base. Remplacer :

```python
PROMPT_SYSTEME = """Tu traduis une question en langage naturel en une requête SQLite en LECTURE \
SEULE sur la base Sorabel. Règles strictes :
```

par :

```python
PROMPT_SYSTEME = f"""Tu traduis une question en langage naturel en une requête SQLite en LECTURE \
SEULE sur la base {enseigne_active().nom_base}. Règles strictes :
```

Les lignes suivantes de `PROMPT_SYSTEME` ne changent pas (elles ne contiennent aucune accolade). `EXEMPLES` ne change pas : le format `REF-XXXX` est commun aux enseignes.

- [ ] **Step 7: `sorabel_sql/tools.py`**

Remplacer :

```python
import re

from .execution import executer
```

par :

```python
import re

from sorabel_enseigne import enseigne_active

from .execution import executer
```

Puis, dans `ask_database`, remplacer :

```python
            "message": "Cette question ne correspond à aucune table de la base Sorabel.",
```

par :

```python
            "message": f"Cette question ne correspond à aucune table de la base {enseigne_active().nom_base}.",
```

- [ ] **Step 8: `sorabel_sql/schema.py` — fichier complet**

Les commentaires porteurs de vocabulaire métier (`produits.categorie`, `produits.unite`, `stocks.entrepot`, `clients.id`, `clients.segment`) sont vidés ici : ils viennent désormais de `[sql.commentaires]`. Les laisser en défaut ferait hériter Kiabi des entrepôts de Sorabel.

```python
"""Schéma SQL commenté envoyé au LLM, filtré par le périmètre du profil (E5).

Pas un CREATE TABLE brut : chaque colonne porte un commentaire qui dit ce qu'elle signifie,
pas seulement son type. Le schéma est construit à partir du périmètre, pas tronqué après
coup — on ne peut pas générer du SQL sur une colonne qu'on ignore.

Tables, colonnes et types sont communs à toutes les enseignes ; le vocabulaire métier
(catégories, entrepôts, segments…) vient de `[sql.commentaires]` dans enseigne.toml.
"""

from __future__ import annotations

from collections.abc import Mapping

from sorabel_enseigne import enseigne_active

# (nom, type SQLite, commentaire — vide si le nom de colonne se suffit à lui-même, ou si le
# commentaire est propre à l'enseigne)
COLONNES: dict[str, list[tuple[str, str, str]]] = {
    "produits": [
        ("ref", "TEXT PRIMARY KEY", "référence commerciale REF-XXXX, clé vers le corpus documentaire"),
        ("nom", "TEXT", "libellé commercial"),
        ("categorie", "TEXT", ""),
        ("fabricant", "TEXT", ""),
        ("unite", "TEXT", ""),
        ("prix_vente_ht", "REAL", "prix public HT"),
        ("prix_achat_ht", "REAL", "prix d'achat fournisseur"),
        ("marge_pct", "REAL", "taux de marge"),
        ("actif", "INTEGER", "1 = au catalogue"),
    ],
    "stocks": [
        ("id", "INTEGER PRIMARY KEY", ""),
        ("ref", "TEXT", "clé vers produits.ref"),
        ("entrepot", "TEXT", ""),
        ("quantite", "INTEGER", ""),
        ("seuil_reappro", "INTEGER", "en dessous, réapprovisionnement nécessaire"),
    ],
    "clients": [
        ("id", "TEXT PRIMARY KEY", ""),
        ("raison_sociale", "TEXT", ""),
        ("segment", "TEXT", ""),
        ("ville", "TEXT", ""),
        ("email", "TEXT", ""),
    ],
    "commandes": [
        ("id", "TEXT PRIMARY KEY", "ex. 'CMD-2025-0004'"),
        ("client_id", "TEXT", "clé vers clients.id"),
        ("date_commande", "TEXT", "ISO 'AAAA-MM-JJ' — utiliser strftime() pour les agrégations temporelles"),
        ("statut", "TEXT", "annulee | en_attente | expediee | livree | preparee"),
        ("montant_ht", "REAL", ""),
    ],
    "ventes": [
        ("id", "INTEGER PRIMARY KEY", ""),
        ("commande_id", "TEXT", "clé vers commandes.id"),
        ("ref", "TEXT", "clé vers produits.ref"),
        ("quantite", "INTEGER", ""),
        ("prix_unitaire_ht", "REAL", ""),
        ("remise_pct", "REAL", ""),
        ("marge_ht", "REAL", "marge en valeur"),
    ],
}

ORDRE_TABLES = ["produits", "stocks", "clients", "commandes", "ventes"]


def valider_commentaires(commentaires: Mapping[str, str]) -> None:
    """Une clé mal orthographiée dans enseigne.toml (`produit.categorie`) serait sinon
    ignorée en silence : le LLM perdrait la liste des valeurs sans que rien ne casse."""
    connues = {f"{table}.{nom}" for table, colonnes in COLONNES.items() for nom, _, _ in colonnes}
    inconnues = sorted(set(commentaires) - connues)
    if inconnues:
        raise ValueError(f"commentaires SQL sur des colonnes inconnues : {', '.join(inconnues)}")


COMMENTAIRES_ENSEIGNE = enseigne_active().commentaires_sql
valider_commentaires(COMMENTAIRES_ENSEIGNE)


def _table_commentee(
    table: str,
    colonnes_interdites: frozenset[str],
    commentaires: Mapping[str, str] | None = None,
) -> str:
    commentaires = COMMENTAIRES_ENSEIGNE if commentaires is None else commentaires
    lignes = [f"CREATE TABLE {table} ("]
    colonnes_visibles = [c for c in COLONNES[table] if c[0] not in colonnes_interdites]
    for index, (nom, type_sql, commentaire_moteur) in enumerate(colonnes_visibles):
        commentaire = commentaires.get(f"{table}.{nom}", commentaire_moteur)
        virgule = "," if index < len(colonnes_visibles) - 1 else ""
        suffixe = f"  -- {commentaire}" if commentaire else ""
        lignes.append(f"  {nom} {type_sql}{virgule}{suffixe}")
    lignes.append(");")
    return "\n".join(lignes)


def schema_commente(perimetre) -> str:
    """Le schéma tel que le profil de `perimetre` le voit — mêmes tables, mêmes colonnes,
    mêmes valeurs types que ce qui est envoyé au modèle de génération SQL."""
    tables_autorisees = perimetre.tables_autorisees()
    morceaux = [
        _table_commentee(table, perimetre.colonnes_interdites(table))
        for table in ORDRE_TABLES
        if table in tables_autorisees
    ]
    return "\n\n".join(morceaux)
```

- [ ] **Step 9: Vérifier qu'aucun texte Sorabel ne reste dans le moteur**

Run: `grep -rn --include=*.py -E "Document Sorabel|base Sorabel|matériel électrique|LILLE \| LYON|CLI-1000|PME \| artisan" sorabel_rag sorabel_sql`
Expected: aucune ligne.

- [ ] **Step 10: Lancer les nouveaux tests et les instantanés**

Run: `uv run python -m pytest tests/test_sql_schema_enseigne.py tests/test_enseigne_raccordement.py tests/test_enseigne_sorabel_inchangee.py -v`
Expected: `14 passed`. Si un instantané diverge, corriger `enseignes/sorabel/enseigne.toml` (jamais l'instantané).

- [ ] **Step 11: Lancer toute la suite**

Run: `uv run python -m pytest -q`
Expected: `207 passed`.

- [ ] **Step 12: Commit**

```bash
git add sorabel_rag/generation.py sorabel_rag/extraction.py sorabel_sql/generation.py sorabel_sql/tools.py sorabel_sql/schema.py tests/test_sql_schema_enseigne.py tests/test_enseigne_raccordement.py
git commit -m "refactor(enseigne): prompts, pied de page et vocabulaire SQL lus dans l'enseigne

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: CLI `sorabel_enseigne` et Makefile multi-enseigne

**Files:**
- Create: `sorabel_enseigne/__main__.py`
- Modify: `Makefile` (fichier complet), `.gitignore`
- Test: `tests/test_enseigne_cli.py`

**Interfaces:**
- Consumes: `sorabel_enseigne.RACINE`, `enseigne(nom)`, `enseignes_disponibles()`, `DOSSIER_ENSEIGNES` (Task 2) ; fixture `ecrire_enseigne`.
- Produces :
  - `sorabel_enseigne.__main__.variables_make(nom: str) -> str` — lignes `CLE := chemin/relatif` pour `GOUVERNANCE_DB`, `MANIFESTE`, `INDEX`, `CORPUS_DIR`, `JOURNAL` ; `SystemExit` si un chemin est hors du dépôt.
  - `sorabel_enseigne.__main__.main(arguments: list[str]) -> int` — `liste` → 0, `make <nom>` → 0, sinon usage sur stderr et 2.
  - Makefile : variable `ENSEIGNE` (défaut `sorabel`), exportée en `SORABEL_ENSEIGNE` ; fichier généré `.make/<enseigne>.mk` ; cible `make enseignes`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_enseigne_cli.py
"""python -m sorabel_enseigne : le pont entre enseigne.toml et le Makefile."""

import subprocess
import sys
from pathlib import Path

import pytest

import sorabel_enseigne
from sorabel_enseigne.__main__ import main, variables_make

RACINE = Path(__file__).resolve().parent.parent


def test_variables_make_de_sorabel_reprennent_ses_chemins_relatifs():
    assert variables_make("sorabel") == (
        "GOUVERNANCE_DB := gouvernance/gouvernance.db\n"
        "MANIFESTE := data/canonique/_manifeste.json\n"
        "INDEX := data/chroma/bm25.pkl\n"
        "CORPUS_DIR := data/corpus\n"
        "JOURNAL := logs/appels.jsonl\n"
    )


def test_un_chemin_hors_du_depot_est_refuse(tmp_path, monkeypatch, ecrire_enseigne):
    monkeypatch.setattr(sorabel_enseigne, "DOSSIER_ENSEIGNES", tmp_path)
    sorabel_enseigne.enseigne.cache_clear()
    ecrire_enseigne(tmp_path, "dehors", (tmp_path / "donnees").as_posix())
    try:
        with pytest.raises(SystemExit, match="hors du dépôt"):
            variables_make("dehors")
    finally:
        sorabel_enseigne.enseigne.cache_clear()


def test_liste_affiche_les_enseignes_disponibles(capsys):
    assert main(["liste"]) == 0
    assert "sorabel" in capsys.readouterr().out.split()


def test_des_arguments_invalides_affichent_l_usage(capsys):
    assert main(["inconnu"]) == 2
    assert "usage" in capsys.readouterr().err


def test_la_sortie_make_est_en_fins_de_ligne_unix():
    """Sous Windows, stdout en mode texte écrirait \\r\\n : Make lirait alors des chemins
    terminés par \\r, introuvables sur le disque."""
    sortie = subprocess.run(
        [sys.executable, "-m", "sorabel_enseigne", "make", "sorabel"],
        cwd=RACINE, capture_output=True, check=True,
    )
    assert b"\r" not in sortie.stdout
    assert sortie.stdout.startswith(b"GOUVERNANCE_DB := ")
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run python -m pytest tests/test_enseigne_cli.py -v`
Expected: erreur de collecte `ModuleNotFoundError: No module named 'sorabel_enseigne.__main__'`.

- [ ] **Step 3: Écrire `sorabel_enseigne/__main__.py`**

```python
"""`python -m sorabel_enseigne liste` : les enseignes disponibles.
`python -m sorabel_enseigne make <nom>` : les variables Make d'une enseigne.

Les chemins sont écrits RELATIFS à la racine du dépôt : Make ne sait pas manipuler un
chemin contenant une espace, et la racine en contient (« Sorabel - l'agent augmenté… »).
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import RACINE, enseigne, enseignes_disponibles


def _relatif(chemin: Path) -> str:
    try:
        return chemin.relative_to(RACINE).as_posix()
    except ValueError:
        raise SystemExit(f"{chemin} est hors du dépôt : Make ne peut pas l'utiliser") from None


def variables_make(nom: str) -> str:
    """Les noms `_manifeste.json` et `bm25.pkl` répètent ceux de sorabel_rag : ce module ne
    peut pas l'importer sans tirer tout le moteur dans chaque appel de Make."""
    chemins = enseigne(nom).chemins
    variables = {
        "GOUVERNANCE_DB": chemins.gouvernance,
        "MANIFESTE": chemins.canonique / "_manifeste.json",
        "INDEX": chemins.chroma / "bm25.pkl",
        "CORPUS_DIR": chemins.corpus,
        "JOURNAL": chemins.journal,
    }
    return "".join(f"{cle} := {_relatif(valeur)}\n" for cle, valeur in variables.items())


def main(arguments: list[str]) -> int:
    if arguments == ["liste"]:
        print("\n".join(enseignes_disponibles()))
        return 0
    if len(arguments) == 2 and arguments[0] == "make":
        print(variables_make(arguments[1]), end="")
        return 0
    print("usage : python -m sorabel_enseigne liste | make <enseigne>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    # Sous Windows, stdout en mode texte traduit \n en \r\n : redirigé vers .make/<nom>.mk,
    # chaque chemin finirait par \r et Make ne trouverait plus aucun fichier.
    sys.stdout.reconfigure(newline="\n")
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `uv run python -m pytest tests/test_enseigne_cli.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Ajouter `.make/` à `.gitignore`**

Après le bloc `logs/` de `.gitignore`, ajouter :

```gitignore

# Variables Make générées depuis enseignes/<nom>/enseigne.toml (python -m sorabel_enseigne)
.make/
```

- [ ] **Step 6: Réécrire le `Makefile`**

Remplacer le fichier entier par :

```make
# Sorabel Data Gateway — raccourcis de développement et de démonstration.
# `make` seul affiche l'aide. Détails du code : docs/DOSSIER_TECHNIQUE.md.

# Lancé depuis PowerShell ou cmd, GNU Make sous Windows retombe sur cmd.exe et aucune
# recette POSIX ne passe. On force le sh de Git for Windows, et on met ses outils (rm,
# find, awk…) en tête du PATH : sans ça, sh démarre sans /usr/bin. Chemin court 8.3
# parce que Make ne sait pas quoter un SHELL contenant une espace.
ifeq ($(OS),Windows_NT)
GIT_USR ?= $(firstword $(wildcard C:/PROGRA~1/Git/usr/bin C:/PROGRA~2/Git/usr/bin))
ifeq ($(GIT_USR),)
$(error Git for Windows introuvable : installer Git, ou passer GIT_USR=<dossier contenant sh.exe>)
endif
SHELL := $(GIT_USR)/sh.exe
export PATH := $(GIT_USR);$(PATH)
endif

# Les scripts impriment accents et pictogrammes : sans UTF-8 forcé, une console Windows
# en cp1252 lève UnicodeEncodeError au premier « é ».
export PYTHONUTF8 := 1

# Pas d'accent dans le texte des recettes (echo…) : sous Windows, Make transmet la ligne
# de commande à sh en page de code ANSI et « é » ressort « Ã© ». Les descriptions `##`
# ne sont pas concernées — awk les lit directement dans ce fichier.

# `uv run` synchronise l'environnement avant chaque commande : pas de venv à activer.
PY := uv run python

# L'enseigne choisit le jeu de données et les textes métier ; le moteur reste le même.
# Exportée pour que chaque recette Python lise la même (sorabel_enseigne).
ENSEIGNE ?= sorabel
export SORABEL_ENSEIGNE := $(ENSEIGNE)

ifeq ($(wildcard enseignes/$(ENSEIGNE)/enseigne.toml),)
$(error Enseigne inconnue : $(ENSEIGNE) (voir make enseignes))
endif

# Chemins de l'enseigne, générés depuis enseigne.toml — seule source de vérité. Make
# régénère un fichier inclus dont la source a changé, puis se relance : le `uv run` n'est
# payé qu'après une modification du .toml, pas à chaque commande.
include .make/$(ENSEIGNE).mk

.make/%.mk: enseignes/%/enseigne.toml sorabel_enseigne/__main__.py
	@mkdir -p .make
	@$(PY) -m sorabel_enseigne make $* > $@

# Une recette interrompue ne doit pas laisser un .mk vide, que Make inclurait ensuite.
.DELETE_ON_ERROR:

PROFIL ?= commercial
N      ?= 10

URL_FRONT  := https://sorabel-front-4g2lzykvia-ew.a.run.app
GCP_PROJET := sorabel-vitrine-2026
GCP_REGION := europe-west1

# Motifs grep -E : sorabel_llm accepte AZURE_OPENAI_DEPLOYMENT_NAME comme alias.
CLES_AZURE := AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY 'AZURE_OPENAI_DEPLOYMENT(_NAME)?' \
              AZURE_OPENAI_EMBEDDING_DEPLOYMENT AZURE_OPENAI_RERANK_DEPLOYMENT

# Différé (`=`) : au premier passage, CORPUS_DIR n'existe pas encore (le .mk se génère).
CORPUS = $(wildcard $(CORPUS_DIR)/*/*)

.DEFAULT_GOAL := help
.PHONY: help install enseignes verifier donnees reindexer test serveur demo contraste \
        demo-http inspecteur journal vitrine gcp-statut clean reset-donnees

##@ Mise en route

help: ## Affiche cette aide
	@awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
	  /^[a-z][a-z-]*:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "Enseigne active : $(ENSEIGNE) (ENSEIGNE=..., voir make enseignes)"
	@echo "Variables : PROFIL=support|commercial|dev|admin (actuel : $(PROFIL)), N=$(N)"

install: ## Installe les dépendances (uv sync, Python 3.12)
	uv sync

enseignes: ## Liste les enseignes disponibles (choisir avec ENSEIGNE=…)
	@$(PY) -m sorabel_enseigne liste

verifier: ## Contrôle avant démo : .env Azure, données de l'enseigne, front déployé joignable
	@echo "Enseigne : $(ENSEIGNE)"
	@echo "Azure : variables du .env"
	@for cle in $(CLES_AZURE); do \
	  if grep -Eq "^$$cle=." .env 2>/dev/null; then echo "  ok      $${cle%%(*}"; \
	  else echo "  VIDE    $${cle%%(*}"; fi; done
	@echo "Fichiers construits"
	@for f in $(GOUVERNANCE_DB) $(MANIFESTE) $(INDEX); do \
	  if [ -f $$f ]; then echo "  ok      $$f"; \
	  else echo "  ABSENT  $$f  -> make donnees ENSEIGNE=$(ENSEIGNE)"; fi; done
	@echo "Front Cloud Run (302 attendu : IAP redirige vers la connexion Google)"
	@code=$$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 $(URL_FRONT)); \
	  echo "  HTTP $$code  $(URL_FRONT)"

donnees: $(GOUVERNANCE_DB) $(MANIFESTE) $(INDEX) ## Construit matrice d'accès, canoniques et index de l'enseigne (seulement ce qui manque)

reindexer: $(MANIFESTE) ## Force la réindexation — obligatoire après un changement de déploiement d'embeddings
	$(PY) scripts/indexer.py

##@ Qualité

# Les tests portent sur le moteur avec Sorabel pour jeu de données (tests/conftest.py) :
# préparer les données d'une autre enseigne avant de les lancer n'aurait aucun sens.
ifeq ($(ENSEIGNE),sorabel)
test: $(GOUVERNANCE_DB) $(MANIFESTE) ## Lance la suite de tests (enseigne sorabel)
	$(PY) -m pytest -q
else
test:
	@echo "make test tourne sur l'enseigne sorabel : relancer sans ENSEIGNE=$(ENSEIGNE)"; exit 1
endif

##@ Démonstration locale (stdio, sans authentification)

demo: donnees .env ## Client MCP scripté : recherche doc, SQL, tentative d'écriture, schéma (PROFIL=…)
	$(PY) scripts/mcp_client.py --profil $(PROFIL)

contraste: donnees .env ## Même séquence en support puis en commercial : marges masquées puis visibles (E5)
	@for p in support commercial; do $(PY) scripts/mcp_client.py --profil $$p; done

journal: ## Derniers appels journalisés de l'enseigne, refus compris (N=…)
	@$(PY) -c "import json; \
	lignes = [json.loads(l) for l in open('$(JOURNAL)', encoding='utf-8')][-$(N):]; \
	[print(f\"{l['horodatage'][:19]}  {l['profil']:<10} {l['tool']:<16} {l['statut']:<13} {l.get('motif') or ''}\") for l in lignes]"

serveur: donnees .env ## Serveur MCP en stdio, profil figé au démarrage (PROFIL=…)
	SORABEL_PROFIL=$(PROFIL) $(PY) -m mcp_server.serveur

# L'Inspector ne transmet au serveur qu'une liste blanche de variables d'environnement :
# sans -e explicite, SORABEL_ENSEIGNE serait perdue et le serveur servirait Sorabel.
inspecteur: donnees .env ## MCP Inspector (navigateur) branché sur le serveur stdio (PROFIL=…)
	npx @modelcontextprotocol/inspector -e SORABEL_PROFIL=$(PROFIL) -e SORABEL_ENSEIGNE=$(ENSEIGNE) uv run python -m mcp_server.serveur

demo-http: donnees .env ## Serveur HTTP :8080 SANS authentification, pour un playground MCP (PROFIL=…)
	$(PY) scripts/demo_mcp_http.py --profil $(PROFIL)

##@ Production (GCP)

vitrine: ## Ouvre le poste de travail déployé (Cloud Run derrière IAP)
	$(PY) -m webbrowser $(URL_FRONT)

gcp-statut: ## État des services Cloud Run sorabel-mcp et sorabel-front
	gcloud run services list --project=$(GCP_PROJET) --region=$(GCP_REGION)

##@ Nettoyage

clean: ## Supprime caches Python, variables Make générées et journaux d'outils (*.log)
	find . -path ./.venv -prune -o -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .make
	rm -f *.log

reset-donnees: ## Supprime les données régénérables de l'enseigne — la reconstruction rappellera Azure
	rm -rf $(dir $(MANIFESTE)) $(dir $(INDEX)) $(GOUVERNANCE_DB)

# --- Fichiers construits ---------------------------------------------------------------

$(GOUVERNANCE_DB): gouvernance/seed.py
	$(PY) scripts/seed_gouvernance.py

$(MANIFESTE): $(CORPUS)
	$(PY) scripts/ingerer.py

# Prérequis d'ordre seul (après `|`) : l'index se construit s'il manque, mais une
# ingestion plus récente ne le périme pas. Chaque réindexation paie les embeddings Azure,
# et l'ingestion réécrit le manifeste même quand le corpus n'a pas bougé — une dépendance
# par date relancerait l'indexation à chaque fois. Pour la forcer : `make reindexer`.
$(INDEX): | $(MANIFESTE)
	$(PY) scripts/indexer.py

.env:
	@cp .env.example .env
	@echo ".env absent : copie de .env.example faite. Renseigner les variables AZURE_*, puis relancer."
	@exit 1
```

- [ ] **Step 7: Vérifier le Makefile (Bash)**

Run et attendus, dans l'ordre :

```bash
rm -rf .make && make help | tail -2
```
Expected : `Enseigne active : sorabel (ENSEIGNE=..., voir make enseignes)` puis la ligne `Variables : …`.

```bash
cat .make/sorabel.mk
```
Expected : exactement les 5 lignes de `test_variables_make_de_sorabel_reprennent_ses_chemins_relatifs`.

```bash
make enseignes
```
Expected : `sorabel`.

```bash
make -n donnees
```
Expected : `make: Nothing to be done for 'donnees'.` (données Sorabel déjà construites : aucune réindexation).

```bash
make -n inspecteur | grep -c "SORABEL_ENSEIGNE=sorabel"
```
Expected : `1`.

```bash
make demo ENSEIGNE=inconnue; echo "code=$?"
```
Expected : `Makefile:<numéro de ligne>: *** Enseigne inconnue : inconnue (voir make enseignes).  Stop.` puis `code=2`.

```bash
make journal N=2
```
Expected : deux lignes de journal (`horodatage  profil  tool  statut …`).

- [ ] **Step 8: Vérifier le Makefile depuis PowerShell**

Lancer avec l'outil PowerShell : `make verifier`
Expected : `Enseigne : sorabel`, cinq `ok` pour Azure, trois `ok` pour les fichiers, `HTTP 302`.

- [ ] **Step 9: Lancer toute la suite via Make**

Run: `make test`
Expected: `212 passed`.

- [ ] **Step 10: Commit**

```bash
git add sorabel_enseigne/__main__.py tests/test_enseigne_cli.py Makefile .gitignore
git commit -m "feat(make): variable ENSEIGNE, chemins generes depuis enseigne.toml

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Documentation et vérification de fin de sous-chantier

**Files:**
- Modify: `CLAUDE.md`, `docs/DOSSIER_TECHNIQUE.md`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: la documentation du contrat `sorabel_enseigne`, lue par les sous-chantiers 2 à 4.

- [ ] **Step 1: `CLAUDE.md` — variables d'environnement**

Dans la section **Conventions**, au début du paragraphe qui commence par `**Variables d'environnement** — `, insérer juste après `**Variables d'environnement** — ` :

```markdown
`SORABEL_ENSEIGNE` : l'enseigne servie par le processus (`sorabel` par défaut, une seule par
processus) — sa config est `enseignes/<nom>/enseigne.toml`, lue par `sorabel_enseigne` et
nulle part ailleurs ; en local, `make … ENSEIGNE=<nom>` la positionne.
```

- [ ] **Step 2: `CLAUDE.md` — données et décompte des tests**

Dans la section **Données**, ajouter à la fin :

```markdown
`enseignes/<nom>/enseigne.toml` : chemins des données et textes métier d'une enseigne
(prompts, pied de page PDF, vocabulaire du schéma SQL). Sorabel y déclare les chemins
historiques ci-dessus ; `tests/test_enseigne_sorabel_inchangee.py` garantit qu'elle se
comporte exactement comme avant le socle multi-enseigne (tag `sorabel-v1`).
```

Puis remplacer chaque occurrence de `182 tests` (`grep -n "182" CLAUDE.md` pour les trouver) par `212 tests`.

- [ ] **Step 3: `docs/DOSSIER_TECHNIQUE.md` — arborescence (§2)**

Dans le bloc de code de l'arborescence, juste avant la ligne `sorabel_llm/`, insérer :

```
sorabel_enseigne/    une enseigne par processus, sans dépendance vers le reste du projet
  __init__.py        enseigne_active(), enseigne(nom), enseignes_disponibles(),
                     charger_enseigne(chemin)
  __main__.py        python -m sorabel_enseigne liste | make <nom> (variables du Makefile)

enseignes/
  sorabel/enseigne.toml  chemins historiques (data/, gouvernance/, logs/), prompts,
                     pied de page PDF, vocabulaire du schéma SQL
```

Puis remplacer la ligne `tests/               26 fichiers, 182 tests` par `tests/               32 fichiers, 212 tests`. Le décompte d'origine compte tous les `.py` du dossier (`__init__.py` compris) : `ls tests/*.py | wc -l` doit afficher `32` (26 + 5 fichiers de test + `conftest.py`).

- [ ] **Step 4: `docs/DOSSIER_TECHNIQUE.md` — contrat (§3)**

Remplacer `Les trois interfaces à ne pas casser.` par `Les quatre interfaces à ne pas casser.`, puis insérer, juste avant `### Forme de retour des tools` :

```markdown
### `sorabel_enseigne` — une enseigne par processus

Le moteur lit ses chemins et ses textes métier dans `enseigne_active()`, jamais en dur :

```python
enseigne_active() -> Enseigne        # SORABEL_ENSEIGNE, « sorabel » par défaut
enseigne(nom: str) -> Enseigne       # par nom, en cache — pour le front mutualisé
enseignes_disponibles() -> list[str]
```

`Enseigne.chemins` porte `corpus`, `canonique`, `chroma`, `base_sql`, `gouvernance`,
`journal` ; `Enseigne` porte aussi `collection`, `presentation`, `pied_de_page`, `nom_base`
et `commentaires_sql`. Les constantes de module (`CORPUS`, `CHEMIN_DB`, `PROMPT_SYSTEME`…)
gardent leur nom mais sont évaluées à l'import depuis l'enseigne active : changer
d'enseigne, c'est changer de processus. Une enseigne inconnue arrête le processus — jamais
de repli silencieux sur Sorabel.
```

- [ ] **Step 5: Vérification de fin — tests**

Run: `make test`
Expected: `212 passed`.

- [ ] **Step 6: Vérification de fin — démonstration réelle**

Run: `make demo PROFIL=dev`
Expected : la ligne `titres trouvés :` liste les mêmes titres qu'avant le socle multi-enseigne :
`['Cheville à frapper 6×40 (boîte 200)', 'Interrupteur différentiel 300 mA type A', 'Câble R2V 3G1,5 mm² (100 m)', 'Disjoncteur tétrapolaire triphasé 40 A courbe C', 'Tableau électrique 4 rangées 52 modules']`.
Ce run appelle Azure (embeddings et reranking) : quelques centimes. Signaler tout écart plutôt que le corriger seul.

- [ ] **Step 7: Vérification de fin — périmètre respecté**

```bash
git diff sorabel-v1 --stat -- Dockerfile cloudbuild.yaml front/app_client.py front/passerelle.py
git ls-files | grep -ic kiabi
```
Expected : aucune ligne pour la première commande ; `0` pour la seconde.

- [ ] **Step 8: Commit**

```bash
git add CLAUDE.md docs/DOSSIER_TECHNIQUE.md
git commit -m "docs: documenter le socle multi-enseigne (SORABEL_ENSEIGNE, sorabel_enseigne)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
