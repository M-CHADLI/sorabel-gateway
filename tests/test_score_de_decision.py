"""Score que lit le seuil de refus : la meilleure note brute pour une enseigne qui a calibré
son seuil (Kiabi), le premier résultat — lecture historique — pour les autres (Sorabel)."""

import pytest

from sorabel_rag import generation
from sorabel_rag.recherche import Resultat


def _resultats(*scores):
    return [Resultat(f"c{i}", "texte", s, {}, {}) for i, s in enumerate(scores)]


def test_sorabel_lit_le_premier_resultat(monkeypatch):
    monkeypatch.setattr(generation, "SEUIL_SUR_MEILLEURE_NOTE", False)
    # Le document à référence citée (0,5) est en tête malgré une note plus basse.
    assert generation.score_de_decision(_resultats(0.5, 1.0, 0.0)) == 0.5


def test_une_enseigne_a_seuil_propre_lit_la_meilleure_note(monkeypatch):
    monkeypatch.setattr(generation, "SEUIL_SUR_MEILLEURE_NOTE", True)
    assert generation.score_de_decision(_resultats(0.5, 1.0, 0.0)) == 1.0


def test_question_mixte_reference_et_langage_naturel_n_est_plus_refusee(monkeypatch):
    monkeypatch.setattr(generation, "SEUIL_SUR_MEILLEURE_NOTE", True)
    monkeypatch.setattr(generation, "SEUIL_REFUS_ENSEIGNE", 0.75)
    monkeypatch.setattr(generation, "rechercher", lambda *a, **k: _resultats(0.5, 1.0))
    monkeypatch.setattr(generation, "completer", lambda messages: "réponse")
    monkeypatch.setattr(generation, "_construire_prompt", lambda q, r: [])
    monkeypatch.setattr(generation, "_construire_citations", lambda r: [])
    assert generation.repondre("Le jean REF-1024 a rétréci, que faire ?")["statut"] == "ok"


def test_hors_corpus_reste_refuse_a_seuil_propre(monkeypatch):
    monkeypatch.setattr(generation, "SEUIL_SUR_MEILLEURE_NOTE", True)
    monkeypatch.setattr(generation, "SEUIL_REFUS_ENSEIGNE", 0.75)
    monkeypatch.setattr(generation, "rechercher", lambda *a, **k: _resultats(0.5, 0.0, 0.0))
    assert generation.repondre("capitale de l'Australie ?")["statut"] == "hors_corpus"


def test_sorabel_declare_aucun_seuil_propre():
    import sorabel_enseigne

    assert sorabel_enseigne.enseigne("sorabel").seuil_refus is None
    assert sorabel_enseigne.enseigne("kiabi").seuil_refus == pytest.approx(0.75)
