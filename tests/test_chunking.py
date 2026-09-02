"""Propagation des métadonnées de gouvernance (sous_type, diffusion_restreinte) dans les chunks."""

from sorabel_rag.chunking import chunker
from sorabel_rag.modeles import TYPE_NOTE, DocumentCanonique, Qualite, Section


def _note_de_test(sous_type: str, diffusion_restreinte: str) -> DocumentCanonique:
    return DocumentCanonique(
        doc_id="note_interne:note-test:v1.0",
        titre="Note de test",
        type_document=TYPE_NOTE,
        version="1.0",
        source_path="data/corpus/notes/note-test.md",
        hash_source="abc",
        hash_texte="def",
        extrait_le="2026-09-02T00:00:00+00:00",
        cle_groupe="note_interne:note-test",
        attributs={"sous_type": sous_type, "diffusion_restreinte": diffusion_restreinte},
        sections=[Section("", "Corps de la note de test, assez long pour ne pas alerter.")],
        qualite=Qualite(),
    )


def test_chunk_porte_le_sous_type_et_la_diffusion_restreinte():
    document = _note_de_test("politique_tarifaire", "true")
    manifeste = {
        "groupes": {
            document.cle_groupe: {
                "doc_id_courant": document.doc_id,
                "versions": [document.version],
            }
        }
    }
    chunks = chunker(document, manifeste)
    assert len(chunks) == 1
    assert chunks[0].metadonnees["sous_type"] == "politique_tarifaire"
    assert chunks[0].metadonnees["diffusion_restreinte"] is True


def test_chunk_diffusion_non_restreinte_est_bool_false():
    document = _note_de_test("logistique", "false")
    manifeste = {
        "groupes": {
            document.cle_groupe: {
                "doc_id_courant": document.doc_id,
                "versions": [document.version],
            }
        }
    }
    chunks = chunker(document, manifeste)
    assert chunks[0].metadonnees["diffusion_restreinte"] is False
    assert chunks[0].metadonnees["sous_type"] == "logistique"
