# Phase 4 — Gouvernance : matrice d'accès, `Perimetre`, journalisation (chantier 3, partie données)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire la matrice d'accès à 4 profils (`support`, `commercial`, `dev`, `admin`)
conforme à `docs/conception_mcp.md` §2 : base `gouvernance.db` peuplée par script d'admin,
validation Pydantic bloquante (E5), objet `Perimetre` consommé par les tools, journalisation
JSONL, puis câblage du `Perimetre` dans le retrieval RAG (Phase 2) et confirmation qu'il
s'intègre sans modification dans le Text-to-SQL (Phase 3, déjà duck-typé pour ça).

**Architecture:** Un nouveau package `gouvernance/` (stockage + validation + `Perimetre` +
journal), puis deux modifications ciblées de code existant :
`sorabel_rag/recherche.py` (filtre de collections) et `sorabel_rag/generation.py` (paramètre
`perimetre` optionnel, rétrocompatible).

**Tech Stack:** `pydantic>=2.0` (déjà installé, 2.13.4 — vérifié par `import pydantic`),
`sqlite3` (standard).

## Global Constraints

- Langue du code de domaine, messages et tests : français.
- **`gouvernance.db` est une base distincte de `data/sorabel.db`**, ouverte en lecture seule
  par tout code qui n'est pas `gouvernance/seed.py`. Le seed script est le SEUL point
  d'écriture — la Gateway n'écrit jamais dans aucune base à l'exécution.
- **E5 est un invariant vérifié par Pydantic, pas seulement par les données** : tout profil
  qui n'est ni `commercial` ni `admin` et qui a accès à `produits` doit exclure
  `prix_achat_ht` et `marge_pct` ; tout profil de ce type avec accès à `ventes` doit exclure
  `marge_ht`. Une matrice qui viole cette règle doit lever `pydantic.ValidationError` au
  chargement, jamais silencieusement laisser passer.
- **Simplification assumée et documentée** (pas un oubli) : le profil `dev` voit le schéma des
  5 tables SQL (`lecture_seule_schema=1` en base, à titre documentaire) mais
  `Perimetre.tables_autorisees()` renvoie quand même l'ensemble complet pour `dev` — la
  barrière réelle contre tout accès aux données de `dev` est `peut_appeler("ask_database")`
  qui vaut `False` pour ce profil (appliquée en Phase 5, au niveau du tool). Ne pas ajouter de
  deuxième méthode `Perimetre` pour distinguer schéma/données : ce serait de la complexité
  non consommée par aucun tool de ce dépôt.
- `gouvernance.db` et `logs/` sont régénérables : à ignorer par git (Task 1).
- Aucun appel réseau ni LLM dans les tests de cette phase.
- Exécuter les tests avec `python -m pytest` depuis la racine du dépôt.

---

## File Structure

```
gouvernance/__init__.py        NOUVEAU : vide
gouvernance/schema.sql          NOUVEAU : les 6 tables (profils, tools, collections,
                                profil_tool, profil_collection, profil_table,
                                colonne_interdite, identites)
gouvernance/seed.py             NOUVEAU : peupler(chemin_db) — matrice exacte de conception_mcp.md
scripts/seed_gouvernance.py     NOUVEAU : appelle gouvernance.seed.peupler sur gouvernance/gouvernance.db
gouvernance/modeles.py          NOUVEAU : DroitsProfil (validateur E5), MatriceAcces, charger_matrice
gouvernance/perimetre.py        NOUVEAU : Perimetre, ProfilInconnu
gouvernance/journal.py          NOUVEAU : journaliser(...)
.gitignore                      MODIFIÉ : ajoute gouvernance/*.db et logs/
requirements.txt                MODIFIÉ : ajoute pydantic
sorabel_rag/recherche.py       MODIFIÉ : filtre_collections(), rechercher() accepte collections_autorisees
sorabel_rag/generation.py      MODIFIÉ : repondre() accepte perimetre=None (rétrocompatible)
tests/test_gouvernance_seed.py       NOUVEAU
tests/test_gouvernance_modeles.py    NOUVEAU
tests/test_gouvernance_perimetre.py  NOUVEAU
tests/test_gouvernance_journal.py    NOUVEAU
tests/test_recherche_collections.py  NOUVEAU
tests/test_generation.py             MODIFIÉ (lambdas de monkeypatch mises à jour, 2 tests ajoutés)
```

---

### Task 1: Schéma et peuplement de `gouvernance.db`

**Files:**
- Create: `gouvernance/__init__.py`
- Create: `gouvernance/schema.sql`
- Create: `gouvernance/seed.py`
- Create: `scripts/seed_gouvernance.py`
- Modify: `.gitignore`
- Test: `tests/test_gouvernance_seed.py`

**Interfaces:**
- Consumes: rien.
- Produces: `gouvernance.seed.peupler(chemin_db: Path) -> None` — Task 2
  (`gouvernance.modeles.charger_matrice`) lit la base que cette fonction produit.

- [ ] **Step 1: Ignorer les artefacts régénérables**

Dans `.gitignore`, ajouter :

```
# Gouvernance : régénérable par scripts/seed_gouvernance.py
gouvernance/*.db
logs/
```

- [ ] **Step 2: Écrire le schéma SQL**

Créer `gouvernance/__init__.py` (vide).

Créer `gouvernance/schema.sql` :

