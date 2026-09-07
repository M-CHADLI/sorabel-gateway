"""Le dépôt d'identités : la seule donnée qui s'écrit en production.

Les tests utilisent SQLite ; Firestore est testé séparément par une doublure. Le contrat
est duck-typé, sur le patron de Perimetre : rien n'importe la classe concrète.
"""

import sqlite3
from pathlib import Path

import pytest

from gouvernance.identites import DepotIdentitesSqlite
from gouvernance.seed import peupler


@pytest.fixture
def depot(tmp_path: Path) -> DepotIdentitesSqlite:
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    return DepotIdentitesSqlite(chemin)


def test_sujet_inconnu_ne_donne_aucun_profil(depot):
    # Jamais de profil par défaut : un inconnu reste un inconnu.
    assert depot.profil_de("sub-jamais-vu") is None


def test_attribuer_puis_relire(depot):
    depot.attribuer("sub-123", "commercial", source="demo")
    assert depot.profil_de("sub-123") == "commercial"


def test_attribuer_deux_fois_remplace_le_profil(depot):
    # Le bouton « changer de profil » réécrit la ligne au lieu d'en empiler une seconde.
    depot.attribuer("sub-123", "commercial", source="demo")
    depot.attribuer("sub-123", "support", source="demo")
    assert depot.profil_de("sub-123") == "support"


def test_la_source_est_conservee(depot, tmp_path):
    depot.attribuer("sub-123", "admin", source="demo")
    connexion = sqlite3.connect(tmp_path / "gouvernance.db")
    try:
        source = connexion.execute(
            "SELECT source FROM identites WHERE sujet = ?", ("sub-123",)
        ).fetchone()[0]
    finally:
        connexion.close()
    assert source == "demo"


def test_profil_inexistant_est_refuse(depot):
    # La matrice est la référence : on n'attribue pas un profil qui n'existe pas.
    with pytest.raises(ValueError, match="profil inconnu"):
        depot.attribuer("sub-123", "directeur", source="demo")
