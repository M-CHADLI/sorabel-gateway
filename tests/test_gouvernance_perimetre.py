"""Perimetre : les droits d'un profil, sous la forme que les tools consomment."""

import pytest

from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre, ProfilInconnu
from gouvernance.seed import peupler


@pytest.fixture
def matrice(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    return charger_matrice(chemin)


def test_support_peut_appeler_ask_database_mais_pas_de_colonnes_sensibles(matrice):
    perimetre = Perimetre("support", matrice)
    assert perimetre.peut_appeler("ask_database") is True
    assert perimetre.tables_autorisees() == frozenset(
        {"produits", "stocks", "clients", "commandes", "ventes"}
    )
    assert perimetre.colonnes_interdites("produits") == frozenset({"prix_achat_ht", "marge_pct"})
    assert perimetre.colonnes_interdites("ventes") == frozenset({"marge_ht"})
    assert perimetre.colonnes_interdites("stocks") == frozenset()


def test_dev_ne_peut_pas_appeler_ask_database_ni_answer_question(matrice):
    perimetre = Perimetre("dev", matrice)
    assert perimetre.peut_appeler("ask_database") is False
    assert perimetre.peut_appeler("answer_question") is False
    assert perimetre.peut_appeler("search_docs") is True


def test_support_na_pas_les_notes_confidentielles(matrice):
    perimetre = Perimetre("support", matrice)
    assert "notes_confidentielles" not in perimetre.collections_autorisees()
    assert "notes_operationnelles" in perimetre.collections_autorisees()


def test_commercial_na_aucune_colonne_interdite(matrice):
    perimetre = Perimetre("commercial", matrice)
    assert perimetre.colonnes_interdites("produits") == frozenset()
    assert perimetre.colonnes_interdites("ventes") == frozenset()


def test_profil_inconnu_leve(matrice):
    with pytest.raises(ProfilInconnu):
        Perimetre("stagiaire", matrice)