```sql
CREATE TABLE profils (
  code   TEXT PRIMARY KEY,
  libelle TEXT,
  actif  INTEGER DEFAULT 1
);

CREATE TABLE tools (
  code        TEXT PRIMARY KEY,
  description TEXT
);

CREATE TABLE collections (
  code    TEXT PRIMARY KEY,
  libelle TEXT
);

CREATE TABLE profil_tool (
  profil TEXT REFERENCES profils(code),
  tool   TEXT REFERENCES tools(code),
  PRIMARY KEY (profil, tool)
);

CREATE TABLE profil_collection (
  profil     TEXT REFERENCES profils(code),
  collection TEXT REFERENCES collections(code),
  PRIMARY KEY (profil, collection)
);

CREATE TABLE profil_table (
  profil               TEXT REFERENCES profils(code),
  table_sql            TEXT,
  lecture_seule_schema INTEGER DEFAULT 0,
  PRIMARY KEY (profil, table_sql)
);

CREATE TABLE colonne_interdite (
  profil    TEXT REFERENCES profils(code),
  table_sql TEXT,
  colonne   TEXT,
  motif     TEXT,
  PRIMARY KEY (profil, table_sql, colonne)
);

CREATE TABLE identites (
  sujet  TEXT PRIMARY KEY,
  profil TEXT REFERENCES profils(code),
  source TEXT
);
```

- [ ] **Step 3: Écrire le test qui échoue**

Créer `tests/test_gouvernance_seed.py` :

```python
"""Peuplement de gouvernance.db : la matrice exacte de docs/conception_mcp.md §2."""

import sqlite3

from gouvernance.seed import peupler


def _compter(connexion, requete, params=()):
    return connexion.execute(requete, params).fetchone()[0]


def test_quatre_profils_huit_tools_cinq_collections(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    connexion = sqlite3.connect(chemin)
    try:
        assert _compter(connexion, "SELECT COUNT(*) FROM profils") == 4
        assert _compter(connexion, "SELECT COUNT(*) FROM tools") == 8
        assert _compter(connexion, "SELECT COUNT(*) FROM collections") == 5
    finally:
        connexion.close()


def test_dev_na_pas_answer_question_ni_ask_database(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    connexion = sqlite3.connect(chemin)
    try:
        tools_dev = {
            r[0] for r in connexion.execute("SELECT tool FROM profil_tool WHERE profil = 'dev'")
        }
        assert tools_dev == {"search_docs", "get_document", "list_sources", "get_schema"}
    finally:
        connexion.close()


def test_support_na_pas_notes_confidentielles(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    connexion = sqlite3.connect(chemin)
    try:
        collections_support = {
            r[0] for r in connexion.execute(
                "SELECT collection FROM profil_collection WHERE profil = 'support'"
            )
        }
        assert "notes_confidentielles" not in collections_support
        assert "notes_operationnelles" in collections_support

        collections_commercial = {
            r[0] for r in connexion.execute(
                "SELECT collection FROM profil_collection WHERE profil = 'commercial'"
            )
        }
        assert "notes_confidentielles" in collections_commercial
    finally:
        connexion.close()


def test_colonnes_sensibles_exclues_pour_support_et_dev(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    connexion = sqlite3.connect(chemin)
    try:
        for profil in ("support", "dev"):
            colonnes = {
                r[0] for r in connexion.execute(
                    "SELECT colonne FROM colonne_interdite WHERE profil = ? AND table_sql = 'produits'",
                    (profil,),
                )
            }
            assert colonnes == {"prix_achat_ht", "marge_pct"}

        colonnes_commercial = {
            r[0] for r in connexion.execute(
                "SELECT colonne FROM colonne_interdite WHERE profil = 'commercial'"
            )
        }
        assert colonnes_commercial == set()  # aucune exclusion pour commercial
    finally:
        connexion.close()


def test_peupler_est_idempotent(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    peupler(chemin)  # ne doit pas lever (contrainte PRIMARY KEY sur un rejeu)
    connexion = sqlite3.connect(chemin)
    try:
        assert _compter(connexion, "SELECT COUNT(*) FROM profils") == 4
    finally:
        connexion.close()
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_gouvernance_seed.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'gouvernance'`

- [ ] **Step 5: Écrire `gouvernance/seed.py`**

