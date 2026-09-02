"""Régression : CORPUS doit pointer vers le corpus réel du dépôt."""

from sorabel_rag.ingestion import CORPUS


def test_corpus_pointe_vers_un_dossier_existant():
    assert CORPUS.is_dir(), f"CORPUS ({CORPUS}) n'existe pas"


def test_corpus_contient_les_quatre_sous_dossiers():
    sous_dossiers = {p.name for p in CORPUS.iterdir() if p.is_dir()}
    assert {"fiches", "notices", "notes", "sav"} <= sous_dossiers
