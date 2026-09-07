"""Enregistrement des tools MCP : les 8 tools sont désormais TOUJOURS enregistrés, quel que
soit le profil ; le contrôle d'accès se fait à l'appel, dans le décorateur `_gouverne` de
mcp_server.tools (Task 4). En stdio, `tools/list` filtré tenait lieu d'intercepteur d'entrée
puisqu'un processus ne servait qu'un seul profil résolu au démarrage ; en HTTP, le profil
vient du jeton à chaque requête, donc le contrôle descend dans le décorateur."""

import asyncio
import json

import pytest
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
    # Résolveur trivial : dans ces tests le profil ne change pas d'un appel à l'autre, mais
    # la signature attendue par enregistrer_tools est bien un appelable, pas un Perimetre.
    enregistrer_tools(mcp, lambda: perimetre)
    return mcp


def test_les_huit_tools_sont_toujours_enregistres_quel_que_soit_le_profil(tmp_path):
    for profil in ("dev", "support", "commercial", "admin"):
        mcp = _construire(profil, tmp_path)
        noms = {t.name for t in asyncio.run(mcp.list_tools())}
        assert noms == {
            "answer_question", "search_docs", "get_document", "list_sources",
            "ask_database", "get_schema", "check_stock", "order_status",
        }


def test_dev_ne_peut_pas_appeler_answer_question_ask_database_check_stock_order_status(tmp_path):
    mcp = _construire("dev", tmp_path)
    for nom_tool, arguments in [
        ("answer_question", {"question": "combien ?"}),
        ("ask_database", {"question": "combien ?"}),
        ("check_stock", {"ref": "REF-1024"}),
        ("order_status", {"order_id": "CMD-2024-0001"}),
    ]:
        blocs = asyncio.run(mcp.call_tool(nom_tool, arguments))
        resultat = json.loads(blocs[0].text)
        assert resultat["statut"] == "non_autorise"


def test_support_peut_appeler_les_huit_tools(tmp_path):
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


def test_un_refus_est_journalise_comme_un_appel(tmp_path, monkeypatch):
    """C'est ce que l'architecture stdio ne permettait pas : un tool hors périmètre n'y
    existait structurellement pas, donc son refus ne pouvait pas être journalisé."""
    chemin_journal = tmp_path / "appels.jsonl"
    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", chemin_journal)

    mcp = _construire("dev", tmp_path)
    asyncio.run(mcp.call_tool("ask_database", {"question": "combien ?"}))

    lignes = chemin_journal.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 1
    ligne = json.loads(lignes[0])
    assert ligne["tool"] == "ask_database"
    assert ligne["profil"] == "dev"
    assert ligne["autorise"] is False
    assert ligne["statut"] == "non_autorise"


class _PerimetreFactice:
    """Le contrôle passe du démarrage à la requête : c'est le changement structurel du
    passage en HTTP. Un processus ne sert plus un profil unique."""

    def __init__(self, profil, tools):
        self.profil = profil
        self._tools = set(tools)

    def peut_appeler(self, tool):
        return tool in self._tools

    def collections_autorisees(self):
        return frozenset({"fiches"})

    def tables_autorisees(self):
        return frozenset({"produits"})

    def colonnes_interdites(self, table):
        return frozenset()


def test_les_huit_tools_sont_enregistres_quel_que_soit_le_profil():
    from mcp.server.fastmcp import FastMCP
    from mcp_server.tools import enregistrer_tools

    mcp = FastMCP(name="test")
    enregistrer_tools(mcp, lambda: _PerimetreFactice("dev", {"search_docs"}))
    noms = {outil.name for outil in mcp._tool_manager.list_tools()}
    assert len(noms) == 8


@pytest.mark.anyio
async def test_un_tool_hors_perimetre_renvoie_non_autorise_et_est_journalise(monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from mcp_server.tools import enregistrer_tools
    import gouvernance.journal as journal

    traces = []
    monkeypatch.setattr(journal, "journaliser", lambda **kw: traces.append(kw))
    import mcp_server.tools as tools_module
    monkeypatch.setattr(tools_module, "journaliser", lambda **kw: traces.append(kw))

    mcp = FastMCP(name="test")
    enregistrer_tools(mcp, lambda: _PerimetreFactice("dev", {"search_docs"}))
    resultat = await mcp._tool_manager.call_tool("ask_database", {"question": "combien ?"})

    assert resultat["statut"] == "non_autorise"
    assert traces and traces[-1]["autorise"] is False
    assert traces[-1]["tool"] == "ask_database"


@pytest.fixture
def anyio_backend():
    return "asyncio"
