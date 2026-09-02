# Phase 3 — Text-to-SQL en lecture seule (chantier 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire le package `sorabel_sql/` conforme à `docs/conception_sql.md` : schéma
commenté filtré par profil, détection d'intention sensible avant génération, génération SQL
via le LLM partagé, validation à quatre barrières, exécution en lecture seule avec `LIMIT` et
timeout, et les quatre tools (`ask_database`, `get_schema`, `check_stock`, `order_status`).

**Architecture:** Six modules à responsabilité unique, composés uniquement dans `tools.py`.
Aucun de ces modules ne dépend de la gouvernance complète (Phase 4, pas encore construite) :
partout où le périmètre d'un profil est nécessaire, les fonctions attendent un objet
`perimetre` **duck-typé** — n'importe quel objet exposant `.tables_autorisees() -> frozenset[str]`
et `.colonnes_interdites(table: str) -> frozenset[str]`. Cette phase teste avec un double de
test minimal ; la Phase 4 fournira le vrai type (`gouvernance.perimetre.Perimetre`) qui
satisfait ce même contrat sans qu'aucune ligne de `sorabel_sql/` ne change.

**Tech Stack:** `sqlite3` (bibliothèque standard), `sorabel_llm.client.completer` (Phase 2).

## Global Constraints

- Langue du code de domaine, messages et tests : français.
- **Quatre barrières indépendantes** (E3) : connexion `mode=ro` (barrière 1, appliquée par
  SQLite lui-même — teste-la en appelant `execution.executer()` directement avec une requête
  d'écriture, sans passer par `validation.valider()`, pour prouver qu'elle protège même si le
  reste est contourné), une seule instruction + `SELECT`/`WITH` + mots-clés interdits +
  tables/colonnes dans le périmètre (barrières 2-3), `LIMIT` par défaut (barrière 4a), timeout
  d'exécution (barrière 4b).
- **Colonnes sensibles E5** : exactement `produits.prix_achat_ht`, `produits.marge_pct`,
  `ventes.marge_ht`. `produits.prix_vente_ht` n'est PAS sensible (prix public).
- **Paramètre lié, jamais concaténé** pour `check_stock` et `order_status` — ce sont des
  requêtes figées, aucune interpolation de chaîne dans le SQL.
- **Le SQL exécuté ou rejeté est toujours renvoyé** dans la réponse (`sql` — jamais omis, même
  en cas de refus).
- Statuts normalisés à utiliser tels quels : `ok`, `hors_schema`, `non_autorise`,
  `refuse_ecriture`. Le statut `ambigu` (détection de questions à interprétations multiples,
  §4 de `docs/conception_sql.md`) est explicitement **hors périmètre de cette phase** — ne pas
  l'implémenter, ne pas le mentionner dans le code produit.
- Aucun appel réseau dans les tests de `schema.py`, `lexique_sensible.py`, `validation.py`,
  `execution.py`, `tools.py` — seul `generation.py` touche le LLM, et ses tests monkeypatchent
  `sorabel_llm.client.completer`. `execution.py` et `tools.py` touchent la vraie base locale
  `data/sorabel.db` (lecture seule) — ce n'est pas un appel réseau, c'est le sujet même du module.
- Exécuter les tests avec `python -m pytest` depuis la racine du dépôt.

---

## Constaté avant ce plan (utilisé pour écrire le schéma et le lexique)

