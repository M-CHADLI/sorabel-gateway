# Phase 1 — Correction du chemin corpus + métadonnées de gouvernance des notes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corriger un bug de chemin qui empêche toute réingestion, puis faire produire par
l'extracteur de notes les deux métadonnées (`sous_type`, `diffusion_restreinte`) requises par
la matrice de gouvernance (chantier 3), et les propager jusqu'aux chunks indexés.

**Architecture:** Une modification ciblée dans trois fichiers existants
(`sorabel_rag/ingestion.py`, `sorabel_rag/extraction.py`, `sorabel_rag/chunking.py`), une
nouvelle suite de tests `tests/`, puis une régénération complète du corpus canonique et de
l'index à partir des sources réelles (`data/corpus/`).

**Tech Stack:** Python 3.12, pytest (nouvelle dépendance de dev), les bibliothèques déjà
utilisées par `sorabel_rag` (pypdf, beautifulsoup4, PyYAML, chromadb, sentence-transformers,
rank-bm25) — toutes déjà installées dans l'environnement.

## Global Constraints

- Langue du code de domaine, messages et tests : français (`sous_type`, `diffusion_restreinte`,
  pas de traduction anglaise des identifiants).
- Ne pas modifier `SCHEMA_VERSION` dans `sorabel_rag/modeles.py` au-delà de ce que ce plan
  demande explicitement (Task 2) — c'est le seul mécanisme d'invalidation du cache
  d'extraction, une omission laisserait des canoniques périmés en place silencieusement.
