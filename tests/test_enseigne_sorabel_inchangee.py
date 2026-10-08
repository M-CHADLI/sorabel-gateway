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
