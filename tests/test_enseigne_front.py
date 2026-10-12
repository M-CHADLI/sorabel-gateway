"""sorabel_enseigne : la table `[front]`, textes et couleurs que le front applique par enseigne.

Sorabel n'en déclare pas : le front retombe sur ses défauts, qui sont ses textes actuels — la
production reste identique. Une clé mal orthographiée doit échouer au chargement plutôt que
de laisser le front afficher silencieusement le défaut Sorabel sur une démonstration.
"""

import pytest

import sorabel_enseigne
from sorabel_enseigne import CLES_FRONT, charger_enseigne, enseigne


@pytest.fixture
def dossier_essai(tmp_path, monkeypatch):
    monkeypatch.setattr(sorabel_enseigne, "DOSSIER_ENSEIGNES", tmp_path)
    enseigne.cache_clear()
    yield tmp_path
    enseigne.cache_clear()


def _ajouter_front(chemin, table: str):
    chemin.write_text(chemin.read_text(encoding="utf-8") + "\n[front]\n" + table, encoding="utf-8")


def test_sorabel_n_a_aucune_personnalisation_de_front():
    assert dict(enseigne("sorabel").front) == {}


def test_kiabi_declare_ses_textes_et_couleurs():
    front = enseigne("kiabi").front
    assert front["titre_page"] == "Kiabi — Poste magasin (démonstration)"
    assert front["nom_produit"] == "Kiabi Data Gateway"
    assert "fictives" in front["mention"]
    assert front["couleur_accent"] == "#1E5BC6"
    assert front["couleur_fond"] == "#0B2E6B"
    assert front["references_exemple"] == ("REF-1024", "REF-1141", "REF-1505", "REF-2422")
    assert front["questions_exemple"] == (
        "À quelle température laver le jean slim brut REF-1024 ?",
        "Quelle est la procédure pour un échange de taille ?",
        "Que faire pour un article décoloré au lavage ?",
    )
    assert front["question_sql_exemple"] == "Combien de réassorts en avril ?"
    assert front["commande_exemple"] == "CMD-2025-0002"
    assert front["document_exemple"] == "fiche_technique:REF-1024:v2.1"


def test_kiabi_ne_declare_que_des_cles_reconnues():
    assert set(enseigne("kiabi").front) <= set(CLES_FRONT)


def test_sans_table_front_le_mapping_est_vide(dossier_essai, ecrire_enseigne):
    chemin = ecrire_enseigne(dossier_essai, "alpha", "enseignes/alpha/data")
    assert dict(charger_enseigne(chemin).front) == {}


def test_les_listes_deviennent_des_tuples(dossier_essai, ecrire_enseigne):
    chemin = ecrire_enseigne(dossier_essai, "alpha", "enseignes/alpha/data")
    _ajouter_front(chemin, 'references_exemple = ["REF-1", "REF-2"]\ntitre_page = "Alpha"\n')
    front = charger_enseigne(chemin).front
    assert front["references_exemple"] == ("REF-1", "REF-2")
    assert front["titre_page"] == "Alpha"


def test_une_cle_inconnue_leve_une_erreur_qui_la_nomme(dossier_essai, ecrire_enseigne):
    chemin = ecrire_enseigne(dossier_essai, "alpha", "enseignes/alpha/data")
    _ajouter_front(chemin, 'couleur_acent = "#000000"\n')
    with pytest.raises(ValueError, match="couleur_acent"):
        charger_enseigne(chemin)


def test_le_front_est_immuable():
    front = enseigne("kiabi").front
    with pytest.raises(TypeError):
        front["titre_page"] = "Autre"
    with pytest.raises(TypeError):
        enseigne("sorabel").front["titre_page"] = "Autre"