Introspection de `data/sorabel.db` (5 tables, colonnes confirmées par `PRAGMA table_info`) :
`commandes.statut` ∈ `{annulee, en_attente, expediee, livree, preparee}` ;
`clients.segment` ∈ `{PME, artisan, grand compte, collectivité}` ; `stocks.entrepot` ∈
`{LILLE, LYON, NANTES}` ; `produits.categorie` a 9 valeurs (`Protection électrique`, `EPI`,
`Câblage`, `Outillage électroportatif`, `Visserie`, `Outillage à main`, `Distribution`,
`Éclairage`, `Mesure`) ; `date_commande` couvre `2025-09-04` → `2026-08-19` ;
`SELECT COUNT(*) FROM commandes WHERE strftime('%m', date_commande) = '04'` renvoie **27**
(test d'acceptance du brief).

## File Structure

```
sorabel_sql/__init__.py       NOUVEAU : vide
sorabel_sql/schema.py          NOUVEAU : schema_commente(perimetre) -> str
sorabel_sql/lexique_sensible.py NOUVEAU : question_sensible(question) -> bool
sorabel_sql/validation.py      NOUVEAU : valider(sql, perimetre) -> str, ValidationEchouee
sorabel_sql/execution.py       NOUVEAU : executer(sql, params=()) -> dict
sorabel_sql/generation.py      NOUVEAU : generer(question, perimetre) -> str | None, QuestionSensible
sorabel_sql/tools.py           NOUVEAU : ask_database, get_schema, check_stock, order_status
tests/test_sql_schema.py       NOUVEAU
tests/test_sql_lexique.py      NOUVEAU
tests/test_sql_validation.py   NOUVEAU
tests/test_sql_execution.py    NOUVEAU
tests/test_sql_generation.py   NOUVEAU
tests/test_sql_tools.py        NOUVEAU
```

---

### Task 1: Schéma commenté filtré par profil

**Files:**
- Create: `sorabel_sql/__init__.py`
- Create: `sorabel_sql/schema.py`
- Test: `tests/test_sql_schema.py`

**Interfaces:**
- Consumes: un objet `perimetre` exposant `.tables_autorisees() -> frozenset[str]` (sous-
  ensemble de `{"produits", "stocks", "clients", "commandes", "ventes"}`) et
  `.colonnes_interdites(table: str) -> frozenset[str]` — duck-typing, satisfait par un double
  de test ici et par `gouvernance.perimetre.Perimetre` en Phase 4.
- Produces: `sorabel_sql.schema.schema_commente(perimetre) -> str` — Task 5 (génération) et
  Task 6 (`get_schema`) l'appellent telle quelle.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `sorabel_sql/__init__.py` (vide).

Créer `tests/test_sql_schema.py` :

```python
"""Schéma SQL commenté, filtré par le périmètre du profil (E5)."""

from sorabel_sql.schema import schema_commente


class _PerimetreFactice:
    def __init__(self, tables, colonnes_interdites=None):
        self._tables = frozenset(tables)
        self._colonnes_interdites = colonnes_interdites or {}

    def tables_autorisees(self):
        return self._tables

    def colonnes_interdites(self, table):
        return frozenset(self._colonnes_interdites.get(table, ()))


def test_schema_ne_contient_que_les_tables_autorisees():
    perimetre = _PerimetreFactice(["produits", "stocks"])
    schema = schema_commente(perimetre)
    assert "CREATE TABLE produits" in schema
    assert "CREATE TABLE stocks" in schema
    assert "CREATE TABLE clients" not in schema
    assert "CREATE TABLE commandes" not in schema
    assert "CREATE TABLE ventes" not in schema


def test_schema_exclut_les_colonnes_interdites_du_profil_support():
    perimetre = _PerimetreFactice(
        ["produits", "ventes"],
        colonnes_interdites={
            "produits": {"prix_achat_ht", "marge_pct"},
            "ventes": {"marge_ht"},
        },
    )
    schema = schema_commente(perimetre)
    assert "prix_achat_ht" not in schema
    assert "marge_pct" not in schema
    assert "marge_ht" not in schema
    # Le prix public reste visible : il n'est pas sensible.
    assert "prix_vente_ht" in schema


def test_schema_profil_commercial_contient_les_colonnes_sensibles():
    perimetre = _PerimetreFactice(["produits", "ventes"])
    schema = schema_commente(perimetre)
    assert "prix_achat_ht" in schema
    assert "marge_pct" in schema
    assert "marge_ht" in schema


def test_schema_contient_les_valeurs_types_des_enumerations():
    perimetre = _PerimetreFactice(["commandes", "clients", "stocks", "produits"])
    schema = schema_commente(perimetre)
    for valeur in ("annulee", "en_attente", "expediee", "livree", "preparee"):
        assert valeur in schema
    for valeur in ("PME", "artisan", "collectivité", "grand compte"):
        assert valeur in schema
    for valeur in ("LILLE", "LYON", "NANTES"):
        assert valeur in schema
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_sql_schema.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'sorabel_sql'`

- [ ] **Step 3: Écrire `sorabel_sql/schema.py`**

```python
"""Schéma SQL commenté envoyé au LLM, filtré par le périmètre du profil (E5).

Pas un CREATE TABLE brut : chaque colonne porte un commentaire qui dit ce qu'elle signifie,
pas seulement son type. Le schéma est construit à partir du périmètre, pas tronqué après
coup — on ne peut pas générer du SQL sur une colonne qu'on ignore.
"""

from __future__ import annotations

# (nom, type SQLite, commentaire — vide si le nom de colonne se suffit à lui-même)
COLONNES: dict[str, list[tuple[str, str, str]]] = {
    "produits": [
        ("ref", "TEXT PRIMARY KEY", "référence commerciale REF-XXXX, clé vers le corpus documentaire"),
        ("nom", "TEXT", "libellé commercial"),
        ("categorie", "TEXT", "Protection électrique | EPI | Câblage | Outillage électroportatif | "
                              "Visserie | Outillage à main | Distribution | Éclairage | Mesure"),
        ("fabricant", "TEXT", ""),
        ("unite", "TEXT", "pièce | conditionnement"),
        ("prix_vente_ht", "REAL", "prix public HT"),
        ("prix_achat_ht", "REAL", "prix d'achat fournisseur"),
        ("marge_pct", "REAL", "taux de marge"),
        ("actif", "INTEGER", "1 = au catalogue"),
    ],
    "stocks": [
        ("id", "INTEGER PRIMARY KEY", ""),
        ("ref", "TEXT", "clé vers produits.ref"),
        ("entrepot", "TEXT", "LILLE | LYON | NANTES"),
        ("quantite", "INTEGER", ""),
        ("seuil_reappro", "INTEGER", "en dessous, réapprovisionnement nécessaire"),
    ],
    "clients": [
        ("id", "TEXT PRIMARY KEY", "ex. 'CLI-1000'"),
        ("raison_sociale", "TEXT", ""),
        ("segment", "TEXT", "PME | artisan | collectivité | grand compte"),
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


def _table_commentee(table: str, colonnes_interdites: frozenset[str]) -> str:
    lignes = [f"CREATE TABLE {table} ("]
    colonnes_visibles = [c for c in COLONNES[table] if c[0] not in colonnes_interdites]
    for index, (nom, type_sql, commentaire) in enumerate(colonnes_visibles):
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

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_sql_schema.py -v`
Expected: `4 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `20 passed` (16 des Phases 1-2 + 4 de cette tâche)

- [ ] **Step 6: Commit**

```bash
git add sorabel_sql/__init__.py sorabel_sql/schema.py tests/test_sql_schema.py
git commit -m "feat(sql): schéma commenté filtré par profil (get_schema)"
```

---

### Task 2: Lexique des intentions sensibles

**Files:**
- Create: `sorabel_sql/lexique_sensible.py`
- Test: `tests/test_sql_lexique.py`

**Interfaces:**
- Consumes: rien.
- Produces: `sorabel_sql.lexique_sensible.question_sensible(question: str) -> bool` — Task 5
  (`generation.generer`) l'appelle en tout premier, avant tout appel LLM.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/test_sql_lexique.py` :

```python
"""Détection lexicale d'intention sensible (E5) — asymétrie assumée : faux positif
récupérable, faux négatif inacceptable, donc le lexique est volontairement large."""

from sorabel_sql.lexique_sensible import question_sensible


def test_detecte_la_marge():
    assert question_sensible("quelle est la marge sur REF-1024 ?")


def test_detecte_le_prix_dachat():
    assert question_sensible("quel est le prix d'achat du REF-1024 ?")


def test_detecte_independamment_de_la_casse():
    assert question_sensible("Quelle MARGE fait-on sur ce produit ?")


def test_ne_detecte_pas_une_question_neutre():
    assert not question_sensible("combien de commandes en avril ?")


def test_ne_detecte_pas_le_prix_de_vente():
    assert not question_sensible("quel est le prix de vente du REF-1024 ?")
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

Run: `python -m pytest tests/test_sql_lexique.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'sorabel_sql.lexique_sensible'`

- [ ] **Step 3: Écrire `sorabel_sql/lexique_sensible.py`**

```python
"""Détection d'intention sensible AVANT génération (E5) — pas de barrière post-génération.

Volontairement large : un faux positif produit un refus clair et récupérable, un faux négatif
laisse fuiter une donnée sensible. L'asymétrie des conséquences dicte le réglage.
"""

LEXIQUE_SENSIBLE = [
    "marge", "marges",
    "prix d'achat", "prix achat", "coût d'achat", "cout d'achat",
    "rentabilité", "rentabilite",
]


def question_sensible(question: str) -> bool:
    q = question.lower()
    return any(mot in q for mot in LEXIQUE_SENSIBLE)
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_sql_lexique.py -v`
Expected: `5 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `25 passed`

- [ ] **Step 6: Commit**

```bash
git add sorabel_sql/lexique_sensible.py tests/test_sql_lexique.py
git commit -m "feat(sql): lexique des intentions sensibles (refus avant génération, E5)"
```

---

### Task 3: Validation à quatre barrières (2 et 3 : instruction, mots-clés, tables/colonnes)

**Files:**
- Create: `sorabel_sql/validation.py`
- Test: `tests/test_sql_validation.py`

**Interfaces:**
- Consumes: un objet `perimetre` (même contrat duck-typé que Task 1).
- Produces: `sorabel_sql.validation.valider(sql: str, perimetre) -> str` (retourne le SQL
  normalisé si valide) ; lève `sorabel_sql.validation.ValidationEchouee` sinon, avec deux
  attributs : `.statut` (`"refuse_ecriture" | "hors_schema" | "non_autorise"`) et `.message`
  (`str`). Task 6 (`tools.ask_database`) capture cette exception.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_sql_validation.py` :

```python
"""Barrières 2 et 3 (sur 4, E3) : une instruction, SELECT/WITH, mots-clés interdits,
tables et colonnes dans le périmètre du profil."""

import pytest

from sorabel_sql.validation import ValidationEchouee, valider


class _PerimetreFactice:
    def __init__(self, tables, colonnes_interdites=None):
        self._tables = frozenset(tables)
        self._colonnes_interdites = colonnes_interdites or {}

    def tables_autorisees(self):
        return self._tables

    def colonnes_interdites(self, table):
        return frozenset(self._colonnes_interdites.get(table, ()))


PERIMETRE_COMPLET = _PerimetreFactice(["produits", "stocks", "clients", "commandes", "ventes"])
PERIMETRE_SUPPORT = _PerimetreFactice(
    ["produits", "stocks", "clients", "commandes", "ventes"],
    colonnes_interdites={"produits": {"prix_achat_ht", "marge_pct"}, "ventes": {"marge_ht"}},
)


def test_requete_select_simple_passe():
    resultat = valider("SELECT COUNT(*) FROM commandes", PERIMETRE_COMPLET)
    assert resultat == "SELECT COUNT(*) FROM commandes"


def test_requete_with_passe():
    sql = "WITH t AS (SELECT * FROM produits) SELECT * FROM t"
    assert valider(sql, PERIMETRE_COMPLET) == sql


def test_refuse_plusieurs_instructions():
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT * FROM produits; DROP TABLE produits;", PERIMETRE_COMPLET)
    assert exc.value.statut == "refuse_ecriture"


def test_refuse_une_ecriture():
    with pytest.raises(ValidationEchouee) as exc:
        valider("DELETE FROM produits WHERE ref = 'REF-1024'", PERIMETRE_COMPLET)
    assert exc.value.statut == "refuse_ecriture"


def test_refuse_pragma_deguise_en_select():
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT * FROM pragma_table_info('produits')", PERIMETRE_COMPLET)
    # pragma_table_info n'est pas une table connue du schéma Sorabel : hors_schema.
    assert exc.value.statut == "hors_schema"

    with pytest.raises(ValidationEchouee) as exc:
        valider("PRAGMA table_info(produits)", PERIMETRE_COMPLET)
    assert exc.value.statut == "refuse_ecriture"


def test_refuse_une_table_inconnue():
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT * FROM avis", PERIMETRE_COMPLET)
    assert exc.value.statut == "hors_schema"


def test_refuse_une_table_hors_perimetre_du_profil():
    perimetre = _PerimetreFactice(["produits"])  # pas "ventes"
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT * FROM ventes", perimetre)
    assert exc.value.statut == "non_autorise"


def test_refuse_une_colonne_interdite_au_profil_support():
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT marge_pct FROM produits", PERIMETRE_SUPPORT)
    assert exc.value.statut == "non_autorise"
    assert "marge_pct" in exc.value.message


def test_autorise_prix_vente_ht_pour_le_profil_support():
    # Non sensible : ne doit jamais être bloqué.
    resultat = valider("SELECT prix_vente_ht FROM produits", PERIMETRE_SUPPORT)
    assert resultat == "SELECT prix_vente_ht FROM produits"


def test_supprime_les_commentaires_avant_validation():
    sql = "SELECT * FROM produits -- commentaire piégeux ; DROP TABLE produits\n"
    resultat = valider(sql, PERIMETRE_COMPLET)
    assert "DROP" not in resultat
    assert "--" not in resultat
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_sql_validation.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'sorabel_sql.validation'`

- [ ] **Step 3: Écrire `sorabel_sql/validation.py`**

```python
"""Barrières 2 et 3 (sur 4, E3) : une instruction, SELECT/WITH, mots-clés interdits, tables
et colonnes dans le périmètre du profil. Les barrières 1 (connexion lecture seule) et 4
(LIMIT, timeout) sont dans execution.py — une seule barrière ne suffit pas.

Liste blanche (SELECT/WITH) plutôt que liste noire seule : plus sûre, une liste noire ne
couvre que les formes d'écriture déjà prévues.
"""

from __future__ import annotations

import re

MOTS_CLES_INTERDITS = {
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "attach", "detach", "pragma", "vacuum", "reindex", "truncate",
}

TABLES_CONNUES = {"produits", "stocks", "clients", "commandes", "ventes"}

MOTIF_TABLE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
MOTIF_COMMENTAIRE_LIGNE = re.compile(r"--.*")
MOTIF_COMMENTAIRE_BLOC = re.compile(r"/\*.*?\*/", re.DOTALL)
MOTIF_MOT = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


class ValidationEchouee(Exception):
    def __init__(self, statut: str, message: str):
        self.statut = statut
        self.message = message
        super().__init__(message)


def _normaliser(sql: str) -> str:
    sans_commentaires = MOTIF_COMMENTAIRE_BLOC.sub(" ", sql)
    sans_commentaires = MOTIF_COMMENTAIRE_LIGNE.sub(" ", sans_commentaires)
    return re.sub(r"\s+", " ", sans_commentaires).strip()


def valider(sql: str, perimetre) -> str:
    """Retourne le SQL normalisé s'il passe les quatre contrôles ; lève ValidationEchouee sinon."""
    normalisee = _normaliser(sql)

    instructions = [i.strip() for i in normalisee.rstrip(";").split(";") if i.strip()]
    if len(instructions) != 1:
        raise ValidationEchouee("refuse_ecriture", "une seule instruction SQL est autorisée")
    instruction = instructions[0]

    premier_mot = instruction.split(" ", 1)[0].lower()
    if premier_mot not in ("select", "with"):
        raise ValidationEchouee(
            "refuse_ecriture", "seules les requêtes SELECT ou WITH sont autorisées"
        )

    mots = {m.lower() for m in MOTIF_MOT.findall(instruction)}
    interdits_presents = mots & MOTS_CLES_INTERDITS
    if interdits_presents:
        raise ValidationEchouee(
            "refuse_ecriture", f"mot-clé interdit détecté : {', '.join(sorted(interdits_presents))}"
        )

    tables_citees = {t.lower() for t in MOTIF_TABLE.findall(instruction)}
    inconnues = tables_citees - TABLES_CONNUES
    if inconnues:
        raise ValidationEchouee(
            "hors_schema",
            f"table(s) inexistante(s) : {', '.join(sorted(inconnues))}. "
            f"Tables disponibles : {', '.join(sorted(TABLES_CONNUES))}.",
        )

    tables_autorisees = perimetre.tables_autorisees()
    hors_perimetre = tables_citees - tables_autorisees
    if hors_perimetre:
        raise ValidationEchouee(
            "non_autorise", f"table(s) hors périmètre du profil : {', '.join(sorted(hors_perimetre))}"
        )

    for table in tables_citees:
        colonnes_interdites = perimetre.colonnes_interdites(table)
        presentes = {
            colonne for colonne in colonnes_interdites
            if re.search(rf"\b{re.escape(colonne)}\b", instruction, re.IGNORECASE)
        }
        if presentes:
            raise ValidationEchouee(
                "non_autorise",
                f"colonne(s) hors périmètre du profil : {', '.join(sorted(presentes))}",
            )

    return instruction
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_sql_validation.py -v`
Expected: `10 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `35 passed`

- [ ] **Step 6: Commit**

```bash
git add sorabel_sql/validation.py tests/test_sql_validation.py
git commit -m "feat(sql): validation à barrières (instruction unique, SELECT/WITH, périmètre)"
```

---

### Task 4: Exécution en lecture seule (barrières 1 et 4)

**Files:**
- Create: `sorabel_sql/execution.py`
- Test: `tests/test_sql_execution.py`

**Interfaces:**
- Consumes: `data/sorabel.db` (fichier existant, inchangé).
- Produces: `sorabel_sql.execution.executer(sql: str, params: tuple = ()) -> dict` — retourne
  `{"sql": str, "colonnes": list[str], "lignes": list[list], "n_lignes": int, "tronque": bool}`.
  Lève `sqlite3.OperationalError` si `sql` contient une écriture (barrière 1, indépendante de
  `validation.py`) ; lève `TimeoutError` si l'exécution dépasse `TIMEOUT_SECONDES`. Task 6
  (`tools.py`) est le seul appelant.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_sql_execution.py` :

```python
"""Barrières 1 (lecture seule) et 4 (LIMIT, timeout), sur la vraie base data/sorabel.db."""

import sqlite3

import pytest

from sorabel_sql import execution


def test_connexion_lecture_seule_refuse_une_ecriture_directe():
    """Barrière 1 : appelée SANS passer par validation.valider(), pour prouver qu'elle
    protège même si le reste de la chaîne est contourné."""
    with pytest.raises(sqlite3.OperationalError):
        execution.executer("DELETE FROM produits WHERE ref = 'REF-9999'")


def test_limit_par_defaut_est_injecte_si_absent():
    resultat = execution.executer("SELECT * FROM ventes")  # 993 lignes réelles
    assert resultat["n_lignes"] == execution.LIMIT_DEFAUT
    assert resultat["tronque"] is True
    assert f"LIMIT {execution.LIMIT_DEFAUT}" in resultat["sql"]


def test_limit_explicite_nest_pas_double():
    resultat = execution.executer("SELECT * FROM ventes LIMIT 5")
    assert resultat["n_lignes"] == 5
    assert resultat["tronque"] is False
    assert resultat["sql"].count("LIMIT") == 1


def test_parametre_lie_fonctionne():
    resultat = execution.executer("SELECT ref FROM produits WHERE ref = ?", ("REF-1024",))
    assert resultat["lignes"] == [["REF-1024"]]


def test_timeout_interrompt_une_requete_trop_longue(monkeypatch):
    monkeypatch.setattr(execution, "TIMEOUT_SECONDES", 0.01)
    with pytest.raises(TimeoutError):
        execution.executer(
            "SELECT * FROM ventes a, ventes b, ventes c LIMIT 999999999"
        )
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_sql_execution.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'sorabel_sql.execution'`

- [ ] **Step 3: Écrire `sorabel_sql/execution.py`**

```python
"""Barrières 1 et 4 (sur 4, E3) : connexion lecture seule, LIMIT par défaut, timeout.

La barrière 1 est la seule vraiment infranchissable : elle est appliquée par SQLite
lui-même (`mode=ro`), pas par notre code. Les autres protègent contre ce qu'elle laisse
passer (une lecture légitime mais hors périmètre, une requête lente ou cartésienne).
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

CHEMIN_DB = Path(__file__).resolve().parent.parent / "data" / "sorabel.db"
LIMIT_DEFAUT = 200
TIMEOUT_SECONDES = 5.0

MOTIF_LIMIT = re.compile(r"\blimit\s+\d+\s*$", re.IGNORECASE)


def _avec_limit(sql: str) -> str:
    return sql if MOTIF_LIMIT.search(sql) else f"{sql} LIMIT {LIMIT_DEFAUT}"


def executer(sql: str, params: tuple = ()) -> dict:
    """`sql` doit déjà avoir passé `validation.valider()` pour les appels génératifs — cette
    fonction reste malgré tout la dernière ligne de défense en lecture seule."""
    sql_avait_deja_un_limit = bool(MOTIF_LIMIT.search(sql))
    sql_limite = _avec_limit(sql)

    uri = f"file:{CHEMIN_DB.as_posix()}?mode=ro"
    connexion = sqlite3.connect(uri, uri=True)
    debut = time.monotonic()

    def _verifier_timeout() -> int:
        return 1 if time.monotonic() - debut > TIMEOUT_SECONDES else 0

    connexion.set_progress_handler(_verifier_timeout, 1000)
    try:
        curseur = connexion.execute(sql_limite, params)
        colonnes = [d[0] for d in curseur.description] if curseur.description else []
        lignes = curseur.fetchall()
    except sqlite3.OperationalError as erreur:
        if "interrupted" in str(erreur).lower():
            raise TimeoutError(
                f"requête interrompue après {TIMEOUT_SECONDES}s (barrière timeout)"
            ) from erreur
        raise
    finally:
        connexion.close()

    return {
        "sql": sql_limite,
        "colonnes": colonnes,
        "lignes": [list(ligne) for ligne in lignes],
        "n_lignes": len(lignes),
        "tronque": len(lignes) == LIMIT_DEFAUT and not sql_avait_deja_un_limit,
    }
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_sql_execution.py -v`
Expected: `5 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `40 passed`

- [ ] **Step 6: Commit**

```bash
git add sorabel_sql/execution.py tests/test_sql_execution.py
git commit -m "feat(sql): exécution lecture seule avec LIMIT par défaut et timeout"
```

---

### Task 5: Génération SQL via le LLM

**Files:**
- Create: `sorabel_sql/generation.py`
- Test: `tests/test_sql_generation.py`

**Interfaces:**
- Consumes: `sorabel_llm.client.completer(messages: list[dict]) -> str` (Phase 2) ;
  `sorabel_sql.schema.schema_commente(perimetre) -> str` (Task 1) ;
  `sorabel_sql.lexique_sensible.question_sensible(question: str) -> bool` (Task 2).
- Produces: `sorabel_sql.generation.generer(question: str, perimetre) -> str | None` (`None`
  signifie hors schéma — la question ne se traduit pas en SQL sur ce périmètre) ; lève
  `sorabel_sql.generation.QuestionSensible` **avant tout appel LLM** si la question est
  détectée comme sensible. Task 6 (`tools.ask_database`) capture `QuestionSensible` et
  interprète `None`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_sql_generation.py` :

```python
"""Génération SQL : refus avant génération (E5), traduction, hors schéma."""

import pytest

import sorabel_sql.generation as generation


class _PerimetreFactice:
    def tables_autorisees(self):
        return frozenset({"produits", "stocks", "clients", "commandes", "ventes"})

    def colonnes_interdites(self, table):
        return frozenset()


def test_question_sensible_leve_avant_tout_appel_llm(monkeypatch):
    appele = False

    def _completer_espion(messages):
        nonlocal appele
        appele = True
        return "SELECT 1"

    monkeypatch.setattr(generation, "completer", _completer_espion)

    with pytest.raises(generation.QuestionSensible):
        generation.generer("quelle est la marge sur REF-1024 ?", _PerimetreFactice())

    assert not appele


def test_traduit_une_question_en_sql(monkeypatch):
    monkeypatch.setattr(
        generation, "completer",
        lambda messages: "SELECT COUNT(*) FROM commandes WHERE strftime('%m', date_commande) = '04';",
    )
    sql = generation.generer("combien de commandes en avril ?", _PerimetreFactice())
    assert sql == "SELECT COUNT(*) FROM commandes WHERE strftime('%m', date_commande) = '04'"


def test_hors_schema_renvoie_none(monkeypatch):
    monkeypatch.setattr(generation, "completer", lambda messages: "AUCUNE_REQUETE")
    assert generation.generer("quel est le taux de satisfaction client ?", _PerimetreFactice()) is None


def test_le_prompt_contient_le_schema_filtre(monkeypatch):
    messages_captures = {}

    def _completer_espion(messages):
        messages_captures["valeur"] = messages
        return "SELECT 1"

    monkeypatch.setattr(generation, "completer", _completer_espion)
    generation.generer("combien de produits ?", _PerimetreFactice())

    contenu_systeme = messages_captures["valeur"][0]["content"]
    assert "CREATE TABLE produits" in contenu_systeme
    assert "SELECT" in contenu_systeme  # règles de sortie présentes
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_sql_generation.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'sorabel_sql.generation'`

- [ ] **Step 3: Écrire `sorabel_sql/generation.py`**

```python
"""Génération de la requête SQL candidate — traduction de la question en langage naturel.

La détection d'intention sensible se fait AVANT tout appel LLM (E5) : aucune raison de payer
un appel et de risquer une fuite pour une question qu'on sait devoir refuser.
"""

from __future__ import annotations

from sorabel_llm.client import completer

from .lexique_sensible import question_sensible
from .schema import schema_commente

PROMPT_SYSTEME = """Tu traduis une question en langage naturel en une requête SQLite en LECTURE \
SEULE sur la base Sorabel. Règles strictes :
- Une seule requête, commençant par SELECT ou WITH.
- Pas de point-virgule multiple, pas de commentaire.
- N'utilise QUE les tables et colonnes du schéma ci-dessous — n'invente jamais de colonne.
- `date_commande` est du texte ISO ('AAAA-MM-JJ') : utilise strftime() pour les agrégations \
temporelles.
- Réponds UNIQUEMENT avec la requête SQL, sans habillage ni explication.
- Si la question ne peut pas être traduite en SQL sur ce schéma, réponds EXACTEMENT : \
AUCUNE_REQUETE"""

EXEMPLES = """Q : combien de commandes en avril ?
S : SELECT COUNT(*) FROM commandes WHERE strftime('%m', date_commande) = '04';

Q : quel est le stock de REF-1024 ?
S : SELECT entrepot, quantite FROM stocks WHERE ref = 'REF-1024';"""


class QuestionSensible(Exception):
    """Levée avant tout appel LLM : la question porte sur une colonne interdite au profil."""


def generer(question: str, perimetre) -> str | None:
    """`None` si la question ne se traduit pas en SQL sur ce schéma (hors_schema)."""
    if question_sensible(question):
        raise QuestionSensible(question)

    schema = schema_commente(perimetre)
    prompt_systeme = f"{PROMPT_SYSTEME}\n\nSchéma disponible :\n{schema}\n\nExemples :\n{EXEMPLES}"
    reponse = completer([
        {"role": "system", "content": prompt_systeme},
        {"role": "user", "content": f"Q : {question}\nS :"},
    ])
    sql = reponse.strip().strip(";").strip()
    return None if sql == "AUCUNE_REQUETE" else sql
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_sql_generation.py -v`
Expected: `4 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `44 passed`

- [ ] **Step 6: Commit**

```bash
git add sorabel_sql/generation.py tests/test_sql_generation.py
git commit -m "feat(sql): génération SQL via le LLM (refus sensible avant génération)"
```

---

### Task 6: Les quatre tools (`ask_database`, `get_schema`, `check_stock`, `order_status`)

**Files:**
- Create: `sorabel_sql/tools.py`
- Test: `tests/test_sql_tools.py`

**Interfaces:**
- Consumes: tout ce des Tasks 1-5 (`schema_commente`, `generer`/`QuestionSensible`,
  `valider`/`ValidationEchouee`, `executer`) ; un objet `perimetre` duck-typé (même contrat).
- Produces : `sorabel_sql.tools.ask_database(question: str, perimetre) -> dict`,
  `get_schema(perimetre) -> dict`, `check_stock(ref: str) -> dict`,
  `order_status(order_id: str) -> dict`. Phase 5 (serveur MCP) enveloppera directement ces
  quatre fonctions comme tools MCP — les noms et signatures ne doivent pas changer sans mettre
  à jour cette phase.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_sql_tools.py` :

```python
"""Les quatre tools SQL du chantier 2 : ask_database, get_schema, check_stock, order_status."""

import pytest

import sorabel_sql.tools as tools
from sorabel_sql.generation import QuestionSensible
from sorabel_sql.validation import ValidationEchouee


class _PerimetreFactice:
    def __init__(self, tables=None, colonnes_interdites=None):
        self._tables = frozenset(tables or {"produits", "stocks", "clients", "commandes", "ventes"})
        self._colonnes_interdites = colonnes_interdites or {}

    def tables_autorisees(self):
        return self._tables

    def colonnes_interdites(self, table):
        return frozenset(self._colonnes_interdites.get(table, ()))


def test_get_schema_renvoie_le_schema_du_perimetre(monkeypatch):
    monkeypatch.setattr(tools, "schema_commente", lambda p: "SCHEMA-FACTICE")
    resultat = tools.get_schema(_PerimetreFactice())
    assert resultat == {"statut": "ok", "schema": "SCHEMA-FACTICE"}


def test_ask_database_question_sensible_est_non_autorise_sans_generation(monkeypatch):
    def _generer_espion(question, perimetre):
        raise QuestionSensible(question)

    monkeypatch.setattr(tools, "generer", _generer_espion)
    resultat = tools.ask_database("quelle est la marge sur REF-1024 ?", _PerimetreFactice())
    assert resultat["statut"] == "non_autorise"
    assert resultat["sql"] is None


def test_ask_database_hors_schema_quand_generer_renvoie_none(monkeypatch):
    monkeypatch.setattr(tools, "generer", lambda question, perimetre: None)
    resultat = tools.ask_database("quel est le taux de satisfaction ?", _PerimetreFactice())
    assert resultat["statut"] == "hors_schema"
    assert resultat["sql"] is None


def test_ask_database_renvoie_le_sql_rejete_si_validation_echoue(monkeypatch):
    monkeypatch.setattr(tools, "generer", lambda question, perimetre: "DELETE FROM produits")

    def _valider_echec(sql, perimetre):
        raise ValidationEchouee("refuse_ecriture", "écriture détectée")

    monkeypatch.setattr(tools, "valider", _valider_echec)
    resultat = tools.ask_database("supprime les commandes de test", _PerimetreFactice())
    assert resultat["statut"] == "refuse_ecriture"
    assert resultat["sql"] == "DELETE FROM produits"


def test_ask_database_execute_et_renvoie_le_resultat(monkeypatch):
    monkeypatch.setattr(tools, "generer", lambda question, perimetre: "SELECT COUNT(*) FROM commandes")
    monkeypatch.setattr(tools, "valider", lambda sql, perimetre: sql)
    monkeypatch.setattr(
        tools, "executer",
        lambda sql, params=(): {"sql": sql, "colonnes": ["COUNT(*)"], "lignes": [[27]], "n_lignes": 1, "tronque": False},
    )
    resultat = tools.ask_database("combien de commandes ?", _PerimetreFactice())
    assert resultat["statut"] == "ok"
    assert resultat["lignes"] == [[27]]
    assert resultat["sql"] == "SELECT COUNT(*) FROM commandes"


def test_check_stock_ref_invalide_est_hors_schema():
    resultat = tools.check_stock("PAS-UNE-REF")
    assert resultat["statut"] == "hors_schema"


def test_check_stock_ref_valide_interroge_par_parametre_lie(monkeypatch):
    appels = []

    def _executer_espion(sql, params=()):
        appels.append((sql, params))
        return {
            "sql": sql, "colonnes": ["entrepot", "quantite", "seuil_reappro"],
            "lignes": [["LYON", 3, 10]], "n_lignes": 1, "tronque": False,
        }

    monkeypatch.setattr(tools, "executer", _executer_espion)
    resultat = tools.check_stock("REF-1024")

    assert resultat["statut"] == "ok"
    assert resultat["sous_seuil_reappro"] is True  # 3 < 10
    assert appels[0][1] == ("REF-1024",)  # paramètre lié, pas concaténé
    assert "REF-1024" not in appels[0][0]  # jamais dans le texte SQL


def test_order_status_id_invalide_est_hors_schema():
    resultat = tools.order_status("PAS-UN-ID")
    assert resultat["statut"] == "hors_schema"


def test_order_status_id_valide_interroge_par_parametre_lie(monkeypatch):
    appels = []

    def _executer_espion(sql, params=()):
        appels.append((sql, params))
        return {
            "sql": sql, "colonnes": ["statut", "date_commande", "montant_ht"],
            "lignes": [["livree", "2026-04-02", 450.0]], "n_lignes": 1, "tronque": False,
        }

    monkeypatch.setattr(tools, "executer", _executer_espion)
    resultat = tools.order_status("CMD-2025-0004")

    assert resultat["statut"] == "ok"
    assert resultat["lignes"] == [["livree", "2026-04-02", 450.0]]
    assert appels[0][1] == ("CMD-2025-0004",)
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_sql_tools.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'sorabel_sql.tools'`

- [ ] **Step 3: Écrire `sorabel_sql/tools.py`**

```python
"""Les quatre tools SQL du chantier 2. Compose schema/generation/validation/execution sans
dupliquer leur logique — chaque tool ne fait que router vers le bon statut."""

from __future__ import annotations

import re

from .execution import executer
from .generation import QuestionSensible, generer
from .schema import schema_commente
from .validation import ValidationEchouee, valider

MOTIF_REF = re.compile(r"^REF-\d{4}$")
MOTIF_COMMANDE = re.compile(r"^CMD-\d{4}-\d{4}$")


def get_schema(perimetre) -> dict:
    return {"statut": "ok", "schema": schema_commente(perimetre)}


def ask_database(question: str, perimetre) -> dict:
    try:
        sql_candidat = generer(question, perimetre)
    except QuestionSensible:
        return {
            "statut": "non_autorise",
            "message": "Ce profil n'a pas accès aux marges ni aux prix d'achat.",
            "sql": None,
        }

    if sql_candidat is None:
        return {
            "statut": "hors_schema",
            "message": "Cette question ne correspond à aucune table de la base Sorabel.",
            "sql": None,
        }

    try:
        sql_valide = valider(sql_candidat, perimetre)
    except ValidationEchouee as erreur:
        return {"statut": erreur.statut, "message": erreur.message, "sql": sql_candidat}

    resultat = executer(sql_valide)
    return {"statut": "ok", **resultat}


def check_stock(ref: str) -> dict:
    if not MOTIF_REF.match(ref):
        return {"statut": "hors_schema", "message": f"référence invalide : {ref!r} (attendu REF-XXXX)"}

    resultat = executer(
        "SELECT entrepot, quantite, seuil_reappro FROM stocks WHERE ref = ?", (ref,)
    )
    index_quantite = resultat["colonnes"].index("quantite")
    index_seuil = resultat["colonnes"].index("seuil_reappro")
    sous_seuil = any(ligne[index_quantite] < ligne[index_seuil] for ligne in resultat["lignes"])
    return {"statut": "ok", **resultat, "sous_seuil_reappro": sous_seuil}


def order_status(order_id: str) -> dict:
    if not MOTIF_COMMANDE.match(order_id):
        return {
            "statut": "hors_schema",
            "message": f"identifiant de commande invalide : {order_id!r} (attendu CMD-AAAA-NNNN)",
        }

    resultat = executer(
        "SELECT statut, date_commande, montant_ht FROM commandes WHERE id = ?", (order_id,)
    )
    return {"statut": "ok", **resultat}
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_sql_tools.py -v`
Expected: `9 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `53 passed`

- [ ] **Step 6: Vérification manuelle sur les deux tests d'acceptance du brief**

Run :
```bash
python -c "
from sorabel_sql.tools import ask_database

class PerimetreCommercial:
    def tables_autorisees(self): return frozenset({'produits','stocks','clients','commandes','ventes'})
    def colonnes_interdites(self, table): return frozenset()

class PerimetreSupport:
    def tables_autorisees(self): return frozenset({'produits','stocks','clients','commandes','ventes'})
    def colonnes_interdites(self, table):
        return frozenset({'prix_achat_ht','marge_pct'}) if table == 'produits' else (
            frozenset({'marge_ht'}) if table == 'ventes' else frozenset())

print('commercial / avril  :', ask_database('combien de commandes en avril ?', PerimetreCommercial())['n_lignes' if False else 'lignes'])
print('support / marge     :', ask_database('quelle est la marge sur REF-1024 ?', PerimetreSupport())['statut'])
print('commercial / marge  :', ask_database('quelle est la marge sur REF-1024 ?', PerimetreCommercial())['statut'])
"
```
Expected : la première ligne affiche `[[27]]` (test d'acceptance du brief) ; la deuxième
affiche `non_autorise` ; la troisième affiche `ok` — **exactement le contraste attendu entre
les deux profils sur la même question**, ce que la Phase 4 câblera avec de vrais objets
`Perimetre` au lieu de ces classes factices.

Aucun commit pour ce step (vérification, pas de code nouveau).

- [ ] **Step 7: Commit**

```bash
git add sorabel_sql/tools.py tests/test_sql_tools.py
git commit -m "feat(sql): ask_database, check_stock, order_status (chantier 2 complet)"
```
