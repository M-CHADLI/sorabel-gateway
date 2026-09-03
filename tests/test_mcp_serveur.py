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
