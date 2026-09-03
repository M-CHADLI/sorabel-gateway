"""Traduction des collections de gouvernance en filtre Chroma (E5 appliquée au RAG)."""

from sorabel_rag.recherche import filtre_collections


def test_aucune_restriction_si_none():
    assert filtre_collections(None) is None


def test_une_seule_collection_simple():
    assert filtre_collections(frozenset({"fiches"})) == {"type_document": "fiche_technique"}


def test_notes_operationnelles_filtre_sur_sous_type():
    filtre = filtre_collections(frozenset({"notes_operationnelles"}))
    assert filtre == {
        "$and": [
            {"type_document": "note_interne"},
            {"sous_type": {"$in": ["alerte_qualite", "logistique", "retour_terrain"]}},
        ]
    }


def test_notes_confidentielles_filtre_sur_sous_type():
    filtre = filtre_collections(frozenset({"notes_confidentielles"}))
    assert filtre == {
        "$and": [
            {"type_document": "note_interne"},
            {"sous_type": {"$in": ["politique_tarifaire", "reunion_achat"]}},
        ]
    }


def test_plusieurs_collections_sont_combinees_en_or():
    filtre = filtre_collections(frozenset({"fiches", "notices"}))
    assert "$or" in filtre
    assert {"type_document": "fiche_technique"} in filtre["$or"]
    assert {"type_document": "notice"} in filtre["$or"]


def test_aucune_collection_autorisee_ne_matche_jamais():
    filtre = filtre_collections(frozenset())
    assert filtre == {"type_document": "__aucune_collection_autorisee__"}
