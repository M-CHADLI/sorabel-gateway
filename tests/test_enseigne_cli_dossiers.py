"""`python -m sorabel_enseigne make` : les dossiers que `make reset-donnees` supprime.

`charger_enseigne` valide par liste noire (ce qui est, ou contient, un chemin de l'enseigne) :
`canonique = ".git"` la traverse. Le CLI, seul producteur des variables que `rm -rf` consomme,
exige donc une liste blanche : `data/<…>` ou `enseignes/<nom>/data/<…>`.
"""

from dataclasses import fields

import pytest

import sorabel_enseigne
from sorabel_enseigne import RACINE, Chemins
from sorabel_enseigne.__main__ import _verifier_cibles_de_reset, variables_make
from tests.conftest import GABARIT_ENSEIGNE


def _enseigne_avec(tmp_path, monkeypatch, *, canonique="data/canonique", chroma="data/chroma",
                   gouvernance="gouvernance/gouvernance.db"):
    """Écrit une enseigne `essai` dont les chemins régénérables sont ceux demandés, en
    gardant les autres hors d'atteinte (sous enseignes/essai/data)."""
    texte = GABARIT_ENSEIGNE.format(nom="essai", nom_declare="essai", donnees="enseignes/essai/data")
    texte = texte.replace('canonique = "enseignes/essai/data/canonique"', f'canonique = "{canonique}"')
    texte = texte.replace('chroma = "enseignes/essai/data/chroma"', f'chroma = "{chroma}"')
    texte = texte.replace(
        'gouvernance = "enseignes/essai/data/gouvernance.db"', f'gouvernance = "{gouvernance}"'
    )
    dossier = tmp_path / "essai"
    dossier.mkdir()
    (dossier / "enseigne.toml").write_text(texte, encoding="utf-8")
    monkeypatch.setattr(sorabel_enseigne, "DOSSIER_ENSEIGNES", tmp_path)
    sorabel_enseigne.enseigne.cache_clear()


@pytest.fixture(autouse=True)
def _cache_propre():
    yield
    sorabel_enseigne.enseigne.cache_clear()


def _chemins(**remplacements):
    """Des Chemins sains (sous enseignes/essai/data), dont on remplace quelques champs."""
    base = {
        champ.name: RACINE / "enseignes" / "essai" / "data" / champ.name
        for champ in fields(Chemins)
    }
    base.update({cle: RACINE / valeur for cle, valeur in remplacements.items()})
    return Chemins(**base)


@pytest.mark.parametrize("dossier", [
    ".git",
    "sorabel_rag",
    "enseignes",
    "enseignes/kiabi",
    "enseignes/kiabi/data",
    "data",
    "data/../../data/canonique",
    "../../data/canonique",
    "../voisin",
])
@pytest.mark.parametrize("cle", ["canonique", "chroma"])
def test_un_dossier_regenerable_hors_liste_blanche_est_refuse(cle, dossier):
    """Appel direct : `charger_enseigne` en refuserait déjà certains (ceux qui contiennent un
    autre chemin), mais pas `.git` ni `sorabel_rag`, et c'est le CLI qui doit tenir seul."""
    with pytest.raises(SystemExit):
        _verifier_cibles_de_reset(_chemins(**{cle: dossier}))


@pytest.mark.parametrize("dossier", [".git", "sorabel_rag", "../voisin"])
@pytest.mark.parametrize("cle", ["canonique", "chroma"])
def test_variables_make_refuse_un_dossier_regenerable_hors_liste_blanche(
    tmp_path, monkeypatch, cle, dossier
):
    """De bout en bout : ces trois-là traversent `charger_enseigne`."""
    _enseigne_avec(tmp_path, monkeypatch, **{cle: dossier})
    with pytest.raises(SystemExit):
        variables_make("essai")


def test_un_dossier_regenerable_absolu_hors_du_depot_est_refuse(tmp_path, monkeypatch):
    _enseigne_avec(tmp_path, monkeypatch, canonique=(tmp_path / "donnees").as_posix())
    with pytest.raises(SystemExit, match="hors du dépôt"):
        variables_make("essai")


def test_un_chemin_avec_des_remontees_ne_sort_pas_du_depot_sans_etre_vu(tmp_path, monkeypatch):
    """`relative_to` seul accepte `data/../../voisin` : le chemin « est dans » le dépôt."""
    _enseigne_avec(tmp_path, monkeypatch, canonique="data/../../voisin/canonique")
    with pytest.raises(SystemExit, match="hors du dépôt"):
        variables_make("essai")


def test_un_dossier_regenerable_sous_le_corpus_est_refuse(tmp_path, monkeypatch):
    """Sous data/, donc dans la liste blanche, mais c'est le corpus : `rm -rf` le mutilerait."""
    _enseigne_avec(tmp_path, monkeypatch, chroma="enseignes/essai/data/corpus/fiches")
    with pytest.raises(SystemExit, match="corpus"):
        variables_make("essai")


@pytest.mark.parametrize("gouvernance", ["data", "enseignes/essai/data", "enseignes/essai/data/corpus"])
def test_une_gouvernance_qui_contient_des_donnees_est_refusee(tmp_path, monkeypatch, gouvernance):
    _enseigne_avec(tmp_path, monkeypatch, gouvernance=gouvernance)
    with pytest.raises(SystemExit, match="gouvernance"):
        variables_make("essai")


@pytest.mark.parametrize("canonique, chroma", [
    ("data/canonique", "data/chroma"),
    ("enseignes/kiabi/data/canonique", "enseignes/kiabi/data/chroma"),
    ("enseignes/essai/data/canonique", "enseignes/essai/data/chroma"),
    ("data/essai/canonique", "enseignes/kiabi/data/chroma"),
])
def test_les_dossiers_regenerables_attendus_passent(tmp_path, monkeypatch, canonique, chroma):
    _enseigne_avec(tmp_path, monkeypatch, canonique=canonique, chroma=chroma)
    sortie = variables_make("essai")
    assert f"MANIFESTE := {canonique}/_manifeste.json\n" in sortie
    assert f"INDEX := {chroma}/bm25.pkl\n" in sortie


@pytest.mark.parametrize("nom", ["sorabel", "kiabi"])
def test_les_enseignes_livrees_passent(nom):
    assert "MANIFESTE := " in variables_make(nom)
