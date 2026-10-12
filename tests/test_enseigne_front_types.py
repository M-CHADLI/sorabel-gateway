"""sorabel_enseigne : `[front]` valide le TYPE et le FORMAT de chaque valeur au chargement.

Sans cette validation, une chaîne à la place d'une liste se découperait caractère par
caractère en boutons d'exemple, et une couleur mal formée finirait telle quelle dans la
feuille de style. Chaque erreur nomme la clé fautive.
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


def _charger(dossier, ecrire_enseigne, table: str):
    chemin = ecrire_enseigne(dossier, "alpha", "enseignes/alpha/data")
    chemin.write_text(
        chemin.read_text(encoding="utf-8") + "\n[front]\n" + table, encoding="utf-8"
    )
    return charger_enseigne(chemin)


@pytest.mark.parametrize(
    "table, cle",
    [
        ('couleur_accent = "bleu"\n', "couleur_accent"),
        ('couleur_accent = "#12345"\n', "couleur_accent"),
        ('couleur_fond = "#GGGGGG"\n', "couleur_fond"),
        ('couleur_fond = "0B2E6B"\n', "couleur_fond"),
        ('couleur_accent = "#1E5BC6; } body { display: none"\n', "couleur_accent"),
        ("couleur_accent = 2563\n", "couleur_accent"),
    ],
)
def test_couleur_hors_format_rrggbb(dossier_essai, ecrire_enseigne, table, cle):
    with pytest.raises(ValueError, match=cle):
        _charger(dossier_essai, ecrire_enseigne, table)


@pytest.mark.parametrize("cle", ["references_exemple", "questions_exemple"])
def test_chaine_a_la_place_d_une_liste(dossier_essai, ecrire_enseigne, cle):
    with pytest.raises(ValueError, match=cle):
        _charger(dossier_essai, ecrire_enseigne, f'{cle} = "REF-1024"\n')


@pytest.mark.parametrize("cle", ["references_exemple", "questions_exemple"])
def test_liste_vide(dossier_essai, ecrire_enseigne, cle):
    with pytest.raises(ValueError, match=cle):
        _charger(dossier_essai, ecrire_enseigne, f"{cle} = []\n")


@pytest.mark.parametrize("cle", ["references_exemple", "questions_exemple"])
def test_doublons(dossier_essai, ecrire_enseigne, cle):
    with pytest.raises(ValueError, match=cle):
        _charger(dossier_essai, ecrire_enseigne, f'{cle} = ["REF-1024", "REF-1024"]\n')


@pytest.mark.parametrize(
    "valeurs", ['["REF-1024", ""]', '["REF-1024", "  "]', '["REF-1024", 5]', "[1, 2]"]
)
def test_liste_contenant_autre_chose_que_des_chaines_non_vides(
    dossier_essai, ecrire_enseigne, valeurs
):
    with pytest.raises(ValueError, match="references_exemple"):
        _charger(dossier_essai, ecrire_enseigne, f"references_exemple = {valeurs}\n")


@pytest.mark.parametrize(
    "cle",
    [
        "titre_page",
        "nom_produit",
        "resume_corpus",
        "question_sql_exemple",
        "commande_exemple",
        "document_exemple",
    ],
)
def test_texte_vide_ou_non_chaine(dossier_essai, ecrire_enseigne, cle):
    with pytest.raises(ValueError, match=cle):
        _charger(dossier_essai, ecrire_enseigne, f'{cle} = ""\n')
    with pytest.raises(ValueError, match=cle):
        _charger(dossier_essai, ecrire_enseigne, f'{cle} = ["a"]\n')
    with pytest.raises(ValueError, match=cle):
        _charger(dossier_essai, ecrire_enseigne, f"{cle} = 12\n")


def test_la_mention_peut_etre_vide(dossier_essai, ecrire_enseigne):
    front = _charger(dossier_essai, ecrire_enseigne, 'mention = ""\n').front
    assert front["mention"] == ""


def test_la_mention_doit_rester_une_chaine(dossier_essai, ecrire_enseigne):
    with pytest.raises(ValueError, match="mention"):
        _charger(dossier_essai, ecrire_enseigne, "mention = 3\n")


def test_front_qui_n_est_pas_une_table(dossier_essai, ecrire_enseigne):
    chemin = ecrire_enseigne(dossier_essai, "alpha", "enseignes/alpha/data")
    brut = chemin.read_text(encoding="utf-8")
    # `front = "x"` doit précéder les tables : TOML refuse une clé racine après `[sql]`.
    chemin.write_text('front = "x"\n' + brut, encoding="utf-8")
    with pytest.raises(ValueError, match=r"\[front\]"):
        charger_enseigne(chemin)


def test_une_valeur_valide_passe_et_l_erreur_cite_le_fichier(dossier_essai, ecrire_enseigne):
    front = _charger(
        dossier_essai,
        ecrire_enseigne,
        'couleur_accent = "#1e5bc6"\nresume_corpus = "12 documents indexés"\n',
    ).front
    assert front["couleur_accent"] == "#1e5bc6"
    assert front["resume_corpus"] == "12 documents indexés"
    with pytest.raises(ValueError, match="enseigne.toml"):
        _charger(dossier_essai, ecrire_enseigne, 'couleur_fond = "x"\n')


def test_resume_corpus_est_une_cle_admise_et_kiabi_le_declare():
    assert "resume_corpus" in CLES_FRONT
    assert enseigne("kiabi").front["resume_corpus"] == "175 documents indexés"
    assert "resume_corpus" not in enseigne("sorabel").front
