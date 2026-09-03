"""Les quatre tools SQL du chantier 2 : ask_database, get_schema, check_stock, order_status."""

import pytest

import sorabel_sql.tools as tools
from sorabel_sql.generation import QuestionSensible
from sorabel_sql.validation import ValidationEchouee


class _PerimetreFactice:
    def __init__(self, tables=None, colonnes_interdites=None):
        self._tables = frozenset(tables or {"produits", "stocks", "clients", "commandes", "ventes"})
        self._colonnes_interdites = colonnes_interdites or {}

    def tables_autorisees(self):
        return self._tables

    def colonnes_interdites(self, table):
        return frozenset(self._colonnes_interdites.get(table, ()))


def test_get_schema_renvoie_le_schema_du_perimetre(monkeypatch):
    monkeypatch.setattr(tools, "schema_commente", lambda p: "SCHEMA-FACTICE")
    resultat = tools.get_schema(_PerimetreFactice())
    assert resultat == {"statut": "ok", "schema": "SCHEMA-FACTICE"}


def test_ask_database_question_sensible_est_non_autorise_sans_generation(monkeypatch):
    def _generer_espion(question, perimetre):
        raise QuestionSensible(question)

    monkeypatch.setattr(tools, "generer", _generer_espion)
    resultat = tools.ask_database("quelle est la marge sur REF-1024 ?", _PerimetreFactice())
    assert resultat["statut"] == "non_autorise"
    assert resultat["sql"] is None


def test_ask_database_hors_schema_quand_generer_renvoie_none(monkeypatch):
    monkeypatch.setattr(tools, "generer", lambda question, perimetre: None)
    resultat = tools.ask_database("quel est le taux de satisfaction ?", _PerimetreFactice())
    assert resultat["statut"] == "hors_schema"
    assert resultat["sql"] is None


def test_ask_database_renvoie_le_sql_rejete_si_validation_echoue(monkeypatch):
    monkeypatch.setattr(tools, "generer", lambda question, perimetre: "DELETE FROM produits")

    def _valider_echec(sql, perimetre):
        raise ValidationEchouee("refuse_ecriture", "écriture détectée")

    monkeypatch.setattr(tools, "valider", _valider_echec)
    resultat = tools.ask_database("supprime les commandes de test", _PerimetreFactice())
    assert resultat["statut"] == "refuse_ecriture"
    assert resultat["sql"] == "DELETE FROM produits"


def test_ask_database_execute_et_renvoie_le_resultat(monkeypatch):
    monkeypatch.setattr(tools, "generer", lambda question, perimetre: "SELECT COUNT(*) FROM commandes")
    monkeypatch.setattr(tools, "valider", lambda sql, perimetre: sql)
    monkeypatch.setattr(
        tools, "executer",
        lambda sql, params=(): {"sql": sql, "colonnes": ["COUNT(*)"], "lignes": [[27]], "n_lignes": 1, "tronque": False},
    )
    resultat = tools.ask_database("combien de commandes ?", _PerimetreFactice())
    assert resultat["statut"] == "ok"
    assert resultat["lignes"] == [[27]]
    assert resultat["sql"] == "SELECT COUNT(*) FROM commandes"


def test_check_stock_ref_invalide_est_hors_schema():
    resultat = tools.check_stock("PAS-UNE-REF")
    assert resultat["statut"] == "hors_schema"


def test_check_stock_ref_valide_interroge_par_parametre_lie(monkeypatch):
    appels = []

    def _executer_espion(sql, params=()):
        appels.append((sql, params))
        return {
            "sql": sql, "colonnes": ["entrepot", "quantite", "seuil_reappro"],
            "lignes": [["LYON", 3, 10]], "n_lignes": 1, "tronque": False,
        }

    monkeypatch.setattr(tools, "executer", _executer_espion)
    resultat = tools.check_stock("REF-1024")

    assert resultat["statut"] == "ok"
    assert resultat["sous_seuil_reappro"] is True  # 3 < 10
    assert appels[0][1] == ("REF-1024",)  # paramètre lié, pas concaténé
    assert "REF-1024" not in appels[0][0]  # jamais dans le texte SQL


def test_order_status_id_invalide_est_hors_schema():
    resultat = tools.order_status("PAS-UN-ID")
    assert resultat["statut"] == "hors_schema"


def test_order_status_id_valide_interroge_par_parametre_lie(monkeypatch):
    appels = []

    def _executer_espion(sql, params=()):
        appels.append((sql, params))
        return {
            "sql": sql, "colonnes": ["statut", "date_commande", "montant_ht"],
            "lignes": [["livree", "2026-04-02", 450.0]], "n_lignes": 1, "tronque": False,
        }

    monkeypatch.setattr(tools, "executer", _executer_espion)
    resultat = tools.order_status("CMD-2025-0004")

    assert resultat["statut"] == "ok"
    assert resultat["lignes"] == [["livree", "2026-04-02", 450.0]]
    assert appels[0][1] == ("CMD-2025-0004",)
