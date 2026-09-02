# Phase 5 — Serveur MCP (stdio) et client de démonstration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer les huit tools du catalogue (`answer_question`, `search_docs`,
`get_document`, `list_sources`, `ask_database`, `get_schema`, `check_stock`, `order_status`)
via un vrai serveur MCP (SDK `mcp`, transport stdio), avec `tools/list` filtré par profil,
journalisation systématique, et un client CLI unique (`scripts/mcp_client.py --profil ...`)
qui rejoue la séquence de démonstration à deux profils de `docs/conception_mcp.md` §6.

**Architecture:** `get_document`/`list_sources` n'existaient dans aucune phase précédente —
Task 1 comble ce manque (`sorabel_rag/documents.py`). `mcp_server/tools.py` compose tout ce
qui existe déjà (Phases 1-4) sans dupliquer de logique : chaque tool MCP n'est qu'un routeur
vers `sorabel_rag`/`sorabel_sql` + journalisation. **`tools/list` filtré EST l'intercepteur
d'entrée dans cette architecture** — chaque processus serveur ne sert qu'un seul profil
(résolu une fois au démarrage via `SORABEL_PROFIL`), donc un tool non enregistré ne peut
structurellement pas être appelé par ce processus (cf. Global Constraints).

**Tech Stack:** SDK `mcp` 1.27.2 (déjà installé — `FastMCP`, `ClientSession`, `stdio_client`
introspectés avant d'écrire ce plan : `list_tools()`/`call_tool()` fonctionnent en mémoire
sans sous-processus, ce qui rend les tests rapides et sans E/S réseau).

## Global Constraints

- Langue du code de domaine, messages et tests : français.
- **Un processus serveur = un profil.** Le profil est résolu une seule fois au démarrage
  (`SORABEL_PROFIL`), jamais par appel. C'est une limite documentée du transport stdio (pas
  une authentification), assumée dans `docs/conception_mcp.md`.
- **Refus = retour normal, jamais une exception de protocole.** Chaque tool retourne un dict
  avec `statut` — `ok`, `hors_corpus`, `hors_schema`, `non_autorise`, `refuse_ecriture`.
- **Tout appel est journalisé**, y compris les appels autorisés qui aboutissent à `ok` — la
  journalisation n'est pas réservée aux refus.
- **Descriptions de tool en trois règles** (`docs/conception_mcp.md` §1) : dire quand NE PAS
  utiliser le tool, distinguer par le déclencheur de la question (pas par le mécanisme
  interne), documenter les statuts dans la description — respecter le texte des docstrings
  fourni dans ce plan, ne pas le raccourcir.
