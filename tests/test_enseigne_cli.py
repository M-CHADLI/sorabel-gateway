"""python -m sorabel_enseigne : le pont entre enseigne.toml et le Makefile."""

import subprocess
import sys
from pathlib import Path

import pytest

import sorabel_enseigne
from sorabel_enseigne.__main__ import main, variables_make

RACINE = Path(__file__).resolve().parent.parent


def test_variables_make_de_sorabel_reprennent_ses_chemins_relatifs():
    assert variables_make("sorabel") == (
        "GOUVERNANCE_DB := gouvernance/gouvernance.db\n"
        "MANIFESTE := data/canonique/_manifeste.json\n"
        "INDEX := data/chroma/bm25.pkl\n"
        "CORPUS_DIR := data/corpus\n"
        "JOURNAL := logs/appels.jsonl\n"
    )


def test_un_chemin_hors_du_depot_est_refuse(tmp_path, monkeypatch, ecrire_enseigne):
    monkeypatch.setattr(sorabel_enseigne, "DOSSIER_ENSEIGNES", tmp_path)
    sorabel_enseigne.enseigne.cache_clear()
    ecrire_enseigne(tmp_path, "dehors", (tmp_path / "donnees").as_posix())
    try:
        with pytest.raises(SystemExit, match="hors du dépôt"):
            variables_make("dehors")
    finally:
        sorabel_enseigne.enseigne.cache_clear()


def test_liste_affiche_les_enseignes_disponibles(capsys):
    assert main(["liste"]) == 0
    assert "sorabel" in capsys.readouterr().out.split()


def test_des_arguments_invalides_affichent_l_usage(capsys):
    assert main(["inconnu"]) == 2
    assert "usage" in capsys.readouterr().err


def test_la_sortie_make_est_en_fins_de_ligne_unix():
    """Sous Windows, stdout en mode texte écrirait \r\n : Make lirait alors des chemins
    terminés par \r, introuvables sur le disque."""
    sortie = subprocess.run(
        [sys.executable, "-m", "sorabel_enseigne", "make", "sorabel"],
        cwd=RACINE, capture_output=True, check=True,
    )
    assert b"\r" not in sortie.stdout
    assert sortie.stdout.startswith(b"GOUVERNANCE_DB := ")
