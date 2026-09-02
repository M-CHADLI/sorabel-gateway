"""Tests de l'extracteur de notes : sous_type et diffusion_restreinte (gouvernance E5)."""

from pathlib import Path

from sorabel_rag.extraction import extraire_note

CORPUS_NOTES = Path(__file__).resolve().parent.parent / "data" / "corpus" / "notes"


def test_note_politique_tarifaire_est_sous_type_et_diffusion_restreinte():
    doc = extraire_note(CORPUS_NOTES / "note-2024-03-03-politique-tarifaire-21.md")
    assert doc.attributs["sous_type"] == "politique_tarifaire"
    assert doc.attributs["diffusion_restreinte"] == "true"


def test_note_reunion_achat_est_sous_type_sans_diffusion_restreinte():
    doc = extraire_note(CORPUS_NOTES / "note-2024-01-02-reunion-achat-32.md")
    assert doc.attributs["sous_type"] == "reunion_achat"
    assert doc.attributs["diffusion_restreinte"] == "false"


def test_note_logistique_est_sous_type_operationnel():
    doc = extraire_note(CORPUS_NOTES / "note-2024-06-05-logistique-08.md")
    assert doc.attributs["sous_type"] == "logistique"
    assert doc.attributs["diffusion_restreinte"] == "false"


def test_note_alerte_qualite_est_sous_type_operationnel():
    doc = extraire_note(CORPUS_NOTES / "note-2024-01-11-alerte-qualite-50.md")
    assert doc.attributs["sous_type"] == "alerte_qualite"


def test_note_retour_terrain_est_sous_type_operationnel():
    doc = extraire_note(CORPUS_NOTES / "note-2024-03-28-retour-terrain-24.md")
    assert doc.attributs["sous_type"] == "retour_terrain"


def test_nom_de_fichier_non_reconnu_ne_bloque_pas_lextraction(tmp_path):
    chemin = tmp_path / "note-sans-motif-connu.md"
    chemin.write_text(
        "---\ntitre: Test\ndate: 2024-01-01\ntype: note_interne\nversion: '1.0'\n---\n\nCorps.",
        encoding="utf-8",
    )
    doc = extraire_note(chemin)
    assert doc.attributs["sous_type"] == ""
    assert doc.attributs["diffusion_restreinte"] == "false"
    assert "sous_type_absent" in doc.qualite.alertes
    assert doc.qualite.indexable  # non bloquant