- Aucune dépendance réseau dans les tests de cette phase (pas d'appel LLM, pas de Chroma) :
  cette phase ne touche que l'extraction et le chunking, purs et locaux.
- Exécuter les tests avec `python -m pytest` (pas `pytest` seul) depuis la racine du dépôt,
  pour que `import sorabel_rag` résolve sans `conftest.py` ni `pyproject.toml`.

---

## État constaté avant ce plan (important pour comprendre les tâches)

`sorabel_rag/ingestion.py:28` définit `CORPUS = RACINE / "data" / "data" / "corpus"` — un
chemin à double niveau `data/data/corpus` qui **n'existe pas** sur ce dépôt : le corpus réel
est à `data/corpus/` (vérifié : `Path("data/data/corpus").exists()` → `False`,
`Path("data/corpus").exists()` → `True`). `data/canonique/` contient déjà 400 fichiers générés
par une exécution antérieure d'`ingerer.py` — ce qui veut dire que ce bug est probablement
apparu après cette dernière exécution réussie (réorganisation du dossier `data/` sans mise à
jour du code). En l'état, relancer `python scripts/ingerer.py --forcer` échouerait
silencieusement : la boucle `for chemin in sorted((CORPUS / dossier).glob(motif))` sur un
dossier inexistant ne lève pas d'erreur, elle itère sur zéro fichier — **0 document traité,
0 erreur visible**. C'est pour cela que Task 1 est un correctif à part entière, pas un détail.

`CLAUDE.md` documente aussi ce double niveau (« Attention au double niveau `data/data` ») —
c'est la documentation qui est obsolète, pas une exigence à préserver. Task 1 corrige le code
pour suivre la structure réelle du dépôt.

## File Structure

```
sorabel_rag/ingestion.py     MODIFIÉ : CORPUS pointe vers data/corpus (Task 1)
sorabel_rag/modeles.py       MODIFIÉ : SCHEMA_VERSION 2→3, alerte sous_type_absent (Task 2)
sorabel_rag/extraction.py    MODIFIÉ : extraire_note() produit sous_type + diffusion_restreinte (Task 2)
sorabel_rag/chunking.py      MODIFIÉ : chunker() propage les deux champs dans metadonnees (Task 3)
requirements.txt             MODIFIÉ : ajoute pytest (Task 1)
tests/__init__.py            NOUVEAU : vide, fait de tests/ un package (Task 1)
tests/test_ingestion.py      NOUVEAU : régression sur le chemin CORPUS (Task 1)
tests/test_extraction.py     NOUVEAU : sous_type + diffusion_restreinte (Task 2)
tests/test_chunking.py       NOUVEAU : propagation dans les métadonnées de chunk (Task 3)
```

---

### Task 1: Corriger le chemin du corpus et poser l'infrastructure de test

**Files:**
- Modify: `sorabel_rag/ingestion.py:28`
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_ingestion.py`

**Interfaces:**
- Consumes: `sorabel_rag.ingestion.CORPUS` (constante `Path`, déjà utilisée par
  `extraire_corpus()` dans le même fichier).
- Produces: `CORPUS` pointe désormais vers un dossier qui existe réellement — aucune autre
  tâche de ce plan ne dépend d'un nouveau nom ou d'une nouvelle signature.

- [ ] **Step 1: Ajouter pytest aux dépendances**

Dans `requirements.txt`, ajouter à la fin :

```
# Tests
pytest>=8.0
```

- [ ] **Step 2: Créer le package de tests**

Créer `tests/__init__.py` (fichier vide).

- [ ] **Step 3: Écrire le test de régression qui échoue**

Créer `tests/test_ingestion.py` :

```python
"""Régression : CORPUS doit pointer vers le corpus réel du dépôt."""

from sorabel_rag.ingestion import CORPUS


def test_corpus_pointe_vers_un_dossier_existant():
    assert CORPUS.is_dir(), f"CORPUS ({CORPUS}) n'existe pas"


def test_corpus_contient_les_quatre_sous_dossiers():
    sous_dossiers = {p.name for p in CORPUS.iterdir() if p.is_dir()}
    assert {"fiches", "notices", "notes", "sav"} <= sous_dossiers
```

- [ ] **Step 4: Lancer le test et vérifier qu'il échoue**

Run: `python -m pytest tests/test_ingestion.py -v`
Expected: `FAILED tests/test_ingestion.py::test_corpus_pointe_vers_un_dossier_existant` avec le
message `CORPUS (.../data/data/corpus) n'existe pas`.

- [ ] **Step 5: Corriger le chemin**

Dans `sorabel_rag/ingestion.py`, ligne 28, remplacer :

```python
CORPUS = RACINE / "data" / "data" / "corpus"
```

par :

```python
CORPUS = RACINE / "data" / "corpus"
```

- [ ] **Step 6: Relancer le test et vérifier qu'il passe**

Run: `python -m pytest tests/test_ingestion.py -v`
Expected: `2 passed`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt tests/__init__.py tests/test_ingestion.py sorabel_rag/ingestion.py
git commit -m "fix: corriger le chemin CORPUS vers data/corpus (au lieu de data/data/corpus)"
```

---

### Task 2: Produire `sous_type` et `diffusion_restreinte` dans l'extracteur de notes

**Files:**
- Modify: `sorabel_rag/modeles.py`
- Modify: `sorabel_rag/extraction.py`
- Create: `tests/test_extraction.py`

**Interfaces:**
- Consumes: `sorabel_rag.modeles.DocumentCanonique.attributs` (`dict[str, str]`, champ déjà
  existant) ; `sorabel_rag.extraction.extraire_note(chemin: Path) -> DocumentCanonique`
  (signature inchangée).
- Produces: pour tout document `d` de type `TYPE_NOTE`, `d.attributs["sous_type"]` vaut l'une
  des 5 valeurs `"politique_tarifaire"`, `"reunion_achat"`, `"logistique"`,
  `"alerte_qualite"`, `"retour_terrain"` (chaîne vide si le nom de fichier ne correspond à
  aucun des 5 motifs) et `d.attributs["diffusion_restreinte"]` vaut la chaîne `"true"` ou
  `"false"`. Task 3 lit ces deux clés depuis `document.attributs`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_extraction.py` :

```python
"""Tests de l'extracteur de notes : sous_type et diffusion_restreinte (gouvernance E5)."""

from pathlib import Path

from sorabel_rag.extraction import extraire_note

CORPUS_NOTES = Path(__file__).resolve().parent.parent / "data" / "corpus" / "notes"


def test_note_politique_tarifaire_est_sous_type_et_diffusion_restreinte():
    doc = extraire_note(CORPUS_NOTES / "note-2024-03-03-politique-tarifaire-21.md")
    assert doc.attributs["sous_type"] == "politique_tarifaire"
    assert doc.attributs["diffusion_restreinte"] == "true"


def test_note_reunion_achat_est_sous_type_sans_diffusion_restreinte():
    doc = extraire_note(CORPUS_NOTES / "note-2024-01-02-reunion-achat-32.md")
    assert doc.attributs["sous_type"] == "reunion_achat"
    assert doc.attributs["diffusion_restreinte"] == "false"


def test_note_logistique_est_sous_type_operationnel():
    doc = extraire_note(CORPUS_NOTES / "note-2024-06-05-logistique-08.md")
    assert doc.attributs["sous_type"] == "logistique"
    assert doc.attributs["diffusion_restreinte"] == "false"


def test_note_alerte_qualite_est_sous_type_operationnel():
    doc = extraire_note(CORPUS_NOTES / "note-2024-01-11-alerte-qualite-50.md")
    assert doc.attributs["sous_type"] == "alerte_qualite"


def test_note_retour_terrain_est_sous_type_operationnel():
    doc = extraire_note(CORPUS_NOTES / "note-2024-03-28-retour-terrain-24.md")
    assert doc.attributs["sous_type"] == "retour_terrain"


def test_nom_de_fichier_non_reconnu_ne_bloque_pas_lextraction(tmp_path):
    chemin = tmp_path / "note-sans-motif-connu.md"
    chemin.write_text(
        "---\ntitre: Test\ndate: 2024-01-01\ntype: note_interne\nversion: '1.0'\n---\n\nCorps.",
        encoding="utf-8",
    )
    doc = extraire_note(chemin)
    assert doc.attributs["sous_type"] == ""
    assert doc.attributs["diffusion_restreinte"] == "false"
    assert "sous_type_absent" in doc.qualite.alertes
    assert doc.qualite.indexable  # non bloquant
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_extraction.py -v`
Expected: `FAILED` sur les 6 tests avec `KeyError: 'sous_type'`.

- [ ] **Step 3: Ajouter l'alerte non bloquante dans `sorabel_rag/modeles.py`**

Dans `sorabel_rag/modeles.py`, incrémenter `SCHEMA_VERSION` (ligne 16) :

```python
SCHEMA_VERSION = 3
```

Dans le dictionnaire `LIBELLES_ALERTES` (lignes 56-63), ajouter une entrée :

```python
LIBELLES_ALERTES = {
    "texte_vide": "aucun texte extrait",
    "texte_court": "texte anormalement court pour ce type",
    "aucune_section": "aucune frontière structurelle détectée",
    "reference_absente": "référence attendue mais introuvable",
    "date_absente": "aucune date exploitable",
    "titre_absent": "aucun titre exploitable",
    "sous_type_absent": "nom de fichier ne correspond à aucun sous-type de note connu",
}
```

`ALERTES_BLOQUANTES` (ligne 54) reste inchangé : `sous_type_absent` ne bloque pas
l'indexation, elle signale seulement un fichier à examiner.

- [ ] **Step 4: Ajouter le motif et l'extraction dans `sorabel_rag/extraction.py`**

Ajouter le motif de nom de fichier, à côté de `MOTIF_NOM_SAV` (après la ligne 35) :

```python
MOTIF_NOM_NOTE = re.compile(
    r"^note-\d{4}-\d{2}-\d{2}-"
    r"(?P<sous_type>alerte-qualite|logistique|politique-tarifaire|retour-terrain|reunion-achat)"
    r"-\d+$"
)
MOTIF_DIFFUSION_RESTREINTE = re.compile(r"diffusion restreinte", re.IGNORECASE)
```

Modifier `_controler` (lignes 59-75) pour ajouter la vérification du sous-type, seulement
pertinente pour les notes :

```python
def _controler(doc: DocumentCanonique, reference_attendue: bool) -> None:
    """Alimente `doc.qualite`. Sans ce contrôle, un document mal extrait disparaît
    silencieusement de l'index et personne ne s'en aperçoit avant la démonstration."""
    alertes = doc.qualite.alertes
    texte = doc.texte
    if not texte.strip():
        alertes.append("texte_vide")
    elif len(texte) < SEUILS_LONGUEUR.get(doc.type_document, 100):
        alertes.append("texte_court")
    if not doc.sections:
        alertes.append("aucune_section")
    if reference_attendue and not doc.reference:
        alertes.append("reference_absente")
    if not doc.date:
        alertes.append("date_absente")
    if not doc.titre:
        alertes.append("titre_absent")
    if doc.type_document == TYPE_NOTE and not doc.attributs.get("sous_type"):
        alertes.append("sous_type_absent")
```

Modifier `extraire_note` (lignes 194-235) pour peupler les deux nouvelles clés dans
`attributs`, avant la construction de `DocumentCanonique` :

```python
def extraire_note(chemin: Path) -> DocumentCanonique:
    brut = chemin.read_text(encoding="utf-8")
    entete: dict = {}
    corps = brut
    if brut.startswith("---"):
        _, bloc, corps = brut.split("---", 2)
        entete = yaml.safe_load(bloc) or {}

    corps = corps.strip()
    # Le titre H1 répète le front-matter : on ne le garde pas dans le contenu.
    lignes = [ligne for ligne in corps.splitlines() if not ligne.startswith("# ")]
    corps_propre = "\n".join(lignes).strip()

    references = extraire_references(corps)
    reference = references[0] if references else None
    version = str(entete.get("version", "1.0"))
    date = entete.get("date")

    correspondance_sous_type = MOTIF_NOM_NOTE.match(chemin.stem)
    sous_type = (
        correspondance_sous_type["sous_type"].replace("-", "_")
        if correspondance_sous_type
        else ""
    )
    diffusion_restreinte = bool(MOTIF_DIFFUSION_RESTREINTE.search(corps_propre))

    attributs = {
        cle: str(valeur)
        for cle, valeur in entete.items()
        if cle in ("auteur", "type") and valeur
    }
    attributs["sous_type"] = sous_type
    attributs["diffusion_restreinte"] = "true" if diffusion_restreinte else "false"

    doc = DocumentCanonique(
        doc_id=f"{TYPE_NOTE}:{chemin.stem}:v{version}",
        titre=str(entete.get("titre", "")).strip(),
        type_document=TYPE_NOTE,
        version=version,
        reference=reference,
        references_citees=references[1:],
        date=str(date) if date else None,
        cle_groupe=f"{TYPE_NOTE}:{chemin.stem}",
        source_path=str(chemin).replace("\\", "/"),
        hash_source=hacher_fichier(chemin),
        hash_texte=hacher_texte(corps_propre, str(entete.get('titre', '')), reference, str(date) if date else None),
        extrait_le=_maintenant(),
        attributs=attributs,
        sections=[Section("", corps_propre)] if corps_propre else [],
        qualite=Qualite(),
    )
    # 16 notes sur 80 ne citent aucune référence : c'est normal, pas une anomalie.
    _controler(doc, reference_attendue=False)
    return doc
```

- [ ] **Step 5: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_extraction.py -v`
Expected: `6 passed`

- [ ] **Step 6: Lancer toute la suite pour vérifier l'absence de régression**

Run: `python -m pytest -v`
Expected: `8 passed` (les 2 de Task 1 + les 6 de Task 2)

- [ ] **Step 7: Commit**

```bash
git add sorabel_rag/modeles.py sorabel_rag/extraction.py tests/test_extraction.py
git commit -m "feat: extraire sous_type et diffusion_restreinte des notes (gouvernance E5)"
```

---

### Task 3: Propager `sous_type` et `diffusion_restreinte` dans les métadonnées de chunk

**Files:**
- Modify: `sorabel_rag/chunking.py:196-210`
- Create: `tests/test_chunking.py`

**Interfaces:**
- Consumes: `document.attributs["sous_type"]` (`str`), `document.attributs["diffusion_restreinte"]`
  (`"true"` | `"false"`) — produits par Task 2 pour tout document `TYPE_NOTE`.
- Produces: pour tout `Chunk` issu d'un document `TYPE_NOTE`,
  `chunk.metadonnees["sous_type"]` (`str`) et `chunk.metadonnees["diffusion_restreinte"]`
  (`bool` Python natif, pas une chaîne — c'est la forme que Chroma indexera). Le chantier de
  gouvernance (matrice d'accès) filtrera dessus via `where={"diffusion_restreinte": False}` ou
  `{"sous_type": {"$in": [...]}}` sur la collection Chroma.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/test_chunking.py` :

```python
"""Propagation des métadonnées de gouvernance (sous_type, diffusion_restreinte) dans les chunks."""

from sorabel_rag.chunking import chunker
from sorabel_rag.modeles import TYPE_NOTE, DocumentCanonique, Qualite, Section


def _note_de_test(sous_type: str, diffusion_restreinte: str) -> DocumentCanonique:
    return DocumentCanonique(
        doc_id="note_interne:note-test:v1.0",
        titre="Note de test",
        type_document=TYPE_NOTE,
        version="1.0",
        source_path="data/corpus/notes/note-test.md",
        hash_source="abc",
        hash_texte="def",
        extrait_le="2026-09-02T00:00:00+00:00",
        cle_groupe="note_interne:note-test",
        attributs={"sous_type": sous_type, "diffusion_restreinte": diffusion_restreinte},
        sections=[Section("", "Corps de la note de test, assez long pour ne pas alerter.")],
        qualite=Qualite(),
    )


def test_chunk_porte_le_sous_type_et_la_diffusion_restreinte():
    document = _note_de_test("politique_tarifaire", "true")
    manifeste = {
        "groupes": {
            document.cle_groupe: {
                "doc_id_courant": document.doc_id,
                "versions": [document.version],
            }
        }
    }
    chunks = chunker(document, manifeste)
    assert len(chunks) == 1
    assert chunks[0].metadonnees["sous_type"] == "politique_tarifaire"
    assert chunks[0].metadonnees["diffusion_restreinte"] is True


def test_chunk_diffusion_non_restreinte_est_bool_false():
    document = _note_de_test("logistique", "false")
    manifeste = {
        "groupes": {
            document.cle_groupe: {
                "doc_id_courant": document.doc_id,
                "versions": [document.version],
            }
        }
    }
    chunks = chunker(document, manifeste)
    assert chunks[0].metadonnees["diffusion_restreinte"] is False
    assert chunks[0].metadonnees["sous_type"] == "logistique"
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

Run: `python -m pytest tests/test_chunking.py -v`
Expected: `FAILED` — `KeyError: 'sous_type'`

- [ ] **Step 3: Modifier `sorabel_rag/chunking.py`**

Dans la fonction `chunker` (lignes 170-213), le dictionnaire `metadonnees` construit lignes
196-210 devient :

```python
                metadonnees={
                    "doc_id": document.doc_id,
                    "titre": document.titre,
                    "type_document": document.type_document,
                    "reference": document.reference or "",
                    # Chroma ne filtre pas sur des listes : chaîne + `contains` pour le boost.
                    "references_citees": "|".join(document.references_citees),
                    "version": document.version,
                    "est_version_courante": est_courante,
                    "versions_anterieures": "|".join(anterieures),
                    "date": document.date or "",
                    "section": titre_section,
                    "source_path": document.source_path,
                    "cle_groupe": document.cle_groupe,
                    # Gouvernance (E5) : filtrage par sous-type et confidentialité des notes.
                    # Chaîne vide / False pour les documents non concernés (fiches, notices, SAV).
                    "sous_type": document.attributs.get("sous_type", ""),
                    "diffusion_restreinte": document.attributs.get("diffusion_restreinte") == "true",
                },
```

- [ ] **Step 4: Lancer le test et vérifier qu'il passe**

Run: `python -m pytest tests/test_chunking.py -v`
Expected: `2 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `10 passed`

- [ ] **Step 6: Commit**

```bash
git add sorabel_rag/chunking.py tests/test_chunking.py
git commit -m "feat: propager sous_type et diffusion_restreinte dans les métadonnées de chunk"
```

---

### Task 4: Régénérer le corpus canonique et l'index, vérifier le rapport qualité

**Files:**
- Aucun fichier de code — cette tâche exécute le pipeline sur les données réelles et vérifie
  ses sorties (`data/canonique/_rapport.md`, `data/canonique/_manifeste.json`,
  `data/chroma/`). Ces sorties sont ignorées par git (`.gitignore`), rien à committer ici.

**Interfaces:**
- Consumes: `sorabel_rag.ingestion.ingerer(forcer: bool) -> tuple[list[DocumentCanonique], dict]`
  (Task 1), `sorabel_rag.chunking.chunker_corpus`, `sorabel_rag.index.indexer` (inchangés).
- Produces: `data/canonique/*.json` régénérés avec `schema_version: 3`, `data/chroma/`
  reconstruit avec les nouvelles métadonnées — c'est l'état que consomment toutes les phases
  suivantes (recherche, génération RAG, gouvernance).

- [ ] **Step 1: Forcer la réextraction complète**

Run: `python scripts/ingerer.py --forcer`

Expected (les comptes exacts du corpus, cf. `CLAUDE.md`) :
```
400 documents traites, 400 indexables
<N> groupes de versions
-> .../data/canonique
-> .../data/canonique/_rapport.md
```
(`N` dépend du nombre de groupes multi-versions du corpus ; ce qui importe est **400
documents traités** — avant le correctif de Task 1, cette commande produisait `0 documents
traites`.)

- [ ] **Step 2: Vérifier qu'aucun document n'est bloquant**

Run (PowerShell) : `Select-String -Path "data/canonique/_rapport.md" -Pattern "Bloquants"`
Expected: la ligne affiche `**0**` — aucun document n'est exclu de l'indexation. Si ce n'est
pas le cas, ouvrir `data/canonique/_rapport.md` section « Documents concernés » avant de
continuer : ne pas indexer par-dessus des documents mal extraits.

- [ ] **Step 3: Vérifier que les notes portent bien sous_type et diffusion_restreinte**

Run :
```bash
python -c "
import json, glob
manquants = []
for chemin in glob.glob('data/canonique/note_interne__*.json'):
    d = json.load(open(chemin, encoding='utf-8'))
    if not d['attributs'].get('sous_type'):
        manquants.append(chemin)
print(f\"{80 - len(manquants)}/80 notes avec sous_type\")
print('Sans sous_type :', manquants or 'aucune')
"
```
Expected: `80/80 notes avec sous_type` et `Sans sous_type : aucune`.

- [ ] **Step 4: Réindexer**

Run: `python scripts/indexer.py`

Expected :
```
400 documents -> 400 chunks
indexes : 400 chunks | 768 dims | intfloat/multilingual-e5-base
```
(400 chunks car le corpus est court — cf. le commentaire en tête de `chunking.py` : aucune
redécoupe ne se déclenche, la fusion ne s'applique qu'à l'intérieur d'un même document donc ne
réduit pas non plus le compte ici.)

- [ ] **Step 5: Vérifier que Chroma expose bien les nouveaux champs**

Run :
```bash
python -c "
from sorabel_rag.index import ouvrir_collection
c = ouvrir_collection()
r = c.get(where={'sous_type': 'politique_tarifaire'}, include=['metadatas'], limit=1)
print(r['metadatas'][0] if r['metadatas'] else 'AUCUN RESULTAT')
"
```
Expected: un dictionnaire de métadonnées où `sous_type` vaut `politique_tarifaire` et
`diffusion_restreinte` vaut `True`.

- [ ] **Step 6: Confirmer qu'aucune régression sur la recherche existante**

Run :
```bash
python -c "
from sorabel_rag.recherche import rechercher
resultats = rechercher('REF-1024', k=3)
for r in resultats:
    print(r.reference, r.titre, round(r.score, 4))
"
```
Expected: 3 résultats, le premier portant `reference == 'REF-1024'` (le bonus de référence
sujet doit continuer à fonctionner après régénération de l'index).

Aucun commit pour cette tâche (sorties régénérables, hors git).