```python
"""Peuple gouvernance.db avec la matrice d'accès exacte de docs/conception_mcp.md §2.

Script d'administration : c'est le SEUL endroit du dépôt qui écrit dans gouvernance.db. La
Gateway l'ouvre toujours en lecture seule à l'exécution — la matrice se modifie hors ligne.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = Path(__file__).resolve().parent / "schema.sql"

PROFILS = [
    ("support", "technicien du support client"),
    ("commercial", "commercial en clientèle"),
    ("dev", "développeur intégrant la Gateway"),
    ("admin", "exploitation"),
]

TOOLS = [
    ("answer_question", "Réponse rédigée avec sources, refuse hors corpus sans appel LLM."),
    ("search_docs", "Recherche hybride, extraits bruts et scores, aucune génération."),
    ("get_document", "Document complet, version courante par défaut."),
    ("list_sources", "Inventaire des documents et de leurs versions."),
    ("ask_database", "Requête SQL en langage naturel, lecture seule (E3)."),
    ("get_schema", "Schéma commenté tel que le profil le voit."),
    ("check_stock", "Stock par entrepôt pour une référence précise, zéro LLM."),
    ("order_status", "Statut, date et montant d'une commande, zéro LLM."),
]

COLLECTIONS = [
    ("fiches", "Fiches techniques"),
    ("notices", "Notices d'installation"),
    ("sav", "Procédures SAV"),
    ("notes_operationnelles", "Alerte qualité, logistique, retour terrain"),
    ("notes_confidentielles", "Politique tarifaire, réunion achats"),
]

PROFIL_TOOL: dict[str, set[str]] = {
    "answer_question": {"support", "commercial", "admin"},
    "search_docs": {"support", "commercial", "dev", "admin"},
    "get_document": {"support", "commercial", "dev", "admin"},
    "list_sources": {"support", "commercial", "dev", "admin"},
    "ask_database": {"support", "commercial", "admin"},
    "get_schema": {"support", "commercial", "dev", "admin"},
    "check_stock": {"support", "commercial", "admin"},
    "order_status": {"support", "commercial", "admin"},
}

PROFIL_COLLECTION: dict[str, set[str]] = {
    "fiches": {"support", "commercial", "dev", "admin"},
    "notices": {"support", "commercial", "dev", "admin"},
    "sav": {"support", "commercial", "dev", "admin"},
    "notes_operationnelles": {"support", "commercial", "admin"},
    "notes_confidentielles": {"commercial", "admin"},
}

TABLES_SQL = ["produits", "stocks", "clients", "commandes", "ventes"]

# Les 4 profils voient les 5 tables — `dev` en lecture de schéma seule (drapeau
# documentaire ; la barrière réelle est `peut_appeler("ask_database")`, cf. Global Constraints).
LECTURE_SEULE_SCHEMA = {("dev", table) for table in TABLES_SQL}

# Exigé par le validateur E5 (Task 2) pour tout profil hors commercial/admin ayant accès à
# la table concernée — dev y est soumis même s'il n'appelle jamais ask_database en pratique.
COLONNES_INTERDITES = [
    ("support", "produits", "prix_achat_ht", "colonne sensible E5"),
    ("support", "produits", "marge_pct", "colonne sensible E5"),
    ("support", "ventes", "marge_ht", "colonne sensible E5"),
    ("dev", "produits", "prix_achat_ht", "colonne sensible E5"),
    ("dev", "produits", "marge_pct", "colonne sensible E5"),
    ("dev", "ventes", "marge_ht", "colonne sensible E5"),
]


def peupler(chemin_db: Path) -> None:
    chemin_db = Path(chemin_db)
    chemin_db.parent.mkdir(parents=True, exist_ok=True)
    if chemin_db.exists():
        chemin_db.unlink()

    connexion = sqlite3.connect(chemin_db)
    try:
        connexion.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        connexion.executemany("INSERT INTO profils (code, libelle) VALUES (?, ?)", PROFILS)
        connexion.executemany("INSERT INTO tools (code, description) VALUES (?, ?)", TOOLS)
        connexion.executemany("INSERT INTO collections (code, libelle) VALUES (?, ?)", COLLECTIONS)

        for tool, profils in PROFIL_TOOL.items():
            connexion.executemany(
                "INSERT INTO profil_tool (profil, tool) VALUES (?, ?)",
                [(profil, tool) for profil in profils],
            )
        for collection, profils in PROFIL_COLLECTION.items():
            connexion.executemany(
                "INSERT INTO profil_collection (profil, collection) VALUES (?, ?)",
                [(profil, collection) for profil in profils],
            )
        for profil, _ in PROFILS:
            connexion.executemany(
                "INSERT INTO profil_table (profil, table_sql, lecture_seule_schema) VALUES (?, ?, ?)",
                [
                    (profil, table, int((profil, table) in LECTURE_SEULE_SCHEMA))
                    for table in TABLES_SQL
                ],
            )
        connexion.executemany(
            "INSERT INTO colonne_interdite (profil, table_sql, colonne, motif) VALUES (?, ?, ?, ?)",
            COLONNES_INTERDITES,
        )
        connexion.commit()
    finally:
        connexion.close()
```

Créer `scripts/seed_gouvernance.py` :

```python
"""Peuple gouvernance/gouvernance.db avec la matrice d'accès. À relancer après toute
modification de gouvernance/seed.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gouvernance.seed import peupler

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_DB = RACINE / "gouvernance" / "gouvernance.db"

if __name__ == "__main__":
    peupler(CHEMIN_DB)
    print(f"-> {CHEMIN_DB}")
```

- [ ] **Step 6: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_gouvernance_seed.py -v`
Expected: `5 passed`

- [ ] **Step 7: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `58 passed` (53 des Phases 1-3 + 5 de cette tâche)

- [ ] **Step 8: Commit**

```bash
git add gouvernance/__init__.py gouvernance/schema.sql gouvernance/seed.py \
        scripts/seed_gouvernance.py .gitignore tests/test_gouvernance_seed.py
git commit -m "feat(gouvernance): schéma et peuplement de gouvernance.db (matrice à 4 profils)"
```

---

### Task 2: Validation Pydantic de la matrice (E5 bloquante)

**Files:**
- Create: `gouvernance/modeles.py`
- Modify: `requirements.txt`
- Test: `tests/test_gouvernance_modeles.py`

**Interfaces:**
- Consumes: `gouvernance.seed.peupler(chemin_db)` (Task 1, pour les fixtures de test).
- Produces: `gouvernance.modeles.DroitsProfil` (Pydantic `BaseModel`, champs `code: str`,
  `tools: frozenset[CodeTool]`, `collections: frozenset[CodeCollection]`,
  `tables: frozenset[TableSql]`, `colonnes_interdites: dict[TableSql, frozenset[str]]`) ;
  `gouvernance.modeles.MatriceAcces` (`profils: dict[str, DroitsProfil]`) ;
  `gouvernance.modeles.charger_matrice(chemin_db: Path) -> MatriceAcces`. Task 3
  (`Perimetre`) consomme `MatriceAcces` et `DroitsProfil` tels que définis ici.

- [ ] **Step 1: Ajouter la dépendance**

Dans `requirements.txt`, ajouter à la fin :

```
# Gouvernance
pydantic>=2.0
```

- [ ] **Step 2: Écrire les tests qui échouent**

Créer `tests/test_gouvernance_modeles.py` :

```python
"""Validation Pydantic de la matrice d'accès : E5 est un invariant bloquant, pas une donnée."""

