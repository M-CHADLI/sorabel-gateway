"""Libellés des types de document : ils ouvrent l'en-tête de chaque chunk, que lisent
l'embedding, BM25, le reranker et le LLM — lequel les répète dans ses réponses. Un guide
d'entretien Kiabi ne doit pas s'y présenter comme une « Notice d'installation ».

tests/instantanes/sorabel/chunks_index_prompt.json a été capturé sur le code de f19e105,
AVANT que les libellés ne passent par l'enseigne : pour Sorabel, ni le texte indexé ni le
prompt ne changent d'un octet. S'il diverge, on corrige le code, jamais l'instantané.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import sorabel_enseigne
from sorabel_enseigne import charger_enseigne, enseigne
from sorabel_rag import modeles
from sorabel_rag.chunking import chunker
from sorabel_rag.extraction import (
    extraire_fiche,
    extraire_note,
    extraire_notice,
    extraire_procedure_sav,
)
from sorabel_rag.generation import _construire_prompt
from sorabel_rag.recherche import Resultat
from tests.test_enseigne_raccordement import PREAMBULE, _executer

RACINE = Path(__file__).resolve().parent.parent
CORPUS = RACINE / "data" / "corpus"
INSTANTANE = Path(__file__).resolve().parent / "instantanes" / "sorabel" / "chunks_index_prompt.json"


def test_texte_indexe_et_prompt_sorabel_inchanges():
    """Un document de chaque type ; la procédure SAV couvre aussi le titre qui répète déjà le
    libellé (« Procédure SAV — … »), que l'en-tête ne doit pas doubler."""
    documents = [
        extraire_fiche(CORPUS / "fiches" / "REF-1024-v2.1.pdf"),
        extraire_notice(CORPUS / "notices" / "notice-REF-1459-v1.1.pdf"),
        extraire_note(CORPUS / "notes" / "note-2024-01-11-alerte-qualite-50.md"),
        extraire_procedure_sav(CORPUS / "sav" / "proc-casse-transport-01-v2.0.html"),
    ]
    chunks = [chunk for document in documents for chunk in chunker(document, {})]
    # Ce que generation.py reçoit de la recherche : le texte brut stocké par Chroma et les
    # métadonnées du chunk, dont il reconstruit l'en-tête.
    resultats = [Resultat(c.chunk_id, c.texte_brut, 1.0, c.metadonnees) for c in chunks]
    attendu = json.loads(INSTANTANE.read_text(encoding="utf-8"))
    assert {c.chunk_id: c.texte for c in chunks} == attendu["index"]
    assert _construire_prompt("Question d'essai ?", resultats)[1]["content"] == attendu["prompt"]


def test_les_types_par_defaut_sont_ceux_du_moteur():
    """sorabel_enseigne n'importe pas sorabel_rag : il répète les codes de types, ce test
    les tient alignés."""
    assert set(sorabel_enseigne.LIBELLES_TYPES_PAR_DEFAUT) == {
        modeles.TYPE_FICHE, modeles.TYPE_NOTICE, modeles.TYPE_NOTE, modeles.TYPE_SAV,
    }


def _avec_libelles(chemin_toml: Path, lignes: str) -> Path:
    """Le gabarit de tests/conftest.py n'a pas de `[rag.libelles_types]` : on l'ajoute en fin
    de fichier — TOML admet une sous-table déclarée après d'autres tables."""
    chemin_toml.write_text(
        chemin_toml.read_text(encoding="utf-8") + f"\n[rag.libelles_types]\n{lignes}\n",
        encoding="utf-8",
    )
    return chemin_toml