- Aucun appel réseau ni LLM dans les tests automatisés de cette phase — `get_schema`,
  `check_stock`, `order_status` (aucune dépendance LLM/Chroma) sont les seuls tools appelés
  par les tests automatisés. `answer_question`, `ask_database`, `search_docs` sont vérifiés
  manuellement dans la dernière tâche (nécessitent `.env` réel et l'index Chroma régénéré).
- Exécuter les tests avec `python -m pytest` depuis la racine du dépôt.

---

## File Structure

```
sorabel_rag/documents.py       NOUVEAU : obtenir_document(doc_id, perimetre=None) -> dict,
                                lister_sources(type_document=None, perimetre=None) -> dict
mcp_server/__init__.py          NOUVEAU : vide
mcp_server/tools.py             NOUVEAU : enregistrer_tools(mcp, perimetre) -> None
mcp_server/serveur.py           NOUVEAU : resoudre_profil(), construire_serveur()
scripts/mcp_client.py           NOUVEAU : client CLI --profil {support,commercial,dev,admin}
requirements.txt                MODIFIÉ : ajoute mcp
tests/test_documents.py         NOUVEAU
tests/test_mcp_tools.py         NOUVEAU
tests/test_mcp_serveur.py       NOUVEAU
```

---

### Task 1: `get_document` et `list_sources`

**Files:**
- Create: `sorabel_rag/documents.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Consumes: `sorabel_rag.ingestion.SORTIE` (`Path`, existant, Phase 1) ; un objet `perimetre`
  optionnel exposant `.collections_autorisees() -> frozenset[str]` (même contrat duck-typé que
  les phases précédentes ; `None` = aucune restriction).
- Produces: `sorabel_rag.documents.obtenir_document(doc_id: str | None = None, reference: str | None = None, version: str | None = None, perimetre=None) -> dict`
  (`{"statut": "ok", "document": dict}` ou `{"statut": "hors_schema"|"non_autorise", "message": str}`) —
  accepte **soit** `doc_id`, **soit** `reference` (+ `version` optionnelle, résolue vers la
  version courante du groupe si absente ; `hors_schema` si `reference` correspond à plusieurs
  types de document, ex. une fiche technique ET une notice partageant la même référence) ;
  `sorabel_rag.documents.lister_sources(type_document: str | None = None, perimetre=None) -> dict`
  (`{"statut": "ok", "sources": list[dict]}`). Task 2 (`mcp_server/tools.py`) les enveloppe
  telles quelles.

**Suppose que la Phase 1 (Task 4 : régénération) est terminée** — `data/canonique/` doit
contenir les canoniques régénérés avec `sous_type`/`diffusion_restreinte`. Les tests
utilisent de vrais fichiers du corpus (mêmes conventions que les phases précédentes).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_documents.py` :

```python
"""get_document et list_sources : accès direct aux documents canoniques et au manifeste."""

from sorabel_rag.documents import lister_sources, obtenir_document


class _PerimetreSansConfidentielles:
    def collections_autorisees(self):
        return frozenset({"fiches", "notices", "sav", "notes_operationnelles"})


class _PerimetreComplet:
    def collections_autorisees(self):
        return frozenset(
            {"fiches", "notices", "sav", "notes_operationnelles", "notes_confidentielles"}
        )


def test_obtenir_document_existant():
    resultat = obtenir_document("fiche_technique:REF-1024:v2.1")
    assert resultat["statut"] == "ok"
    assert resultat["document"]["reference"] == "REF-1024"
    assert resultat["document"]["type_document"] == "fiche_technique"


def test_obtenir_document_inexistant_est_hors_schema():
    resultat = obtenir_document("fiche_technique:REF-0000:v1.0")
    assert resultat["statut"] == "hors_schema"


def test_obtenir_document_sans_perimetre_nest_pas_restreint():
    doc_id = "note_interne:note-2024-03-03-politique-tarifaire-21:v1.0"
    resultat = obtenir_document(doc_id)
    assert resultat["statut"] == "ok"


def test_obtenir_document_note_confidentielle_refusee_hors_perimetre():
    doc_id = "note_interne:note-2024-03-03-politique-tarifaire-21:v1.0"
    resultat = obtenir_document(doc_id, perimetre=_PerimetreSansConfidentielles())
    assert resultat["statut"] == "non_autorise"


def test_obtenir_document_note_confidentielle_autorisee_avec_le_bon_perimetre():
    doc_id = "note_interne:note-2024-03-03-politique-tarifaire-21:v1.0"
    resultat = obtenir_document(doc_id, perimetre=_PerimetreComplet())
    assert resultat["statut"] == "ok"


def test_obtenir_document_fiche_technique_nest_jamais_restreint():
    # "fiches" est autorisée pour les deux périmètres de test : jamais de faux refus.
    resultat = obtenir_document(
        "fiche_technique:REF-1024:v2.1", perimetre=_PerimetreSansConfidentielles()
    )
    assert resultat["statut"] == "ok"


def test_obtenir_document_par_reference_resout_la_version_courante():
    # REF-1024 n'a qu'une fiche technique (v1.0, v2.1) — pas de notice : sans ambiguïté.
    resultat = obtenir_document(reference="REF-1024")
    assert resultat["statut"] == "ok"
    assert resultat["document"]["version"] == "2.1"


def test_obtenir_document_par_reference_et_version_explicite():
    resultat = obtenir_document(reference="REF-1024", version="1.0")
    assert resultat["statut"] == "ok"
    assert resultat["document"]["version"] == "1.0"


def test_obtenir_document_par_reference_ambigue_entre_fiche_et_notice():
    # REF-1459 a À LA FOIS une fiche technique ET une notice : la référence seule ne suffit
    # pas à choisir.
    resultat = obtenir_document(reference="REF-1459")
    assert resultat["statut"] == "hors_schema"
    assert "ambigu" in resultat["message"].lower()


def test_obtenir_document_par_reference_inconnue():
    resultat = obtenir_document(reference="REF-0000")
    assert resultat["statut"] == "hors_schema"


def test_obtenir_document_par_reference_version_inconnue():
    resultat = obtenir_document(reference="REF-1024", version="9.9")
    assert resultat["statut"] == "hors_schema"


def test_obtenir_document_sans_doc_id_ni_reference_est_hors_schema():
    resultat = obtenir_document()
    assert resultat["statut"] == "hors_schema"


def test_lister_sources_filtre_par_type_document():
    resultat = lister_sources(type_document="procedure_sav")
    assert resultat["statut"] == "ok"
    assert len(resultat["sources"]) > 0
    assert all(s["type_document"] == "procedure_sav" for s in resultat["sources"])


def test_lister_sources_exclut_notes_confidentielles_hors_perimetre():
    resultat = lister_sources(
        type_document="note_interne", perimetre=_PerimetreSansConfidentielles()
    )
    cles = {s["cle_groupe"] for s in resultat["sources"]}
    assert "note_interne:note-2024-03-03-politique-tarifaire-21" not in cles
    assert "note_interne:note-2024-06-05-logistique-08" in cles


def test_lister_sources_inclut_notes_confidentielles_avec_le_bon_perimetre():
    resultat = lister_sources(type_document="note_interne", perimetre=_PerimetreComplet())
    cles = {s["cle_groupe"] for s in resultat["sources"]}
    assert "note_interne:note-2024-03-03-politique-tarifaire-21" in cles
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_documents.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'sorabel_rag.documents'`

- [ ] **Step 3: Écrire `sorabel_rag/documents.py`**

```python
"""get_document et list_sources — accès direct aux documents canoniques et au manifeste.

Contrairement à search_docs/answer_question, ces deux tools ne passent pas par l'index
Chroma : ils lisent directement les fichiers produits par l'ingestion (chantier 1).
"""

from __future__ import annotations

import json

from .ingestion import SORTIE

COLLECTION_PAR_TYPE = {
    "fiche_technique": "fiches",
    "notice": "notices",
    "procedure_sav": "sav",
}
SOUS_TYPES_OPERATIONNELS = frozenset({"logistique", "alerte_qualite", "retour_terrain"})
SOUS_TYPES_CONFIDENTIELS = frozenset({"politique_tarifaire", "reunion_achat"})


def _collection_depuis_sous_type(sous_type: str) -> str | None:
    if sous_type in SOUS_TYPES_OPERATIONNELS:
        return "notes_operationnelles"
    if sous_type in SOUS_TYPES_CONFIDENTIELS:
        return "notes_confidentielles"
    return None


def _collection_du_document(type_document: str, attributs: dict) -> str | None:
    if type_document in COLLECTION_PAR_TYPE:
        return COLLECTION_PAR_TYPE[type_document]
    if type_document == "note_interne":
        return _collection_depuis_sous_type(attributs.get("sous_type", ""))
    return None


def _resoudre_doc_id_par_reference(reference: str, version: str | None) -> tuple[str | None, dict | None]:
    """`(doc_id, None)` si résolu, `(None, refus)` sinon. Une référence peut être partagée par
    plusieurs types de document (fiche technique ET notice) : sans version, la version
    courante du groupe unique est prise ; si plusieurs groupes matchent, c'est ambigu."""
    manifeste = json.loads((SORTIE / "_manifeste.json").read_text(encoding="utf-8"))
    candidats = {
        cle: groupe for cle, groupe in manifeste["groupes"].items()
        if groupe.get("reference") == reference
    }
    if not candidats:
        return None, {"statut": "hors_schema", "message": f"référence introuvable : {reference!r}"}
    if len(candidats) > 1:
        return None, {
            "statut": "hors_schema",
            "message": (
                f"référence {reference!r} ambiguë entre plusieurs types de document : "
                f"{', '.join(sorted(candidats))} — précisez un doc_id."
            ),
        }
    (groupe,) = candidats.values()
    if version is None:
        return groupe["doc_id_courant"], None
    correspondance = dict(zip(groupe["versions"], groupe["doc_ids"]))
    if version not in correspondance:
        return None, {
            "statut": "hors_schema",
            "message": f"version {version!r} introuvable pour {reference!r} "
                       f"(versions disponibles : {groupe['versions']})",
        }
    return correspondance[version], None


def obtenir_document(
    doc_id: str | None = None,
    reference: str | None = None,
    version: str | None = None,
    perimetre=None,
) -> dict:
    if doc_id is None and reference is None:
        return {
            "statut": "hors_schema",
            "message": "fournir doc_id, ou reference (+ version optionnelle)",
        }

    if doc_id is None:
        doc_id, refus = _resoudre_doc_id_par_reference(reference, version)
        if refus is not None:
            return refus

    chemin = SORTIE / f"{doc_id.replace(':', '__')}.json"
    if not chemin.exists():
        return {"statut": "hors_schema", "message": f"document introuvable : {doc_id!r}"}

    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    if perimetre is not None:
        collection = _collection_du_document(donnees["type_document"], donnees.get("attributs", {}))
        if collection is not None and collection not in perimetre.collections_autorisees():
            return {
                "statut": "non_autorise",
                "message": f"ce profil n'a pas accès à la collection {collection!r}",
            }

    return {"statut": "ok", "document": donnees}


def _collection_du_groupe(groupe: dict) -> str | None:
    type_document = groupe["type_document"]
    if type_document in COLLECTION_PAR_TYPE:
        return COLLECTION_PAR_TYPE[type_document]
    if type_document == "note_interne":
        chemin = SORTIE / f"{groupe['doc_id_courant'].replace(':', '__')}.json"
        if chemin.exists():
            attributs = json.loads(chemin.read_text(encoding="utf-8")).get("attributs", {})
            return _collection_depuis_sous_type(attributs.get("sous_type", ""))
    return None


def lister_sources(type_document: str | None = None, perimetre=None) -> dict:
    manifeste = json.loads((SORTIE / "_manifeste.json").read_text(encoding="utf-8"))
    collections_autorisees = perimetre.collections_autorisees() if perimetre is not None else None

    inventaire = []
    for cle, groupe in manifeste["groupes"].items():
        if type_document and groupe["type_document"] != type_document:
            continue
        if collections_autorisees is not None:
            collection = _collection_du_groupe(groupe)
            if collection is not None and collection not in collections_autorisees:
                continue
        inventaire.append({
            "cle_groupe": cle,
            "type_document": groupe["type_document"],
            "reference": groupe.get("reference"),
            "titre": groupe["titre"],
            "versions": groupe["versions"],
            "version_courante": groupe["version_courante"],
        })
    return {"statut": "ok", "sources": inventaire}
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_documents.py -v`
Expected: `15 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `95 passed` (80 des Phases 1-4 + 15 de cette tâche)

- [ ] **Step 6: Commit**

```bash
git add sorabel_rag/documents.py tests/test_documents.py
git commit -m "feat(rag): get_document et list_sources, filtrés par collections de gouvernance"
```

---

### Task 2: Enregistrement des tools MCP, filtré par profil

**Files:**
- Create: `mcp_server/__init__.py`
- Create: `mcp_server/tools.py`
- Modify: `requirements.txt`
- Test: `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `gouvernance.perimetre.Perimetre` (Phase 4) ; `gouvernance.journal.journaliser`
  (Phase 4) ; `sorabel_rag.generation.repondre`, `sorabel_rag.recherche.rechercher`,
  `sorabel_rag.documents.obtenir_document`/`lister_sources` (Task 1) ;
  `sorabel_sql.tools.ask_database`/`get_schema`/`check_stock`/`order_status` (Phase 3).
- Produces: `mcp_server.tools.enregistrer_tools(mcp: FastMCP, perimetre: Perimetre) -> None` —
  Task 3 (`serveur.py`) est le seul appelant.

- [ ] **Step 1: Ajouter la dépendance**

Dans `requirements.txt`, ajouter à la fin :

```
# Serveur MCP
mcp>=1.20
```

- [ ] **Step 2: Écrire les tests qui échouent**

Créer `mcp_server/__init__.py` (vide).

Créer `tests/test_mcp_tools.py` :

```python
"""Enregistrement des tools MCP filtré par profil (tools/list = intercepteur d'entrée ici)."""

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre
from gouvernance.seed import peupler
from gouvernance import journal
from mcp_server.tools import enregistrer_tools


def _construire(profil: str, tmp_path) -> FastMCP:
    chemin_gouvernance = tmp_path / "gouvernance.db"
    peupler(chemin_gouvernance)
    matrice = charger_matrice(chemin_gouvernance)
    perimetre = Perimetre(profil, matrice)
    mcp = FastMCP(name="test-sorabel")
    enregistrer_tools(mcp, perimetre)
    return mcp


def test_dev_ne_voit_ni_answer_question_ni_ask_database_ni_check_stock_ni_order_status(tmp_path):
    mcp = _construire("dev", tmp_path)
    noms = {t.name for t in asyncio.run(mcp.list_tools())}
    assert noms == {"search_docs", "get_document", "list_sources", "get_schema"}


def test_support_voit_les_huit_tools(tmp_path):
    mcp = _construire("support", tmp_path)
    noms = {t.name for t in asyncio.run(mcp.list_tools())}
    assert noms == {
        "answer_question", "search_docs", "get_document", "list_sources",
        "ask_database", "get_schema", "check_stock", "order_status",
    }


def test_get_schema_fonctionne_sans_llm_ni_chroma(tmp_path):
    mcp = _construire("support", tmp_path)
    blocs = asyncio.run(mcp.call_tool("get_schema", {}))
    resultat = json.loads(blocs[0].text)
    assert resultat["statut"] == "ok"
    assert "CREATE TABLE produits" in resultat["schema"]
    assert "prix_achat_ht" not in resultat["schema"]


def test_check_stock_fonctionne_sans_llm(tmp_path):
    mcp = _construire("commercial", tmp_path)
    blocs = asyncio.run(mcp.call_tool("check_stock", {"ref": "REF-1024"}))
    resultat = json.loads(blocs[0].text)
    assert resultat["statut"] == "ok"


def test_order_status_ref_invalide_est_hors_schema(tmp_path):
    mcp = _construire("commercial", tmp_path)
    blocs = asyncio.run(mcp.call_tool("order_status", {"order_id": "PAS-UN-ID"}))
    resultat = json.loads(blocs[0].text)
    assert resultat["statut"] == "hors_schema"


def test_get_document_par_reference_resout_la_version_courante(tmp_path):
    mcp = _construire("support", tmp_path)
    blocs = asyncio.run(mcp.call_tool("get_document", {"reference": "REF-1024"}))
    resultat = json.loads(blocs[0].text)
    assert resultat["statut"] == "ok"
    assert resultat["document"]["version"] == "2.1"


def test_chaque_appel_est_journalise(tmp_path, monkeypatch):
    chemin_journal = tmp_path / "appels.jsonl"
    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", chemin_journal)

    mcp = _construire("commercial", tmp_path)
    asyncio.run(mcp.call_tool("check_stock", {"ref": "REF-1024"}))

    lignes = chemin_journal.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 1
    ligne = json.loads(lignes[0])
    assert ligne["tool"] == "check_stock"
    assert ligne["profil"] == "commercial"
    assert ligne["autorise"] is True
```

- [ ] **Step 3: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_mcp_tools.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'mcp_server.tools'`

- [ ] **Step 4: Écrire `mcp_server/tools.py`**

```python
"""Enregistre les tools MCP autorisés pour un profil donné.

tools/list filtré EST l'intercepteur d'entrée dans cette architecture (Global Constraints du
plan) : chaque processus serveur ne sert qu'un seul profil, résolu une fois au démarrage —
il n'existe donc structurellement aucun moyen d'appeler un tool non enregistré ici.

Les imports de sorabel_sql.tools sont aliasés pour éviter toute collision de nom avec les
fonctions MCP de même nom définies plus bas (ask_database, get_schema, check_stock,
order_status) — sans l'alias, la fonction imbriquée masquerait l'import au lieu de l'appeler.
"""

from __future__ import annotations

import time

from gouvernance.journal import journaliser
from gouvernance.perimetre import Perimetre
from sorabel_rag.documents import lister_sources, obtenir_document
from sorabel_rag.generation import repondre
from sorabel_rag.recherche import rechercher
from sorabel_sql.tools import ask_database as _sql_ask_database
from sorabel_sql.tools import check_stock as _sql_check_stock
from sorabel_sql.tools import get_schema as _sql_get_schema
from sorabel_sql.tools import order_status as _sql_order_status


def enregistrer_tools(mcp, perimetre: Perimetre) -> None:
    profil = perimetre.profil

    def _journaliser(tool: str, entrees: dict, resultat: dict, debut: float) -> dict:
        journaliser(
            profil=profil, tool=tool, autorise=True,
            statut=resultat.get("statut", "ok"), entrees=entrees,
            sql=resultat.get("sql"), n_lignes=resultat.get("n_lignes", 0),
            duree_ms=(time.monotonic() - debut) * 1000,
            motif=resultat.get("message"),
        )
        return resultat

    if perimetre.peut_appeler("answer_question"):
        @mcp.tool()
        def answer_question(question: str) -> dict:
            """Réponse rédigée avec sources, à partir du corpus documentaire Sorabel.
            N'utilisez PAS ce tool pour obtenir des extraits bruts : voyez search_docs.
            Statuts possibles : ok, hors_corpus (aucune réponse trouvée, à afficher tel quel,
            pas comme une panne)."""
            debut = time.monotonic()
            resultat = repondre(question, perimetre=perimetre)
            return _journaliser("answer_question", {"question": question}, resultat, debut)

    if perimetre.peut_appeler("search_docs"):
        @mcp.tool()
        def search_docs(requete: str, k: int = 5, type_document: str | None = None) -> dict:
            """Recherche documentaire hybride : extraits bruts + scores, AUCUNE génération.
            N'utilisez PAS ce tool pour obtenir une réponse rédigée : voyez answer_question."""
            debut = time.monotonic()
            resultats = rechercher(
                requete, k=k, type_document=type_document,
                collections_autorisees=perimetre.collections_autorisees(),
            )
            resultat = {
                "statut": "ok",
                "resultats": [
                    {"chunk_id": r.chunk_id, "texte": r.texte, "score": r.score,
                     "titre": r.titre, "reference": r.reference}
                    for r in resultats
                ],
            }
            return _journaliser("search_docs", {"requete": requete}, resultat, debut)

    if perimetre.peut_appeler("get_document"):
        @mcp.tool()
        def get_document(
            doc_id: str | None = None,
            reference: str | None = None,
            version: str | None = None,
        ) -> dict:
            """Document canonique complet, par doc_id OU par (reference + version optionnelle
            — version courante par défaut si omise). Voir list_sources ou search_docs pour
            obtenir un doc_id ou une référence. Statuts : ok, hors_schema (introuvable, ou
            reference ambiguë entre plusieurs types de document), non_autorise (collection
            hors périmètre du profil)."""
            debut = time.monotonic()
            resultat = obtenir_document(doc_id, reference, version, perimetre=perimetre)
            entrees = {"doc_id": doc_id, "reference": reference, "version": version}
            return _journaliser("get_document", entrees, resultat, debut)

    if perimetre.peut_appeler("list_sources"):
        @mcp.tool()
        def list_sources(type_document: str | None = None) -> dict:
            """Inventaire des documents indexés et de leurs versions, reflète le périmètre
            du profil (une note confidentielle hors périmètre n'apparaît pas)."""
            debut = time.monotonic()
            resultat = lister_sources(type_document, perimetre=perimetre)
            return _journaliser("list_sources", {"type_document": type_document}, resultat, debut)

    if perimetre.peut_appeler("ask_database"):
        @mcp.tool()
        def ask_database(question: str) -> dict:
            """Question en langage naturel sur les données Sorabel (produits, stocks, clients,
            commandes, ventes). Utilisez ce tool quand la question demande un CALCUL ou un
            AGRÉGAT. Lecture seule ; renvoie toujours le SQL exécuté ou rejeté. Statuts :
            ok, hors_schema, non_autorise, refuse_ecriture."""
            debut = time.monotonic()
            resultat = _sql_ask_database(question, perimetre)
            return _journaliser("ask_database", {"question": question}, resultat, debut)

    if perimetre.peut_appeler("get_schema"):
        @mcp.tool()
        def get_schema() -> dict:
            """Schéma commenté des tables SQL tel que ce profil le voit (mêmes colonnes que
            celles disponibles via ask_database)."""
            debut = time.monotonic()
            resultat = _sql_get_schema(perimetre)
            return _journaliser("get_schema", {}, resultat, debut)

    if perimetre.peut_appeler("check_stock"):
        @mcp.tool()
        def check_stock(ref: str) -> dict:
            """Stock par entrepôt pour UNE référence précise (format REF-XXXX). Utilisez ce
            tool quand la question porte sur une référence précise, pas un agrégat — pour un
            agrégat (ex. "quelles références sont sous le seuil ?"), voyez ask_database."""
            debut = time.monotonic()
            resultat = _sql_check_stock(ref)
            return _journaliser("check_stock", {"ref": ref}, resultat, debut)

    if perimetre.peut_appeler("order_status"):
        @mcp.tool()
        def order_status(order_id: str) -> dict:
            """Statut, date et montant d'UNE commande précise (format CMD-AAAA-NNNN)."""
            debut = time.monotonic()
            resultat = _sql_order_status(order_id)
            return _journaliser("order_status", {"order_id": order_id}, resultat, debut)
```

- [ ] **Step 5: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_mcp_tools.py -v`
Expected: `7 passed`

- [ ] **Step 6: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `102 passed`

- [ ] **Step 7: Commit**

```bash
git add mcp_server/__init__.py mcp_server/tools.py requirements.txt tests/test_mcp_tools.py
git commit -m "feat(mcp): enregistrement des 8 tools, filtré par profil"
```

---

### Task 3: Le serveur (résolution du profil, démarrage)

**Files:**
- Create: `mcp_server/serveur.py`
- Test: `tests/test_mcp_serveur.py`

**Interfaces:**
- Consumes: `gouvernance.modeles.charger_matrice`, `gouvernance.perimetre.Perimetre`/
  `ProfilInconnu` (Phase 4) ; `mcp_server.tools.enregistrer_tools` (Task 2).
- Produces: `mcp_server.serveur.resoudre_profil() -> str` (lève `RuntimeError` si
  `SORABEL_PROFIL` absent) ; `mcp_server.serveur.construire_serveur(chemin_gouvernance_db=...) -> FastMCP`.
  Task 4 (`scripts/mcp_client.py`) lance `python -m mcp_server.serveur` comme sous-processus.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_mcp_serveur.py` :

```python
"""Construction du serveur MCP : résolution du profil (SEUL point dépendant du transport),
chargement et validation de la matrice au démarrage."""

import asyncio

import pytest

from gouvernance.perimetre import ProfilInconnu
from gouvernance.seed import peupler
from mcp_server.serveur import construire_serveur, resoudre_profil


def test_resoudre_profil_leve_si_variable_absente(monkeypatch):
    monkeypatch.delenv("SORABEL_PROFIL", raising=False)
    with pytest.raises(RuntimeError, match="SORABEL_PROFIL"):
        resoudre_profil()


def test_resoudre_profil_lit_la_variable_denvironnement(monkeypatch):
    monkeypatch.setenv("SORABEL_PROFIL", "commercial")
    assert resoudre_profil() == "commercial"


def test_construire_serveur_enregistre_les_bons_tools(tmp_path, monkeypatch):
    chemin_gouvernance = tmp_path / "gouvernance.db"
    peupler(chemin_gouvernance)
    monkeypatch.setenv("SORABEL_PROFIL", "dev")

    mcp = construire_serveur(chemin_gouvernance_db=chemin_gouvernance)

    noms = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "ask_database" not in noms
    assert "search_docs" in noms


def test_construire_serveur_profil_inconnu_leve(tmp_path, monkeypatch):
    chemin_gouvernance = tmp_path / "gouvernance.db"
    peupler(chemin_gouvernance)
    monkeypatch.setenv("SORABEL_PROFIL", "stagiaire")

    with pytest.raises(ProfilInconnu):
        construire_serveur(chemin_gouvernance_db=chemin_gouvernance)
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_mcp_serveur.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'mcp_server.serveur'`

- [ ] **Step 3: Écrire `mcp_server/serveur.py`**

```python
"""Serveur MCP stdio : résout le profil, charge et valide la matrice au démarrage, enregistre
les tools autorisés.

`resoudre_profil` est le SEUL point qui dépend du transport (ici, stdio : variable
d'environnement du sous-processus). Passer en HTTP/OAuth ne toucherait que cette fonction —
tout le reste (matrice, Perimetre, tools) est inchangé d'un transport à l'autre.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre

from .tools import enregistrer_tools

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_GOUVERNANCE_DB = RACINE / "gouvernance" / "gouvernance.db"


def resoudre_profil() -> str:
    profil = os.environ.get("SORABEL_PROFIL")
    if not profil:
        raise RuntimeError(
            "SORABEL_PROFIL doit être défini avant de lancer le serveur "
            "(ex. SORABEL_PROFIL=support python -m mcp_server.serveur)"
        )
    return profil


def construire_serveur(chemin_gouvernance_db: Path = CHEMIN_GOUVERNANCE_DB) -> FastMCP:
    matrice = charger_matrice(chemin_gouvernance_db)
    perimetre = Perimetre(resoudre_profil(), matrice)
    mcp = FastMCP(name="sorabel-data-gateway")
    enregistrer_tools(mcp, perimetre)
    return mcp


if __name__ == "__main__":
    construire_serveur().run(transport="stdio")
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_mcp_serveur.py -v`
Expected: `4 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `106 passed`

- [ ] **Step 6: Commit**

```bash
git add mcp_server/serveur.py tests/test_mcp_serveur.py
git commit -m "feat(mcp): serveur stdio, résolution du profil, démarrage bloquant si matrice invalide"
```

---

### Task 4: Client CLI de démonstration (`scripts/mcp_client.py`)

**Files:**
- Create: `scripts/mcp_client.py`

**Interfaces:**
- Consumes: `mcp_server.serveur` lancé comme sous-processus (`python -m mcp_server.serveur`,
  variable d'environnement `SORABEL_PROFIL`) ; SDK `mcp.client.stdio.stdio_client`,
  `mcp.ClientSession`.
- Produces: un script exécutable `python scripts/mcp_client.py --profil {support,commercial,dev,admin}` —
  aucune autre tâche n'en dépend, c'est un livrable terminal du chantier 3.

Pas de test automatisé pour cette tâche : c'est un client de démonstration interactif, sa
vérification se fait à l'exécution (Task 5).

- [ ] **Step 1: Écrire `scripts/mcp_client.py`**

```python
"""Client MCP unique : `--profil {support,commercial,dev,admin}`.

Même code, même serveur, même séquence d'appels — seul le profil change. C'est ce qui rend
le contraste entre profils démontrable : avec quatre clients différents, on ne pourrait pas
écarter l'hypothèse que la différence de réponse vient du client plutôt que de la matrice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RACINE = Path(__file__).resolve().parent.parent


async def _appeler(session: ClientSession, tool: str, arguments: dict) -> dict:
    resultat = await session.call_tool(tool, arguments)
    bloc = resultat.content[0] if resultat.content else None
    if bloc is None or not hasattr(bloc, "text"):
        return {"erreur": "réponse MCP sans contenu textuel"}
    return json.loads(bloc.text)


async def demo(profil: str) -> None:
    parametres = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.serveur"],
        env={"SORABEL_PROFIL": profil},
        cwd=str(RACINE),
    )
    async with stdio_client(parametres) as (lecture, ecriture):
        async with ClientSession(lecture, ecriture) as session:
            await session.initialize()
            outils = await session.list_tools()
            noms_outils = sorted(t.name for t in outils.tools)
            print(f"\n=== profil : {profil} — tools disponibles : {noms_outils} ===")

            print(f"\n[{profil}] search_docs('politique tarifaire')")
            resultat = await _appeler(session, "search_docs", {"requete": "politique tarifaire"})
            titres = [r["titre"] for r in resultat.get("resultats", [])]
            print(f"  titres trouvés : {titres}")

            if "ask_database" in noms_outils:
                print(f"\n[{profil}] ask_database('quelle est la marge sur REF-1024 ?')")
                print(" ", await _appeler(session, "ask_database", {"question": "quelle est la marge sur REF-1024 ?"}))

                print(f"\n[{profil}] ask_database('combien de commandes en avril ?')")
                print(" ", await _appeler(session, "ask_database", {"question": "combien de commandes en avril ?"}))

                print(f"\n[{profil}] ask_database('supprime les commandes de test')")
                print(" ", await _appeler(session, "ask_database", {"question": "supprime les commandes de test"}))

            print(f"\n[{profil}] get_schema()")
            schema = await _appeler(session, "get_schema", {})
            print("  contient marge_pct :", "marge_pct" in schema.get("schema", ""))


