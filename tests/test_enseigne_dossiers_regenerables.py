"""`make reset-donnees` efface en entier (rm -rf) les dossiers `canonique` et `chroma` de
l'enseigne, chemins lus dans son `.toml`. `charger_enseigne` refuse donc tout `.toml` où l'un
d'eux est la racine du dépôt, ou contient ce qui ne se régénère pas : corpus, base SQL,
gouvernance, journal. Le refus a lieu au chargement, donc avant que Make n'obtienne le
moindre chemin."""

import os
from pathlib import Path

import pytest

import sorabel_enseigne
from sorabel_enseigne import charger_enseigne, enseigne
from sorabel_enseigne.__main__ import variables_make

RACINE = Path(__file__).resolve().parent.parent
DONNEES = "enseignes/essai/data"


def _poser(chemin_toml: Path, **chemins: str) -> Path:
    """Réécrit des clés de `[chemins]` dans le gabarit de tests/conftest.py, qui préfixe tous
    les chemins par le même dossier de données."""
    lignes = chemin_toml.read_text(encoding="utf-8").splitlines()
    for cle, valeur in chemins.items():
        lignes = [f'{cle} = "{valeur}"' if ligne.startswith(f"{cle} = ") else ligne for ligne in lignes]
    chemin_toml.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return chemin_toml


def test_chroma_sur_data_effacerait_le_corpus(tmp_path, ecrire_enseigne):
    """Le cas relevé par la revue : les chemins de Sorabel, avec `chroma = "data"`."""
    chemin = _poser(ecrire_enseigne(tmp_path, "essai", "data"), chroma="data")
    with pytest.raises(ValueError, match=r"chemins\.chroma .*chemins\.corpus"):
        charger_enseigne(chemin)


@pytest.mark.parametrize("dossier", ["canonique", "chroma"])
@pytest.mark.parametrize(
    "valeur", [".", "", "..", RACINE.as_posix()], ids=["point", "vide", "parent", "absolu"]
)
def test_la_racine_du_depot_ou_un_de_ses_parents_est_refusee(tmp_path, ecrire_enseigne, dossier, valeur):
    chemin = _poser(ecrire_enseigne(tmp_path, "essai", DONNEES), **{dossier: valeur})
    with pytest.raises(ValueError, match=rf"chemins\.{dossier} .*racine du dépôt"):
        charger_enseigne(chemin)


@pytest.mark.parametrize("dossier", ["canonique", "chroma"])
@pytest.mark.parametrize("preserve", ["corpus", "base_sql", "gouvernance", "journal"])
@pytest.mark.parametrize("valeur", [f"{DONNEES}/precieux", f"{DONNEES}/precieux/x"], ids=["parent", "egal"])
def test_un_dossier_regenerable_ne_peut_etre_ni_contenir_un_chemin_preserve(
    tmp_path, ecrire_enseigne, dossier, preserve, valeur
):
    chemin = _poser(
        ecrire_enseigne(tmp_path, "essai", DONNEES), **{preserve: f"{DONNEES}/precieux/x", dossier: valeur}
    )
    with pytest.raises(ValueError, match=rf"chemins\.{dossier} .*chemins\.{preserve}"):
        charger_enseigne(chemin)


def test_un_detour_par_dossier_parent_ne_trompe_pas_la_verification(tmp_path, ecrire_enseigne):
    """`rm -rf data/corpus/../` efface `data/` : la comparaison porte sur le chemin normalisé."""
    chemin = _poser(ecrire_enseigne(tmp_path, "essai", DONNEES), canonique=f"{DONNEES}/corpus/..")
    with pytest.raises(ValueError, match=r"chemins\.canonique .*chemins\.corpus"):
        charger_enseigne(chemin)


@pytest.mark.skipif(os.name != "nt", reason="système de fichiers insensible à la casse")
def test_sous_windows_la_casse_ne_trompe_pas_la_verification(tmp_path, ecrire_enseigne):
    chemin = _poser(ecrire_enseigne(tmp_path, "essai", DONNEES), chroma=DONNEES.upper())
    with pytest.raises(ValueError, match=r"chemins\.chroma .*chemins\.corpus"):
        charger_enseigne(chemin)


@pytest.mark.parametrize("donnees", ["data", DONNEES, "absolu"])
def test_le_gabarit_des_tests_reste_valide(tmp_path, ecrire_enseigne, donnees):
    """Dossiers voisins du corpus, comme chez Sorabel (`data/canonique`, `data/corpus`)."""
    donnees = (tmp_path / "donnees").as_posix() if donnees == "absolu" else donnees
    essai = charger_enseigne(ecrire_enseigne(tmp_path, "essai", donnees))
    assert essai.chemins.chroma.name == "chroma"


def test_un_prefixe_commun_n_est_pas_un_dossier_parent(tmp_path, ecrire_enseigne):
    """`data/corp` n'est pas le parent de `data/corpus` : la comparaison porte sur les
    composants du chemin, pas sur les caractères."""
    chemin = _poser(ecrire_enseigne(tmp_path, "essai", DONNEES), chroma=f"{DONNEES}/corp")
    assert charger_enseigne(chemin).chemins.chroma == RACINE / DONNEES / "corp"


def test_les_enseignes_du_depot_sont_valides():
    assert enseigne("sorabel").chemins.chroma == RACINE / "data" / "chroma"
    assert enseigne("kiabi").chemins.chroma == RACINE / "enseignes" / "kiabi" / "data" / "chroma"


def test_make_n_obtient_aucun_chemin_d_un_toml_dangereux(tmp_path, monkeypatch, ecrire_enseigne):
    """Les variables de `make reset-donnees` viennent de `python -m sorabel_enseigne make` :
    le refus au chargement empêche Make de générer `.make/<enseigne>.mk`."""
    monkeypatch.setattr(sorabel_enseigne, "DOSSIER_ENSEIGNES", tmp_path)
    sorabel_enseigne.enseigne.cache_clear()
    _poser(ecrire_enseigne(tmp_path, "essai", "data"), chroma="data")
    try:
        with pytest.raises(ValueError, match=r"chemins\.chroma"):
            variables_make("essai")
    finally:
        sorabel_enseigne.enseigne.cache_clear()