import pytest
from pydantic import ValidationError

from gouvernance.modeles import DroitsProfil, charger_matrice
from gouvernance.seed import peupler


def test_e5_leve_si_colonne_sensible_non_exclue_pour_support():
    with pytest.raises(ValidationError):
        DroitsProfil(
            code="support",
            tools=frozenset({"get_schema"}),
            collections=frozenset(),
            tables=frozenset({"produits"}),
            colonnes_interdites={},  # manque prix_achat_ht et marge_pct
        )


def test_e5_leve_si_exclusion_partielle():
    with pytest.raises(ValidationError):
        DroitsProfil(
            code="dev",
            tools=frozenset(),
            collections=frozenset(),
            tables=frozenset({"produits"}),
            colonnes_interdites={"produits": frozenset({"prix_achat_ht"})},  # marge_pct manque
        )


def test_e5_nexige_rien_pour_commercial_ni_admin():
    for profil in ("commercial", "admin"):
        droits = DroitsProfil(
            code=profil,
            tools=frozenset({"ask_database"}),
            collections=frozenset(),
            tables=frozenset({"produits", "ventes"}),
            colonnes_interdites={},
        )
        assert droits.colonnes_interdites == {}


def test_droits_profil_valide_passe():
    droits = DroitsProfil(
        code="support",
        tools=frozenset({"get_schema", "ask_database"}),
        collections=frozenset({"fiches"}),
        tables=frozenset({"produits"}),
        colonnes_interdites={"produits": frozenset({"prix_achat_ht", "marge_pct"})},
    )
    assert droits.tables == frozenset({"produits"})


def test_code_tool_inconnu_est_rejete():
    with pytest.raises(ValidationError):
        DroitsProfil(
            code="admin",
            tools=frozenset({"answer_questionn"}),  # faute de frappe
            collections=frozenset(),
            tables=frozenset(),
            colonnes_interdites={},
        )


def test_charger_matrice_depuis_gouvernance_db(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)

    matrice = charger_matrice(chemin)

    assert set(matrice.profils) == {"support", "commercial", "dev", "admin"}
    support = matrice.profils["support"]
    assert "ask_database" in support.tools
    assert "notes_confidentielles" not in support.collections
    assert support.colonnes_interdites["produits"] == frozenset({"prix_achat_ht", "marge_pct"})

    dev = matrice.profils["dev"]
    assert "ask_database" not in dev.tools
    assert "answer_question" not in dev.tools
```

- [ ] **Step 3: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_gouvernance_modeles.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'gouvernance.modeles'`

- [ ] **Step 4: Écrire `gouvernance/modeles.py`**

```python
"""Validation Pydantic de la matrice d'accès — chargée une fois au démarrage du serveur MCP.

Deux garanties : un code inconnu (faute de frappe dans gouvernance.db) fait échouer le
chargement, pas silencieusement à l'appel ; E5 est vérifiée par un validateur, pas seulement
espérée dans les données — si l'exclusion d'une colonne sensible manque, le chargement lève.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationInfo, field_validator

CodeTool = Literal[
    "answer_question", "search_docs", "get_document", "list_sources",
    "ask_database", "get_schema", "check_stock", "order_status",
]
CodeCollection = Literal[
    "fiches", "notices", "sav", "notes_operationnelles", "notes_confidentielles",
]
TableSql = Literal["produits", "stocks", "clients", "commandes", "ventes"]

COLONNES_SENSIBLES_OBLIGATOIRES: dict[str, frozenset[str]] = {
    "produits": frozenset({"prix_achat_ht", "marge_pct"}),
    "ventes": frozenset({"marge_ht"}),
}


class DroitsProfil(BaseModel):
    code: str
    tools: frozenset[CodeTool]
    collections: frozenset[CodeCollection]
    tables: frozenset[TableSql]
    colonnes_interdites: dict[TableSql, frozenset[str]]

    @field_validator("colonnes_interdites")
    @classmethod
    def colonnes_sensibles_couvertes(cls, valeur, info: ValidationInfo):
        if info.data.get("code") in ("commercial", "admin"):
            return valeur
        for table, colonnes_obligatoires in COLONNES_SENSIBLES_OBLIGATOIRES.items():
            if table in info.data.get("tables", frozenset()):
                manquantes = colonnes_obligatoires - valeur.get(table, frozenset())
                if manquantes:
                    raise ValueError(
                        f"E5 violée pour le profil {info.data.get('code')!r} : "
                        f"{table}.{sorted(manquantes)} non exclue(s)"
                    )
        return valeur


class MatriceAcces(BaseModel):
    profils: dict[str, DroitsProfil]


def charger_matrice(chemin_db: Path) -> MatriceAcces:
    """Lecture seule de gouvernance.db. Un code inconnu en base fait échouer Pydantic ici,
    au démarrage — jamais à l'appel d'un tool."""
    connexion = sqlite3.connect(f"file:{Path(chemin_db).as_posix()}?mode=ro", uri=True)
    try:
        codes_profils = [
            row[0] for row in connexion.execute("SELECT code FROM profils WHERE actif = 1")
        ]
        profils: dict[str, DroitsProfil] = {}
        for code in codes_profils:
            tools = {
                r[0] for r in connexion.execute(
                    "SELECT tool FROM profil_tool WHERE profil = ?", (code,)
                )
            }
            collections = {
                r[0] for r in connexion.execute(
                    "SELECT collection FROM profil_collection WHERE profil = ?", (code,)
                )
            }
            tables = {
                r[0] for r in connexion.execute(
                    "SELECT table_sql FROM profil_table WHERE profil = ?", (code,)
                )
            }
            colonnes_interdites: dict[str, set[str]] = {}
            for table, colonne in connexion.execute(
                "SELECT table_sql, colonne FROM colonne_interdite WHERE profil = ?", (code,)
            ):
                colonnes_interdites.setdefault(table, set()).add(colonne)

            profils[code] = DroitsProfil(
                code=code,
                tools=tools,
                collections=collections,
                tables=tables,
                colonnes_interdites={t: frozenset(c) for t, c in colonnes_interdites.items()},
            )
        return MatriceAcces(profils=profils)
    finally:
        connexion.close()
```