if __name__ == "__main__":
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--profil", required=True, choices=["support", "commercial", "dev", "admin"]
    )
    arguments = analyseur.parse_args()
    asyncio.run(demo(arguments.profil))
```

- [ ] **Step 2: Commit**

```bash
git add scripts/mcp_client.py
git commit -m "feat(mcp): client CLI de démonstration --profil {support,commercial,dev,admin}"
```

---

### Task 5: Vérification manuelle — contraste `support` vs `commercial` (livrable §6)

**⚠️ Nécessite : Phase 1 Task 4 terminée (index Chroma régénéré), Phase 2 Task 3 terminée
(`.env` réel), `data/sorabel.db` présent. Consomme de vrais appels Azure AI Foundry — ne pas
dispatcher à un sous-agent sans confirmation de l'utilisateur.**

**Files:** aucun — vérification manuelle, rien à committer sauf `gouvernance/gouvernance.db`
n'est PAS committé (ignoré, régénérable).

- [ ] **Step 1: Peupler la matrice de gouvernance par défaut**

Run: `python scripts/seed_gouvernance.py`
Expected: `-> .../gouvernance/gouvernance.db`

- [ ] **Step 2: Rejouer la séquence sous `support`**

Run: `python scripts/mcp_client.py --profil support`

Expected (comparer à `docs/conception_mcp.md` §6) :
- `tools disponibles` contient les 8 tools.
- `search_docs('politique tarifaire')` → **aucun** titre de note confidentielle dans les résultats.
- `ask_database('quelle est la marge sur REF-1024 ?')` → `statut: non_autorise`.
- `ask_database('combien de commandes en avril ?')` → `statut: ok`, résultat = **27**.
- `ask_database('supprime les commandes de test')` → `statut: refuse_ecriture`.
- `get_schema()` → `contient marge_pct : False`.

- [ ] **Step 3: Rejouer la séquence sous `commercial`**

Run: `python scripts/mcp_client.py --profil commercial`

Expected :
- `search_docs('politique tarifaire')` → **au moins un** titre de note confidentielle présent.
- `ask_database('quelle est la marge sur REF-1024 ?')` → `statut: ok` (+ SQL + résultat).
- `ask_database('combien de commandes en avril ?')` → `statut: ok`, résultat = **27** (identique à support).
- `ask_database('supprime les commandes de test')` → `statut: refuse_ecriture` (identique à support — **aucun** profil n'écrit).
- `get_schema()` → `contient marge_pct : True`.

- [ ] **Step 4: Ouvrir le journal**

Run (PowerShell) : `Get-Content logs/appels.jsonl | Select-Object -Last 12`
Expected : les 12 derniers appels des deux séquences y figurent (6 par profil : search_docs,
3× ask_database, get_schema — + éventuellement des appels antérieurs des tests), chacun avec
`profil`, `tool`, `autorise`, `statut`. Vérifier que la ligne `ask_database` refusée pour
`support` porte bien `"autorise": true` au niveau du tool (le tool a été appelé et a répondu,
c'est `statut` qui vaut `non_autorise` — pas une erreur d'autorisation d'accès au tool
lui-même, puisque `support` a le droit d'appeler `ask_database`).

Si les deux séquences correspondent aux résultats attendus, E4 et E5 sont démontrées de bout
en bout. Aucun commit pour cette tâche.
