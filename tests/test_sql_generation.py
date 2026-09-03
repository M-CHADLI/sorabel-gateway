"""Génération SQL : refus avant génération (E5), traduction, hors schéma."""

import pytest

import sorabel_sql.generation as generation


class _PerimetreFactice:
    def tables_autorisees(self):
        return frozenset({"produits", "stocks", "clients", "commandes", "ventes"})

    def colonnes_interdites(self, table):
        return frozenset()


def test_question_sensible_leve_avant_tout_appel_llm(monkeypatch):
    appele = False

    def _completer_espion(messages):
        nonlocal appele
        appele = True
        return "SELECT 1"

    monkeypatch.setattr(generation, "completer", _completer_espion)

    with pytest.raises(generation.QuestionSensible):
        generation.generer("quelle est la marge sur REF-1024 ?", _PerimetreFactice())

    assert not appele


def test_traduit_une_question_en_sql(monkeypatch):
    monkeypatch.setattr(
        generation, "completer",
        lambda messages: "SELECT COUNT(*) FROM commandes WHERE strftime('%m', date_commande) = '04';",
    )
    sql = generation.generer("combien de commandes en avril ?", _PerimetreFactice())
    assert sql == "SELECT COUNT(*) FROM commandes WHERE strftime('%m', date_commande) = '04'"


def test_hors_schema_renvoie_none(monkeypatch):
    monkeypatch.setattr(generation, "completer", lambda messages: "AUCUNE_REQUETE")
    assert generation.generer("quel est le taux de satisfaction client ?", _PerimetreFactice()) is None


def test_le_prompt_contient_le_schema_filtre(monkeypatch):
    messages_captures = {}

    def _completer_espion(messages):
        messages_captures["valeur"] = messages
        return "SELECT 1"

    monkeypatch.setattr(generation, "completer", _completer_espion)
    generation.generer("combien de produits ?", _PerimetreFactice())

    contenu_systeme = messages_captures["valeur"][0]["content"]
    assert "CREATE TABLE produits" in contenu_systeme
    assert "SELECT" in contenu_systeme  # règles de sortie présentes