def test_sans_table_les_libelles_sont_ceux_d_origine(tmp_path, ecrire_enseigne):
    essai = charger_enseigne(ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data"))
    assert dict(essai.libelles_types) == {
        "fiche_technique": "Fiche technique",
        "notice": "Notice d'installation",
        "note_interne": "Note interne",
        "procedure_sav": "Procédure SAV",
    }


def test_la_table_ne_change_que_les_types_qu_elle_nomme(tmp_path, ecrire_enseigne):
    chemin = _avec_libelles(
        ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data"), "notice = \"Guide d'essai\""
    )
    libelles = charger_enseigne(chemin).libelles_types
    assert libelles["notice"] == "Guide d'essai"
    assert libelles["fiche_technique"] == "Fiche technique"
    assert enseigne("sorabel").libelles_types["notice"] == "Notice d'installation"


def test_un_type_inconnu_est_refuse(tmp_path, ecrire_enseigne):
    """Une faute de frappe (« notices ») ignorée laisserait le libellé par défaut sans le
    moindre signal : c'est exactement le défaut que la table sert à corriger."""
    chemin = _avec_libelles(
        ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data"), 'notices = "Guide"'
    )
    with pytest.raises(ValueError, match="notices"):
        charger_enseigne(chemin)


@pytest.mark.parametrize("valeur", ['""', '"   "', "3"])
def test_un_libelle_vide_ou_non_textuel_est_refuse(tmp_path, ecrire_enseigne, valeur):
    chemin = _avec_libelles(
        ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data"), f"notice = {valeur}"
    )
    with pytest.raises(ValueError, match=r"libelles_types\.notice"):
        charger_enseigne(chemin)


@pytest.mark.parametrize("valeur", [
    '"Guide\\nd\'essai"',   # saut de ligne : l'en-tête tiendrait sur deux lignes
    '"Guide\\rd\'essai"',
    '"Guide] d\'essai"',    # crochet : l'en-tête serait refermé avant la référence
    '"[Guide]"',
])
def test_un_libelle_qui_casse_l_en_tete_est_refuse(tmp_path, ecrire_enseigne, valeur):
    """L'en-tête est `[libellé REF vX — titre]` : un libellé n'y met ni saut de ligne ni `]`."""
    chemin = _avec_libelles(
        ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data"), f"notice = {valeur}"
    )
    with pytest.raises(ValueError, match=r"libelles_types\.notice.*ni saut de ligne ni"):
        charger_enseigne(chemin)


def test_les_espaces_de_bordure_d_un_libelle_sont_retires(tmp_path, ecrire_enseigne):
    """Gardés, ils produiraient `[ Guide REF-0001 …]` dans l'en-tête, donc dans l'embedding."""
    chemin = _avec_libelles(
        ecrire_enseigne(tmp_path, "essai", "enseignes/essai/data"), 'notice = "  Guide d\'essai \\t"'
    )
    assert charger_enseigne(chemin).libelles_types["notice"] == "Guide d'essai"


def test_kiabi_nomme_ses_fiches_et_ses_guides():
    libelles = enseigne("kiabi").libelles_types
    assert libelles["fiche_technique"] == "Fiche produit"
    assert libelles["notice"] == "Guide d'entretien"
    # Les titres des procédures Kiabi commencent par « Procédure SAV — », comme chez Sorabel :
    # garder ce libellé, c'est garder l'en-tête sans répétition.
    assert libelles["procedure_sav"] == "Procédure SAV"
    assert libelles["note_interne"] == "Note interne"


SCRIPT_ENTETES = PREAMBULE + """
from sorabel_rag.chunking import texte_complet
meta = {"reference": "REF-0001", "version": "1.0", "titre": "Article d'essai"}
print(json.dumps({
    type_document: texte_complet({**meta, "type_document": type_document}, "corps")
    for type_document in ("fiche_technique", "notice", "note_interne", "procedure_sav")
}))
"""


def test_l_en_tete_des_chunks_suit_l_enseigne_active(tmp_path, ecrire_enseigne):
    """Interpréteur neuf : les libellés sont lus à l'import de sorabel_rag.chunking, et le
    processus de test l'a déjà importé avec l'enseigne sorabel."""
    _avec_libelles(
        ecrire_enseigne(tmp_path, "essai", (tmp_path / "donnees").as_posix()),
        "fiche_technique = \"Fiche article\"\nnotice = \"Guide d'entretien\"",
    )
    textes = _executer(SCRIPT_ENTETES, tmp_path)
    assert textes == {
        "fiche_technique": "[Fiche article REF-0001 v1.0 — Article d'essai]\ncorps",
        "notice": "[Guide d'entretien REF-0001 v1.0 — Article d'essai]\ncorps",
        "note_interne": "[Note interne REF-0001 v1.0 — Article d'essai]\ncorps",
        "procedure_sav": "[Procédure SAV REF-0001 v1.0 — Article d'essai]\ncorps",
    }


def test_un_guide_kiabi_s_indexe_comme_guide_d_entretien():
    """Le défaut observé en démonstration : le LLM répétait « Notice d'installation » à
    propos d'un guide d'entretien Kiabi. Chunk construit pour l'index, puis en-tête
    reconstruit pour le prompt, sur le vrai document."""
    script = """
import json
from pathlib import Path
from sorabel_enseigne import enseigne_active
from sorabel_rag.chunking import chunker, texte_complet
from sorabel_rag.extraction import extraire_notice
chemin = Path(enseigne_active().chemins.corpus) / "notices" / "notice-REF-1024-v2.0.pdf"
chunk = chunker(extraire_notice(chemin), {})[0]
print(json.dumps({"index": chunk.texte, "prompt": texte_complet(chunk.metadonnees, chunk.texte_brut)}))
"""
    sortie = subprocess.run(
        [sys.executable, "-c", script], cwd=RACINE, capture_output=True, text=True,
        encoding="utf-8", env={**os.environ, "SORABEL_ENSEIGNE": "kiabi"},
    )
    assert sortie.returncode == 0, sortie.stderr
    textes = json.loads(sortie.stdout)
    assert textes["index"].startswith("[Guide d'entretien REF-1024 v2.0 — Jean slim brut]\n")
    assert textes["prompt"] == textes["index"]
    assert "Notice d'installation" not in textes["index"]