- [ ] **Step 5: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_gouvernance_modeles.py -v`
Expected: `6 passed`

- [ ] **Step 6: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `64 passed`

- [ ] **Step 7: Commit**

```bash
git add gouvernance/modeles.py requirements.txt tests/test_gouvernance_modeles.py
git commit -m "feat(gouvernance): validation Pydantic de la matrice, E5 bloquante au chargement"
```

---

### Task 3: L'objet `Perimetre`

**Files:**
- Create: `gouvernance/perimetre.py`
- Test: `tests/test_gouvernance_perimetre.py`

**Interfaces:**
- Consumes: `gouvernance.modeles.MatriceAcces`, `charger_matrice` (Task 2).
- Produces: `gouvernance.perimetre.Perimetre(profil: str, matrice: MatriceAcces)` avec
  `.peut_appeler(tool: str) -> bool`, `.collections_autorisees() -> frozenset[str]`,
  `.tables_autorisees() -> frozenset[str]`, `.colonnes_interdites(table: str) -> frozenset[str]`
  — exactement le contrat duck-typé attendu par `sorabel_sql` (Phase 3) et par
  `sorabel_rag.generation.repondre()` (Task 6 de cette phase). `ProfilInconnu` (`Exception`).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_gouvernance_perimetre.py` :

```python
"""Perimetre : les droits d'un profil, sous la forme que les tools consomment."""

import pytest

from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre, ProfilInconnu
from gouvernance.seed import peupler


@pytest.fixture
def matrice(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    return charger_matrice(chemin)


def test_support_peut_appeler_ask_database_mais_pas_de_colonnes_sensibles(matrice):
    perimetre = Perimetre("support", matrice)
    assert perimetre.peut_appeler("ask_database") is True
    assert perimetre.tables_autorisees() == frozenset(
        {"produits", "stocks", "clients", "commandes", "ventes"}
    )
    assert perimetre.colonnes_interdites("produits") == frozenset({"prix_achat_ht", "marge_pct"})
    assert perimetre.colonnes_interdites("ventes") == frozenset({"marge_ht"})
    assert perimetre.colonnes_interdites("stocks") == frozenset()


def test_dev_ne_peut_pas_appeler_ask_database_ni_answer_question(matrice):
    perimetre = Perimetre("dev", matrice)
    assert perimetre.peut_appeler("ask_database") is False
    assert perimetre.peut_appeler("answer_question") is False
    assert perimetre.peut_appeler("search_docs") is True


def test_support_na_pas_les_notes_confidentielles(matrice):
    perimetre = Perimetre("support", matrice)
    assert "notes_confidentielles" not in perimetre.collections_autorisees()
    assert "notes_operationnelles" in perimetre.collections_autorisees()


def test_commercial_na_aucune_colonne_interdite(matrice):
    perimetre = Perimetre("commercial", matrice)
    assert perimetre.colonnes_interdites("produits") == frozenset()
    assert perimetre.colonnes_interdites("ventes") == frozenset()


def test_profil_inconnu_leve(matrice):
    with pytest.raises(ProfilInconnu):
        Perimetre("stagiaire", matrice)
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_gouvernance_perimetre.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'gouvernance.perimetre'`

- [ ] **Step 3: Écrire `gouvernance/perimetre.py`**

```python
"""Le Perimetre : les droits d'un profil, sous la forme que les tools consomment.

Les tools ne lisent ni gouvernance.db ni le modèle Pydantic : ils reçoivent un Perimetre
construit une fois par appel et lui posent des questions. Duck-typé pour satisfaire le
contrat déjà attendu par sorabel_sql (Phase 3) sans qu'aucune ligne de ce package ne
dépende de `gouvernance`.
"""

from __future__ import annotations

from .modeles import MatriceAcces


class ProfilInconnu(Exception):
    pass


class Perimetre:
    def __init__(self, profil: str, matrice: MatriceAcces):
        if profil not in matrice.profils:
            raise ProfilInconnu(f"profil inconnu : {profil!r}")
        self.profil = profil
        self._droits = matrice.profils[profil]

    def peut_appeler(self, tool: str) -> bool:
        return tool in self._droits.tools

    def collections_autorisees(self) -> frozenset[str]:
        return self._droits.collections

    def tables_autorisees(self) -> frozenset[str]:
        return self._droits.tables

    def colonnes_interdites(self, table: str) -> frozenset[str]:
        return self._droits.colonnes_interdites.get(table, frozenset())
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_gouvernance_perimetre.py -v`
Expected: `5 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `69 passed`

- [ ] **Step 6: Commit**

```bash
git add gouvernance/perimetre.py tests/test_gouvernance_perimetre.py
git commit -m "feat(gouvernance): Perimetre (droits d'un profil, contrat duck-typé)"
```

---

### Task 4: Journalisation (E4, E5)

**Files:**
- Create: `gouvernance/journal.py`
- Test: `tests/test_gouvernance_journal.py`

**Interfaces:**
- Consumes: rien.
- Produces: `gouvernance.journal.journaliser(*, profil, tool, autorise, statut, entrees, sql=None,
  n_lignes=0, duree_ms=0.0, motif=None, code=None) -> None` — Phase 5 (serveur MCP) l'appelle
  après chaque tool, autorisé ou refusé.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/test_gouvernance_journal.py` :

