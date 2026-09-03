"""Validation Pydantic de la matrice d'accès : E5 est un invariant bloquant, pas une donnée."""

import pytest
from pydantic import ValidationError

from gouvernance.modeles import DroitsProfil, charger_matrice
from gouvernance.seed import peupler


def test_e5_leve_si_colonne_sensible_non_exclue_pour_support():
    with pytest.raises(ValidationError):
        DroitsProfil(
            code="support",
            tools=frozenset({"get_schema"}),
            collections=frozenset(),
            tables=frozenset({"produits"}),
            colonnes_interdites={},  # manque prix_achat_ht et marge_pct
        )


def test_e5_leve_si_exclusion_partielle():
    with pytest.raises(ValidationError):
        DroitsProfil(
            code="dev",
            tools=frozenset(),
            collections=frozenset(),
            tables=frozenset({"produits"}),
            colonnes_interdites={"produits": frozenset({"prix_achat_ht"})},  # marge_pct manque
        )


def test_e5_nexige_rien_pour_commercial_ni_admin():
    for profil in ("commercial", "admin"):
        droits = DroitsProfil(
            code=profil,
            tools=frozenset({"ask_database"}),
            collections=frozenset(),
            tables=frozenset({"produits", "ventes"}),
            colonnes_interdites={},
        )
        assert droits.colonnes_interdites == {}


def test_droits_profil_valide_passe():
    droits = DroitsProfil(
        code="support",
        tools=frozenset({"get_schema", "ask_database"}),
        collections=frozenset({"fiches"}),
        tables=frozenset({"produits"}),
        colonnes_interdites={"produits": frozenset({"prix_achat_ht", "marge_pct"})},
    )
    assert droits.tables == frozenset({"produits"})


def test_code_tool_inconnu_est_rejete():
    with pytest.raises(ValidationError):
        DroitsProfil(
            code="admin",
            tools=frozenset({"answer_questionn"}),  # faute de frappe
            collections=frozenset(),
            tables=frozenset(),
            colonnes_interdites={},
        )


def test_charger_matrice_depuis_gouvernance_db(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)

    matrice = charger_matrice(chemin)

    assert set(matrice.profils) == {"support", "commercial", "dev", "admin"}
    support = matrice.profils["support"]
    assert "ask_database" in support.tools
    assert "notes_confidentielles" not in support.collections
    assert support.colonnes_interdites["produits"] == frozenset({"prix_achat_ht", "marge_pct"})

    dev = matrice.profils["dev"]
    assert "ask_database" not in dev.tools
    assert "answer_question" not in dev.tools
