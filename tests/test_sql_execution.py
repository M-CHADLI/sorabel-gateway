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
