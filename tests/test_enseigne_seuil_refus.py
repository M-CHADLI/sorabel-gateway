"""Seuil de refus hors corpus (E1) par enseigne : `seuil_refus` dans la section [rag].

Un seuil se calibre sur un corpus. Sorabel garde le sien à l'identique (instantané capturé
sur le code d'avant cette option) ; Kiabi déclare celui mesuré dans docs/calibrage-kiabi.md.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import sorabel_rag.generation as generation
from sorabel_enseigne import charger_enseigne, enseigne
from sorabel_rag.recherche import SEUIL_REFUS, Resultat

RACINE = Path(__file__).resolve().parent.parent
INSTANTANES = Path(__file__).resolve().parent / "instantanes" / "sorabel"

# Notes du barème du reranker (PROMPT_RERANK, sorabel_rag/recherche.py).
SUJET_PROCHE = 0.5
REPOND_DIRECTEMENT = 1.0


def _gabarit_avec(chemin: Path, ligne: str) -> Path:
    """Ajoute `ligne` en fin de section [rag] du gabarit de tests/conftest.py."""
    texte = chemin.read_text(encoding="utf-8")
    chemin.write_text(texte.replace("[extraction]", f"{ligne}\n\n[extraction]"), encoding="utf-8")
    return chemin


def _resultat(note: float) -> Resultat:
    meta = {"doc_id": "fiche_technique:REF-1024:v2.1", "titre": "Jean slim brut",
            "type_document": "fiche_technique", "reference": "REF-1024", "date": "2025-11-23"}
    return Resultat("fiche_technique:REF-1024:v2.1#0", "corps du chunk", note, meta)


def test_sorabel_garde_le_seuil_d_origine():
    seuil_d_origine = float((INSTANTANES / "seuil_refus.txt").read_text(encoding="utf-8"))
    assert enseigne("sorabel").seuil_refus is None
    assert generation.SEUIL_REFUS_ENSEIGNE == SEUIL_REFUS == seuil_d_origine


def test_sans_cle_une_enseigne_garde_le_seuil_du_moteur(tmp_path, ecrire_enseigne):
    essai = charger_enseigne(ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data"))
    assert essai.seuil_refus is None
    assert generation.seuil_refus_de(essai) == SEUIL_REFUS


@pytest.mark.parametrize("valeur, attendu", [("0.75", 0.75), ("1", 1.0)])
def test_le_seuil_declare_remplace_celui_du_moteur(tmp_path, ecrire_enseigne, valeur, attendu):
    chemin = ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data")
    essai = charger_enseigne(_gabarit_avec(chemin, f"seuil_refus = {valeur}"))
    assert essai.seuil_refus == attendu
    assert isinstance(essai.seuil_refus, float)
    assert generation.seuil_refus_de(essai) == attendu


@pytest.mark.parametrize("valeur", ["0", "0.0", "-0.2", "1.5", "true", '"0.75"'])
def test_un_seuil_invalide_est_refuse_au_chargement(tmp_path, ecrire_enseigne, valeur):
    chemin = ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data")
    with pytest.raises(ValueError, match=r"rag\.seuil_refus"):
        charger_enseigne(_gabarit_avec(chemin, f"seuil_refus = {valeur}"))


def test_kiabi_refuse_la_note_sujet_proche():
    """La décision de docs/calibrage-kiabi.md : sur ce corpus, le reranker donne 0.5 à des
    questions hors corpus, jamais au meilleur document d'une question couverte."""
    assert SUJET_PROCHE < generation.seuil_refus_de(enseigne("kiabi")) <= REPOND_DIRECTEMENT


@pytest.mark.parametrize("note, statut", [(SUJET_PROCHE, "hors_corpus"), (REPOND_DIRECTEMENT, "ok")])
def test_repondre_applique_le_seuil_de_l_enseigne(monkeypatch, note, statut):
    appels_llm = []
    monkeypatch.setattr(generation, "SEUIL_REFUS_ENSEIGNE", 0.75)
    monkeypatch.setattr(
        generation, "rechercher",
        lambda question, k, config, collections_autorisees=None: [_resultat(note)],
    )
    monkeypatch.setattr(generation, "completer", lambda messages: appels_llm.append(messages) or "réponse")

    resultat = generation.repondre("vendez-vous des robes de mariée ?")

    assert resultat["statut"] == statut
    # Sous le seuil, le refus est déterministe : aucun appel LLM.
    assert len(appels_llm) == (1 if statut == "ok" else 0)


def test_un_processus_kiabi_applique_le_seuil_de_kiabi():
    """Le seuil est figé à l'import : vérifié dans un interpréteur neuf, le processus de test
    ayant déjà importé generation avec l'enseigne sorabel (tests/conftest.py)."""
    sortie = subprocess.run(
        [sys.executable, "-c", "from sorabel_rag import generation; print(generation.SEUIL_REFUS_ENSEIGNE)"],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "SORABEL_ENSEIGNE": "kiabi", "PYTHONIOENCODING": "utf-8"},
    )
    assert sortie.returncode == 0, sortie.stderr
    assert float(sortie.stdout) == enseigne("kiabi").seuil_refus
