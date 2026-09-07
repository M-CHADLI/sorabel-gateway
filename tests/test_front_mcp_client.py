"""Pont Streamlit <-> serveur MCP : une connexion stdio de courte durée par appel."""

from gouvernance.seed import peupler
from mcp_server.serveur import CHEMIN_GOUVERNANCE_DB

from front.mcp_client import appeler, lister_tools


def test_lister_tools_dev_a_aussi_les_huit_tools_mais_ne_peut_pas_appeler_ask_database():
    """Depuis la Task 4, tools/list n'est plus filtré par profil (les 8 tools existent
    toujours, quel que soit le profil) : le refus se constate à l'appel, pas au listing."""
    peupler(CHEMIN_GOUVERNANCE_DB)  # même base que scripts/seed_gouvernance.py
    noms = lister_tools("dev")
    assert "ask_database" in noms
    assert "search_docs" in noms
    resultat = appeler("dev", "ask_database", {"question": "combien de produits ?"})
    assert resultat["statut"] == "non_autorise"


def test_lister_tools_support_a_les_huit_tools():
    peupler(CHEMIN_GOUVERNANCE_DB)
    noms = lister_tools("support")
    assert len(noms) == 8


def test_appeler_get_schema_fonctionne_sans_llm():
    peupler(CHEMIN_GOUVERNANCE_DB)
    resultat = appeler("commercial", "get_schema", {})
    assert resultat["statut"] == "ok"
    assert "marge_pct" in resultat["schema"]


def test_appeler_get_schema_support_exclut_marge_pct():
    peupler(CHEMIN_GOUVERNANCE_DB)
    resultat = appeler("support", "get_schema", {})
    assert "marge_pct" not in resultat["schema"]


def test_appeler_tool_non_autorise_est_signale_sans_exception():
    peupler(CHEMIN_GOUVERNANCE_DB)
    resultat = appeler("dev", "ask_database", {"question": "combien de produits ?"})
    assert resultat["statut"] == "non_autorise"
