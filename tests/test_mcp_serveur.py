"""Construction du serveur MCP : résolution du profil (SEUL point dépendant du transport),
chargement et validation de la matrice au démarrage. Depuis la Task 4, l'enregistrement des
tools n'est plus filtré par profil (cf. mcp_server.tools) : ce fichier ne teste donc plus le
filtrage de tools/list, seulement la résolution du profil et la validation de la matrice."""

import asyncio

import pytest

from gouvernance.perimetre import ProfilInconnu
from gouvernance.seed import peupler
from mcp_server.serveur import construire_serveur, resoudre_profil_stdio


def test_resoudre_profil_leve_si_variable_absente(monkeypatch):
    monkeypatch.delenv("SORABEL_PROFIL", raising=False)
    with pytest.raises(RuntimeError, match="SORABEL_PROFIL"):
        resoudre_profil_stdio()


def test_resoudre_profil_lit_la_variable_denvironnement(monkeypatch):
    monkeypatch.setenv("SORABEL_PROFIL", "commercial")
    assert resoudre_profil_stdio() == "commercial"


def test_construire_serveur_enregistre_toujours_les_huit_tools(tmp_path, monkeypatch):
    """Depuis la Task 4, l'enregistrement n'est plus filtré par profil : les 8 tools sont
    toujours enregistrés, et c'est le décorateur de mcp_server.tools qui refuse à l'appel
    (ask_database reste hors de portée du profil dev, mais le tool existe désormais)."""
    chemin_gouvernance = tmp_path / "gouvernance.db"
    peupler(chemin_gouvernance)
    monkeypatch.setenv("SORABEL_PROFIL", "dev")

    mcp = construire_serveur(chemin_gouvernance_db=chemin_gouvernance)

    noms = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "ask_database" in noms
    assert "search_docs" in noms
    assert len(noms) == 8


def test_construire_serveur_profil_inconnu_leve(tmp_path, monkeypatch):
    chemin_gouvernance = tmp_path / "gouvernance.db"
    peupler(chemin_gouvernance)
    monkeypatch.setenv("SORABEL_PROFIL", "stagiaire")

    with pytest.raises(ProfilInconnu):
        construire_serveur(chemin_gouvernance_db=chemin_gouvernance)


def test_en_stdio_le_profil_vient_de_la_variable_d_environnement(monkeypatch, tmp_path):
    from gouvernance.seed import peupler
    from mcp_server.serveur import construire_serveur

    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    monkeypatch.setenv("SORABEL_TRANSPORT", "stdio")
    monkeypatch.setenv("SORABEL_PROFIL", "support")
    serveur = construire_serveur(chemin)
    assert serveur is not None


def test_en_http_la_variable_de_profil_est_ignoree(monkeypatch, tmp_path):
    """Accepter SORABEL_PROFIL en HTTP rouvrirait exactement la faille qu'on ferme :
    l'appelant qui déclare son identité."""
    from gouvernance.seed import peupler
    from mcp_server.serveur import resoudre_profil_http

    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    monkeypatch.setenv("SORABEL_TRANSPORT", "http")
    monkeypatch.setenv("SORABEL_PROFIL", "admin")

    from gouvernance.identites import DepotIdentitesSqlite
    depot = DepotIdentitesSqlite(chemin)

    with pytest.raises(PermissionError, match="aucun profil"):
        resoudre_profil_http(depot, sujet="sub-inconnu")


def test_en_http_le_profil_vient_du_depot(monkeypatch, tmp_path):
    from gouvernance.identites import DepotIdentitesSqlite
    from gouvernance.seed import peupler
    from mcp_server.serveur import resoudre_profil_http

    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    depot = DepotIdentitesSqlite(chemin)
    depot.attribuer("sub-123", "support", source="demo")
    assert resoudre_profil_http(depot, sujet="sub-123") == "support"