```python
"""Journalisation (E4, E5) : une ligne JSON par appel, en ajout seul."""

import json

from gouvernance import journal


def test_journaliser_ecrit_une_ligne_json_valide(tmp_path, monkeypatch):
    chemin = tmp_path / "appels.jsonl"
    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", chemin)

    journal.journaliser(
        profil="support", tool="ask_database", autorise=False, statut="non_autorise",
        entrees={"question": "quelle est la marge sur REF-1024 ?"},
        sql=None, n_lignes=0, duree_ms=3.2, motif="produits.marge_pct hors périmètre",
        code="COLONNE_INTERDITE",
    )

    lignes = chemin.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 1
    ligne = json.loads(lignes[0])
    assert ligne["profil"] == "support"
    assert ligne["tool"] == "ask_database"
    assert ligne["autorise"] is False
    assert ligne["statut"] == "non_autorise"
    assert ligne["code"] == "COLONNE_INTERDITE"
    assert ligne["motif"] == "produits.marge_pct hors périmètre"
    assert "horodatage" in ligne


def test_journaliser_ajoute_sans_ecraser(tmp_path, monkeypatch):
    chemin = tmp_path / "appels.jsonl"
    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", chemin)

    journal.journaliser(profil="admin", tool="get_schema", autorise=True, statut="ok", entrees={})
    journal.journaliser(profil="admin", tool="get_schema", autorise=True, statut="ok", entrees={})

    lignes = chemin.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 2


def test_journaliser_cree_le_dossier_logs_sil_manque(tmp_path, monkeypatch):
    chemin = tmp_path / "sous_dossier_absent" / "appels.jsonl"
    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", chemin)

    journal.journaliser(profil="dev", tool="search_docs", autorise=True, statut="ok", entrees={})

    assert chemin.exists()
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_gouvernance_journal.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'gouvernance.journal'`

- [ ] **Step 3: Écrire `gouvernance/journal.py`**

```python
"""Journalisation (E4, E5) : une ligne JSON par appel, en ajout seul.

Tout appel est journalisé, autorisé comme refusé. On trace la question, la requête et le
volume — jamais le contenu des résultats : un journal ne doit pas devenir une copie de la
base sans les contrôles d'accès de la base.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

CHEMIN_JOURNAL = Path(__file__).resolve().parent.parent / "logs" / "appels.jsonl"


def journaliser(
    *,
    profil: str,
    tool: str,
    autorise: bool,
    statut: str,
    entrees: dict,
    sql: str | None = None,
    n_lignes: int = 0,
    duree_ms: float = 0.0,
    motif: str | None = None,
    code: str | None = None,
) -> None:
    ligne = {
        "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profil": profil,
        "tool": tool,
        "autorise": autorise,
        "statut": statut,
        "code": code,
        "entrees": entrees,
        "sql": sql,
        "n_lignes": n_lignes,
        "duree_ms": duree_ms,
        "motif": motif,
    }
    CHEMIN_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with CHEMIN_JOURNAL.open("a", encoding="utf-8") as fichier:
        fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_gouvernance_journal.py -v`
Expected: `3 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `72 passed`

- [ ] **Step 6: Commit**

```bash
git add gouvernance/journal.py tests/test_gouvernance_journal.py
git commit -m "feat(gouvernance): journalisation JSONL (E4, E5) — tout appel, autorisé ou refusé"
```

---

### Task 5: Filtrer le retrieval RAG par collections de gouvernance

**Files:**
- Modify: `sorabel_rag/recherche.py`
- Test: `tests/test_recherche_collections.py`

**Interfaces:**
- Consumes: rien de `gouvernance` (couplage évité — cette fonction prend un `frozenset[str]`
  brut, pas un `Perimetre`).
- Produces: `sorabel_rag.recherche.filtre_collections(collections_autorisees: frozenset[str] | None) -> dict | None`.
  `sorabel_rag.recherche.rechercher(...)` gagne un paramètre `collections_autorisees: frozenset[str] | None = None`
  (dernier paramètre, après `inclure_versions_anciennes` — rétrocompatible, `None` = comportement
  actuel inchangé). Task 6 appelle `rechercher(..., collections_autorisees=perimetre.collections_autorisees())`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_recherche_collections.py` :

```python
"""Traduction des collections de gouvernance en filtre Chroma (E5 appliquée au RAG)."""

from sorabel_rag.recherche import filtre_collections


def test_aucune_restriction_si_none():
    assert filtre_collections(None) is None


def test_une_seule_collection_simple():
    assert filtre_collections(frozenset({"fiches"})) == {"type_document": "fiche_technique"}


def test_notes_operationnelles_filtre_sur_sous_type():
    filtre = filtre_collections(frozenset({"notes_operationnelles"}))
    assert filtre == {
        "$and": [
            {"type_document": "note_interne"},
            {"sous_type": {"$in": ["alerte_qualite", "logistique", "retour_terrain"]}},
        ]
    }


def test_notes_confidentielles_filtre_sur_sous_type():
    filtre = filtre_collections(frozenset({"notes_confidentielles"}))
    assert filtre == {
        "$and": [
            {"type_document": "note_interne"},
            {"sous_type": {"$in": ["politique_tarifaire", "reunion_achat"]}},
        ]
    }


def test_plusieurs_collections_sont_combinees_en_or():
    filtre = filtre_collections(frozenset({"fiches", "notices"}))
    assert "$or" in filtre
    assert {"type_document": "fiche_technique"} in filtre["$or"]
    assert {"type_document": "notice"} in filtre["$or"]


def test_aucune_collection_autorisee_ne_matche_jamais():
    filtre = filtre_collections(frozenset())
    assert filtre == {"type_document": "__aucune_collection_autorisee__"}
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_recherche_collections.py -v`
Expected: `FAILED` — `ImportError: cannot import name 'filtre_collections'`

