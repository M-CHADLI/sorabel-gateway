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
