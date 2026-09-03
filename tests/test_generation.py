"""Génération de réponse RAG : refus déterministe (E1), citations construites en code,
et restriction par périmètre de gouvernance (Phase 4)."""

import sorabel_rag.generation as generation
from sorabel_rag.recherche import Resultat


def _resultat(score, doc_id="fiche_technique:REF-1024:v2.1", chunk_id=None, **meta_extra):
    meta = {
        "doc_id": doc_id,
        "titre": "Disjoncteur différentiel 30mA",
        "type_document": "fiche_technique",
        "reference": "REF-1024",
        "date": "2025-01-10",
        **meta_extra,
    }
    return Resultat(chunk_id or f"{doc_id}#0", "corps du chunk", score, meta)


def test_hors_corpus_sous_le_seuil_naspelle_pas_le_llm(monkeypatch):
    appele = False

    def _completer_espion(messages):
        nonlocal appele
        appele = True
        return "ne devrait jamais être retourné"

    monkeypatch.setattr(
        generation, "rechercher",
        lambda question, k, config, collections_autorisees=None: [_resultat(1e-6)],
    )
    monkeypatch.setattr(generation, "completer", _completer_espion)

    resultat = generation.repondre("capitale de l'Australie ?")

    assert resultat["statut"] == "hors_corpus"
    assert not appele


def test_hors_corpus_quand_aucun_resultat(monkeypatch):
    monkeypatch.setattr(
        generation, "rechercher",
        lambda question, k, config, collections_autorisees=None: [],
    )
    resultat = generation.repondre("question quelconque")
    assert resultat["statut"] == "hors_corpus"


def test_reponse_ok_construit_les_citations_depuis_les_metadonnees(monkeypatch):
    monkeypatch.setattr(
        generation, "rechercher",
        lambda question, k, config, collections_autorisees=None: [_resultat(0.9)],
    )
    monkeypatch.setattr(generation, "completer", lambda messages: "Le REF-1024 supporte 30mA.")

    resultat = generation.repondre("Quel est le seuil du REF-1024 ?")

    assert resultat["statut"] == "ok"
    assert resultat["reponse"] == "Le REF-1024 supporte 30mA."
    assert resultat["citations"] == [
        {"titre": "Disjoncteur différentiel 30mA", "reference": "REF-1024",
         "date": "2025-01-10", "type_document": "fiche_technique"}
    ]
    assert resultat["chunks_utilises"] == ["fiche_technique:REF-1024:v2.1#0"]


def test_citations_dedupliquees_par_document(monkeypatch):
    resultats = [
        _resultat(0.9, doc_id="procedure_sav:proc-casse-transport-01:v2.0", chunk_id="a#0",
                  titre="Procédure casse transport", type_document="procedure_sav",
                  reference="", date="2025-02-01"),
        _resultat(0.8, doc_id="procedure_sav:proc-casse-transport-01:v2.0", chunk_id="a#1",
                  titre="Procédure casse transport", type_document="procedure_sav",
                  reference="", date="2025-02-01"),
    ]
    monkeypatch.setattr(
        generation, "rechercher",
        lambda question, k, config, collections_autorisees=None: resultats,
    )
    monkeypatch.setattr(generation, "completer", lambda messages: "réponse")

    resultat = generation.repondre("comment déclarer une casse transport ?")

    assert len(resultat["citations"]) == 1
    assert resultat["citations"][0]["reference"] is None  # chaîne vide -> None
    assert resultat["chunks_utilises"] == ["a#0", "a#1"]


def test_perimetre_none_ne_restreint_pas_les_collections(monkeypatch):
    captures = {}

    def _rechercher_espion(question, k, config, collections_autorisees=None):
        captures["collections"] = collections_autorisees
        return [_resultat(0.9)]

    monkeypatch.setattr(generation, "rechercher", _rechercher_espion)
    monkeypatch.setattr(generation, "completer", lambda messages: "réponse")

    generation.repondre("question quelconque")

    assert captures["collections"] is None


class _PerimetreFactice:
    def collections_autorisees(self):
        return frozenset({"fiches", "notices"})


def test_perimetre_fourni_restreint_les_collections(monkeypatch):
    captures = {}

    def _rechercher_espion(question, k, config, collections_autorisees=None):
        captures["collections"] = collections_autorisees
        return [_resultat(0.9)]

    monkeypatch.setattr(generation, "rechercher", _rechercher_espion)
    monkeypatch.setattr(generation, "completer", lambda messages: "réponse")

    generation.repondre("question quelconque", perimetre=_PerimetreFactice())

    assert captures["collections"] == frozenset({"fiches", "notices"})