- [ ] **Step 3: Modifier `sorabel_rag/recherche.py`**

Ajouter, juste après les constantes existantes (après la ligne `PREFERENCE_TYPE_SUR_REFERENCE_SEULE`,
avant `_reranker = None`) :

```python
# Une "collection" de gouvernance n'est pas une collection Chroma : c'est un regroupement
# métier (chantier 3) qui se traduit en filtre sur type_document (+ sous_type pour distinguer
# les deux familles de notes — cf. docs/conception_mcp.md §2).
SOUS_TYPES_OPERATIONNELS = frozenset({"logistique", "alerte_qualite", "retour_terrain"})
SOUS_TYPES_CONFIDENTIELS = frozenset({"politique_tarifaire", "reunion_achat"})

CONDITION_COLLECTION: dict[str, dict] = {
    "fiches": {"type_document": "fiche_technique"},
    "notices": {"type_document": "notice"},
    "sav": {"type_document": "procedure_sav"},
    "notes_operationnelles": {
        "$and": [
            {"type_document": "note_interne"},
            {"sous_type": {"$in": sorted(SOUS_TYPES_OPERATIONNELS)}},
        ]
    },
    "notes_confidentielles": {
        "$and": [
            {"type_document": "note_interne"},
            {"sous_type": {"$in": sorted(SOUS_TYPES_CONFIDENTIELS)}},
        ]
    },
}


def filtre_collections(collections_autorisees: frozenset[str] | None) -> dict | None:
    """`None` = aucune restriction (profil non gouverné, comportement historique)."""
    if collections_autorisees is None:
        return None
    conditions = [
        CONDITION_COLLECTION[c] for c in collections_autorisees if c in CONDITION_COLLECTION
    ]
    if not conditions:
        return {"type_document": "__aucune_collection_autorisee__"}  # ne matche jamais
    return conditions[0] if len(conditions) == 1 else {"$or": conditions}
```

Modifier `_filtre_chroma` (juste avant `rechercher`) pour y intégrer ce filtre :

```python
def _filtre_chroma(
    inclure_versions_anciennes: bool,
    type_document: str | None,
    collections_autorisees: frozenset[str] | None = None,
) -> dict | None:
    conditions = []
    if not inclure_versions_anciennes:
        conditions.append({"est_version_courante": True})
    if type_document:
        conditions.append({"type_document": type_document})
    filtre_gouvernance = filtre_collections(collections_autorisees)
    if filtre_gouvernance:
        conditions.append(filtre_gouvernance)
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}
```

Modifier la signature de `rechercher` et l'appel à `_filtre_chroma` :

```python
def rechercher(
    requete: str,
    k: int = 5,
    config: str = "hybride_rerank",
    profondeur: int = PROFONDEUR,
    type_document: str | None = None,
    inclure_versions_anciennes: bool = False,
    collections_autorisees: frozenset[str] | None = None,
) -> list[Resultat]:
    """`config` ∈ {dense, hybride, hybride_rerank} — les trois configurations de l'éval.
    `collections_autorisees` : `None` = aucune restriction ; sinon un sous-ensemble de
    {fiches, notices, sav, notes_operationnelles, notes_confidentielles} (gouvernance, E5)."""
    collection = ouvrir_collection()
    filtre = _filtre_chroma(inclure_versions_anciennes, type_document, collections_autorisees)
```

(Le reste du corps de `rechercher` est inchangé — seule la ligne `filtre = _filtre_chroma(...)`
gagne le troisième argument.)

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_recherche_collections.py -v`
Expected: `6 passed`

- [ ] **Step 5: Lancer toute la suite (aucune régression sur les tests de recherche existants)**

Run: `python -m pytest -v`
Expected: `78 passed`

- [ ] **Step 6: Commit**

```bash
git add sorabel_rag/recherche.py tests/test_recherche_collections.py
git commit -m "feat(rag): filtrer le retrieval par collections de gouvernance (E5)"
```

---

### Task 6: Brancher le `Perimetre` dans `answer_question`

**Files:**
- Modify: `sorabel_rag/generation.py`
- Modify: `tests/test_generation.py`

**Interfaces:**
- Consumes: `sorabel_rag.recherche.rechercher(..., collections_autorisees=...)` (Task 5) ; un
  objet `perimetre` duck-typé exposant `.collections_autorisees() -> frozenset[str] | None`
  (même contrat que Task 3 de cette phase, satisfait par `gouvernance.perimetre.Perimetre`).
- Produces: `sorabel_rag.generation.repondre(question: str, k: int = 5, perimetre=None) -> dict`
  — `perimetre=None` (par défaut) préserve exactement le comportement de la Phase 2 (aucune
  restriction). Phase 5 (serveur MCP) appelle toujours avec un `Perimetre` réel.

- [ ] **Step 1: Modifier `sorabel_rag/generation.py`**

Remplacer la fonction `repondre` par :

```python
def repondre(question: str, k: int = 5, perimetre=None) -> dict:
    """Le tool `answer_question` du catalogue MCP (chantier 1).

    `perimetre=None` : aucune restriction de collection (comportement de la Phase 2). Un
    `Perimetre` réel (Phase 4) restreint le retrieval aux collections autorisées du profil —
    appliqué DANS le retrieval, pas en post-filtrage des résultats (E5)."""
    collections = perimetre.collections_autorisees() if perimetre is not None else None
    resultats = rechercher(
        question, k=k, config="hybride_rerank", collections_autorisees=collections
    )
    if not resultats or resultats[0].score < SEUIL_REFUS:
        return {
            "statut": "hors_corpus",
            "message": "Je ne trouve pas de réponse à cette question dans le corpus documentaire.",
        }

    reponse = completer(_construire_prompt(question, resultats))
    return {
        "statut": "ok",
        "reponse": reponse,
        "citations": _construire_citations(resultats),
        "chunks_utilises": [r.chunk_id for r in resultats],
    }
