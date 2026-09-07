"""Peuplement de gouvernance.db : la matrice exacte de docs/conception.md (chantier MCP §2)."""

import sqlite3

from gouvernance.seed import peupler


def _compter(connexion, requete, params=()):
    return connexion.execute(requete, params).fetchone()[0]


def test_quatre_profils_huit_tools_cinq_collections(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    connexion = sqlite3.connect(chemin)
    try:
        assert _compter(connexion, "SELECT COUNT(*) FROM profils") == 4
        assert _compter(connexion, "SELECT COUNT(*) FROM tools") == 8
        assert _compter(connexion, "SELECT COUNT(*) FROM collections") == 5
    finally:
        connexion.close()


def test_dev_na_pas_answer_question_ni_ask_database(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    connexion = sqlite3.connect(chemin)
    try:
        tools_dev = {
            r[0] for r in connexion.execute("SELECT tool FROM profil_tool WHERE profil = 'dev'")
        }
        assert tools_dev == {"search_docs", "get_document", "list_sources", "get_schema"}
    finally:
        connexion.close()


def test_support_na_pas_notes_confidentielles(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    connexion = sqlite3.connect(chemin)
    try:
        collections_support = {
            r[0] for r in connexion.execute(
                "SELECT collection FROM profil_collection WHERE profil = 'support'"
            )
        }
        assert "notes_confidentielles" not in collections_support
        assert "notes_operationnelles" in collections_support

        collections_commercial = {
            r[0] for r in connexion.execute(
                "SELECT collection FROM profil_collection WHERE profil = 'commercial'"
            )
        }
        assert "notes_confidentielles" in collections_commercial
    finally:
        connexion.close()


def test_colonnes_sensibles_exclues_pour_support_et_dev(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    connexion = sqlite3.connect(chemin)
    try:
        for profil in ("support", "dev"):
            colonnes = {
                r[0] for r in connexion.execute(
                    "SELECT colonne FROM colonne_interdite WHERE profil = ? AND table_sql = 'produits'",
                    (profil,),
                )
            }
            assert colonnes == {"prix_achat_ht", "marge_pct"}

        colonnes_commercial = {
            r[0] for r in connexion.execute(
                "SELECT colonne FROM colonne_interdite WHERE profil = 'commercial'"
            )
        }
        assert colonnes_commercial == set()  # aucune exclusion pour commercial
    finally:
        connexion.close()


def test_peupler_est_idempotent(tmp_path):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    peupler(chemin)  # ne doit pas lever (contrainte PRIMARY KEY sur un rejeu)
    connexion = sqlite3.connect(chemin)
    try:
        assert _compter(connexion, "SELECT COUNT(*) FROM profils") == 4
    finally:
        connexion.close()
