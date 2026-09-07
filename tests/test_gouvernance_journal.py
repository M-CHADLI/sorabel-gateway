"""Journalisation (E4, E5) : une ligne JSON par appel, en ajout seul."""

import json

from gouvernance import journal


def test_journaliser_ecrit_une_ligne_json_valide(tmp_path, monkeypatch):
    chemin = tmp_path / "appels.jsonl"
    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", chemin)

    journal.journaliser(
        profil="support", tool="ask_database", autorise=False, statut="non_autorise",
        entrees={"question": "quelle est la marge sur REF-1024 ?"},
        sql=None, n_lignes=0, duree_ms=3.2, motif="produits.marge_pct hors périmètre",
        code="COLONNE_INTERDITE",
    )

    lignes = chemin.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 1
    ligne = json.loads(lignes[0])
    assert ligne["profil"] == "support"
    assert ligne["tool"] == "ask_database"
    assert ligne["autorise"] is False
    assert ligne["statut"] == "non_autorise"
    assert ligne["code"] == "COLONNE_INTERDITE"
    assert ligne["motif"] == "produits.marge_pct hors périmètre"
    assert "horodatage" in ligne


def test_journaliser_ajoute_sans_ecraser(tmp_path, monkeypatch):
    chemin = tmp_path / "appels.jsonl"
    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", chemin)

    journal.journaliser(profil="admin", tool="get_schema", autorise=True, statut="ok", entrees={})
    journal.journaliser(profil="admin", tool="get_schema", autorise=True, statut="ok", entrees={})

    lignes = chemin.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 2


def test_journaliser_cree_le_dossier_logs_sil_manque(tmp_path, monkeypatch):
    chemin = tmp_path / "sous_dossier_absent" / "appels.jsonl"
    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", chemin)

    journal.journaliser(profil="dev", tool="search_docs", autorise=True, statut="ok", entrees={})

    assert chemin.exists()


def test_journal_sur_stdout_quand_la_variable_le_demande(monkeypatch, capsys):
    """Cloud Logging indexe la sortie standard sans agent : en production, on n'écrit
    plus de fichier, qui serait de toute façon perdu au recyclage du conteneur."""
    monkeypatch.setenv("SORABEL_JOURNAL", "stdout")
    from gouvernance.journal import journaliser

    journaliser(
        profil="support",
        tool="ask_database",
        autorise=False,
        statut="non_autorise",
        entrees={"question": "quelles marges ?"},
        motif="tool hors perimetre",
    )
    ligne = json.loads(capsys.readouterr().out.strip())
    assert ligne["profil"] == "support"
    assert ligne["autorise"] is False
    assert ligne["statut"] == "non_autorise"


def test_journal_dans_un_fichier_par_defaut(monkeypatch, tmp_path):
    monkeypatch.delenv("SORABEL_JOURNAL", raising=False)
    import gouvernance.journal as journal

    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", tmp_path / "appels.jsonl")
    journal.journaliser(
        profil="commercial", tool="check_stock", autorise=True,
        statut="ok", entrees={"ref": "REF-8842"},
    )
    contenu = (tmp_path / "appels.jsonl").read_text(encoding="utf-8")
    assert json.loads(contenu.strip())["tool"] == "check_stock"