```

(`_construire_prompt` et `_construire_citations` sont inchangées.)

- [ ] **Step 2: Mettre à jour les tests existants et en ajouter deux**

Remplacer le contenu de `tests/test_generation.py` par :

```python
"""Génération de réponse RAG : refus déterministe (E1), citations construites en code,
et restriction par périmètre de gouvernance (Phase 4)."""

import sorabel_rag.generation as generation
from sorabel_rag.recherche import Resultat


def _resultat(score, doc_id="fiche_technique:REF-1024:v2.1", chunk_id=None, **meta_extra):
    meta = {
        "doc_id": doc_id,
        "titre": "Disjoncteur différentiel 30mA",
        "type_document": "fiche_technique",
        "reference": "REF-1024",
        "date": "2025-01-10",
        **meta_extra,
    }
    return Resultat(chunk_id or f"{doc_id}#0", "corps du chunk", score, meta)


def test_hors_corpus_sous_le_seuil_naspelle_pas_le_llm(monkeypatch):
    appele = False

    def _completer_espion(messages):
        nonlocal appele
        appele = True
        return "ne devrait jamais être retourné"

    monkeypatch.setattr(
        generation, "rechercher",
        lambda question, k, config, collections_autorisees=None: [_resultat(1e-6)],
    )
    monkeypatch.setattr(generation, "completer", _completer_espion)

    resultat = generation.repondre("capitale de l'Australie ?")

    assert resultat["statut"] == "hors_corpus"
    assert not appele


def test_hors_corpus_quand_aucun_resultat(monkeypatch):
    monkeypatch.setattr(
        generation, "rechercher",
        lambda question, k, config, collections_autorisees=None: [],
    )
    resultat = generation.repondre("question quelconque")
    assert resultat["statut"] == "hors_corpus"


def test_reponse_ok_construit_les_citations_depuis_les_metadonnees(monkeypatch):
    monkeypatch.setattr(
        generation, "rechercher",
        lambda question, k, config, collections_autorisees=None: [_resultat(0.9)],
    )
    monkeypatch.setattr(generation, "completer", lambda messages: "Le REF-1024 supporte 30mA.")

    resultat = generation.repondre("Quel est le seuil du REF-1024 ?")

    assert resultat["statut"] == "ok"
    assert resultat["reponse"] == "Le REF-1024 supporte 30mA."
    assert resultat["citations"] == [
        {"titre": "Disjoncteur différentiel 30mA", "reference": "REF-1024",
         "date": "2025-01-10", "type_document": "fiche_technique"}
    ]
    assert resultat["chunks_utilises"] == ["fiche_technique:REF-1024:v2.1#0"]


def test_citations_dedupliquees_par_document(monkeypatch):
    resultats = [
        _resultat(0.9, doc_id="procedure_sav:proc-casse-transport-01:v2.0", chunk_id="a#0",
                  titre="Procédure casse transport", type_document="procedure_sav",
                  reference="", date="2025-02-01"),
        _resultat(0.8, doc_id="procedure_sav:proc-casse-transport-01:v2.0", chunk_id="a#1",
                  titre="Procédure casse transport", type_document="procedure_sav",
                  reference="", date="2025-02-01"),
    ]
    monkeypatch.setattr(
        generation, "rechercher",
        lambda question, k, config, collections_autorisees=None: resultats,
    )
    monkeypatch.setattr(generation, "completer", lambda messages: "réponse")

    resultat = generation.repondre("comment déclarer une casse transport ?")

    assert len(resultat["citations"]) == 1
    assert resultat["citations"][0]["reference"] is None  # chaîne vide -> None
    assert resultat["chunks_utilises"] == ["a#0", "a#1"]


def test_perimetre_none_ne_restreint_pas_les_collections(monkeypatch):
    captures = {}

    def _rechercher_espion(question, k, config, collections_autorisees=None):
        captures["collections"] = collections_autorisees
        return [_resultat(0.9)]

    monkeypatch.setattr(generation, "rechercher", _rechercher_espion)
    monkeypatch.setattr(generation, "completer", lambda messages: "réponse")

    generation.repondre("question quelconque")

    assert captures["collections"] is None


class _PerimetreFactice:
    def collections_autorisees(self):
        return frozenset({"fiches", "notices"})


def test_perimetre_fourni_restreint_les_collections(monkeypatch):
    captures = {}

    def _rechercher_espion(question, k, config, collections_autorisees=None):
        captures["collections"] = collections_autorisees
        return [_resultat(0.9)]

    monkeypatch.setattr(generation, "rechercher", _rechercher_espion)
    monkeypatch.setattr(generation, "completer", lambda messages: "réponse")

    generation.repondre("question quelconque", perimetre=_PerimetreFactice())

    assert captures["collections"] == frozenset({"fiches", "notices"})
```

- [ ] **Step 3: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_generation.py -v`
Expected: `6 passed`

- [ ] **Step 4: Lancer toute la suite (Phase 1 à 4 complètes)**

Run: `python -m pytest -v`
Expected: `80 passed`

- [ ] **Step 5: Commit**

```bash
git add sorabel_rag/generation.py tests/test_generation.py
git commit -m "feat(rag): brancher le Perimetre dans answer_question (rétrocompatible)"
```
