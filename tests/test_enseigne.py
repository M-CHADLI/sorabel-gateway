"""sorabel_enseigne : une enseigne par processus, jamais de repli silencieux."""

from pathlib import Path

import pytest

import sorabel_enseigne
from sorabel_enseigne import charger_enseigne, enseigne, enseigne_active, enseignes_disponibles

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def dossier_essai(tmp_path, monkeypatch):
    """`enseignes/` remplacé par un dossier temporaire. Le cache est vidé avant et après :
    sinon une enseigne d'essai survivrait au test dans `enseigne()`."""
    monkeypatch.setattr(sorabel_enseigne, "DOSSIER_ENSEIGNES", tmp_path)
    enseigne.cache_clear()
    yield tmp_path
    enseigne.cache_clear()


@pytest.fixture
def enseigne_non_figee(monkeypatch):
    """Remet à zéro le nom figé au premier appel d'`enseigne_active()` : les tests qui
    changent `SORABEL_ENSEIGNE` partent d'un processus vierge, et la valeur d'origine
    (celle de l'ensemble de la session de test) est restaurée ensuite."""
    monkeypatch.setattr(sorabel_enseigne, "_ENSEIGNE_FIGEE", None)


def test_sans_variable_l_enseigne_active_est_sorabel(monkeypatch):
    monkeypatch.delenv("SORABEL_ENSEIGNE", raising=False)
    assert enseigne_active().nom == "sorabel"


def test_variable_vide_retombe_sur_sorabel(monkeypatch):
    monkeypatch.setenv("SORABEL_ENSEIGNE", "")
    assert enseigne_active().nom == "sorabel"


def test_enseigne_inconnue_leve_une_erreur_qui_liste_les_disponibles(monkeypatch, enseigne_non_figee):
    monkeypatch.setenv("SORABEL_ENSEIGNE", "inexistante")
    with pytest.raises(ValueError, match=r"inexistante.*disponibles : .*sorabel"):
        enseigne_active()


def test_changer_de_variable_apres_le_premier_appel_leve_une_erreur(
    monkeypatch, dossier_essai, ecrire_enseigne, enseigne_non_figee
):
    ecrire_enseigne(dossier_essai, "alpha", "enseignes/alpha/data")
    ecrire_enseigne(dossier_essai, "beta", "enseignes/beta/data")
    monkeypatch.setenv("SORABEL_ENSEIGNE", "alpha")
    assert enseigne_active().nom == "alpha"
    monkeypatch.setenv("SORABEL_ENSEIGNE", "beta")
    with pytest.raises(ValueError, match=r"alpha.*beta|beta.*alpha"):
        enseigne_active()


def test_un_premier_appel_sur_une_enseigne_inconnue_ne_fige_rien(
    monkeypatch, dossier_essai, ecrire_enseigne, enseigne_non_figee
):
    ecrire_enseigne(dossier_essai, "alpha", "enseignes/alpha/data")
    monkeypatch.setenv("SORABEL_ENSEIGNE", "inconnue")
    with pytest.raises(ValueError, match="enseigne inconnue"):
        enseigne_active()
    monkeypatch.setenv("SORABEL_ENSEIGNE", "alpha")
    assert enseigne_active().nom == "alpha"


def test_sorabel_declare_les_chemins_historiques():
    sorabel = enseigne("sorabel")
    assert sorabel.chemins.corpus == RACINE / "data" / "corpus"
    assert sorabel.chemins.canonique == RACINE / "data" / "canonique"
    assert sorabel.chemins.chroma == RACINE / "data" / "chroma"
    assert sorabel.chemins.base_sql == RACINE / "data" / "sorabel.db"
    assert sorabel.chemins.gouvernance == RACINE / "gouvernance" / "gouvernance.db"
    assert sorabel.chemins.journal == RACINE / "logs" / "appels.jsonl"
    assert sorabel.collection == "sorabel_docs"


def test_une_seconde_enseigne_resout_ses_propres_chemins(tmp_path, ecrire_enseigne):
    essai = charger_enseigne(ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data"))
    assert essai.chemins.corpus == RACINE / "enseignes" / "essai" / "data" / "corpus"
    assert essai.chemins.base_sql == RACINE / "enseignes" / "essai" / "data" / "essai.db"
    assert essai.commentaires_sql["stocks.entrepot"] == "ENTREPOT-essai"
    assert enseigne("sorabel").chemins.corpus == RACINE / "data" / "corpus"


def test_un_chemin_absolu_est_conserve_tel_quel(tmp_path, ecrire_enseigne):
    essai = charger_enseigne(ecrire_enseigne(tmp_path, "essai", tmp_path.as_posix()))
    assert essai.chemins.corpus == tmp_path / "corpus"


def test_une_cle_manquante_est_signalee(tmp_path):
    chemin = tmp_path / "enseigne.toml"
    chemin.write_text('nom = "incomplete"\nlibelle = "Incomplète"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="clé manquante"):
        charger_enseigne(chemin)


def test_un_pied_de_page_vide_est_refuse(tmp_path, ecrire_enseigne):
    chemin = ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data")
    chemin.write_text(
        chemin.read_text(encoding="utf-8").replace('"Document essai"', '""'), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="pied_de_page"):
        charger_enseigne(chemin)


def test_meme_nom_meme_objet_noms_distincts_independants(dossier_essai, ecrire_enseigne):
    ecrire_enseigne(dossier_essai, "alpha", "enseignes/alpha/data")
    ecrire_enseigne(dossier_essai, "beta", "enseignes/beta/data")
    assert enseigne("alpha") is enseigne("alpha")
    assert enseigne("alpha").chemins.corpus != enseigne("beta").chemins.corpus
    assert enseigne("alpha").collection == "alpha_docs"
    assert enseigne("beta").collection == "beta_docs"


def test_un_nom_qui_contredit_son_dossier_est_refuse(dossier_essai, ecrire_enseigne):
    ecrire_enseigne(dossier_essai, "gamma", "enseignes/gamma/data", nom_declare="delta")
    with pytest.raises(ValueError, match="delta"):
        enseigne("gamma")


def test_enseignes_disponibles_contient_sorabel():
    assert "sorabel" in enseignes_disponibles()
