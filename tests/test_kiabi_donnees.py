"""Données fictives Kiabi : cohérentes entre base et corpus, et lisibles par l'ingestion telle
quelle. Les fichiers testés sont ceux commités (enseignes/kiabi/data/), pas une régénération :
c'est ce que la démonstration indexe réellement."""

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "enseignes" / "kiabi" / "data"
CORPUS = DONNEES / "corpus"
MOTIF_REF = re.compile(r"REF-\d{4}")


@pytest.fixture(scope="module")
def base():
    connexion = sqlite3.connect(f"file:{(DONNEES / 'kiabi.db').as_posix()}?mode=ro", uri=True)
    yield connexion
    connexion.close()


def _texte(chemin: Path) -> str:
    if chemin.suffix == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(str(chemin)).pages)
    return chemin.read_text(encoding="utf-8")


def test_toute_reference_citee_par_le_corpus_existe_en_base(base):
    """`produits.ref` est le pivot entre les deux mondes : une référence orpheline ferait
    répondre la documentation sur un produit que la base ignore."""
    connues = {ref for (ref,) in base.execute("SELECT ref FROM produits")}
    citees = {ref for chemin in CORPUS.rglob("*.*") for ref in MOTIF_REF.findall(_texte(chemin))}
    assert citees and citees <= connues


def test_stocks_et_ventes_pointent_vers_des_produits_et_magasins_connus(base):
    assert base.execute(
        "SELECT COUNT(*) FROM stocks WHERE ref NOT IN (SELECT ref FROM produits)").fetchone() == (0,)
    assert base.execute(
        "SELECT COUNT(*) FROM ventes WHERE ref NOT IN (SELECT ref FROM produits)").fetchone() == (0,)
    assert base.execute(
        "SELECT COUNT(*) FROM ventes WHERE commande_id NOT IN (SELECT id FROM commandes)"
    ).fetchone() == (0,)
    assert base.execute(
        "SELECT COUNT(*) FROM commandes WHERE client_id NOT IN (SELECT id FROM clients)"
    ).fetchone() == (0,)


def test_identifiants_au_format_des_tools_figes(base):
    """check_stock et order_status valident REF-XXXX et CMD-AAAA-NNNN avant toute requête."""
    assert all(re.fullmatch(r"REF-\d{4}", r) for (r,) in base.execute("SELECT ref FROM produits"))
    assert all(re.fullmatch(r"CMD-\d{4}-\d{4}", c) for (c,) in base.execute("SELECT id FROM commandes"))
    assert base.execute("SELECT COUNT(*) FROM produits WHERE ref = 'REF-1024'").fetchone() == (1,)


def test_les_marges_sont_coherentes_avec_les_prix(base):
    assert base.execute(
        "SELECT COUNT(*) FROM produits WHERE prix_achat_ht >= prix_vente_ht").fetchone() == (0,)
    ecarts = base.execute(
        "SELECT MAX(ABS(v.marge_ht - (v.prix_unitaire_ht - p.prix_achat_ht) * v.quantite)) "
        "FROM ventes v JOIN produits p ON p.ref = v.ref").fetchone()[0]
    assert ecarts < 0.01


def test_le_corpus_contient_des_versions_multiples():
    """Le piège qui justifie le filtre sur la version courante doit exister chez Kiabi aussi."""
    def familles_versionnees(dossier: str, motif: str) -> int:
        familles: dict[str, int] = {}
        for chemin in (CORPUS / dossier).iterdir():
            cle = re.sub(motif, "", chemin.stem)
            familles[cle] = familles.get(cle, 0) + 1
        return sum(1 for n in familles.values() if n > 1)

    assert familles_versionnees("fiches", r"-v\d+\.\d+$") >= 10
    assert familles_versionnees("notices", r"-v\d+\.\d+$") >= 3
    assert familles_versionnees("sav", r"-v\d+\.\d+$") >= 3


def test_les_notes_de_politique_tarifaire_sont_a_diffusion_restreinte():
    notes = list((CORPUS / "notes").glob("note-*-politique-tarifaire-*.md"))
    assert notes and all("Diffusion restreinte" in n.read_text(encoding="utf-8") for n in notes)


def test_l_ingestion_reconnait_chaque_document_sous_l_enseigne_kiabi():
    """Interpréteur neuf : le pied de page filtré est celui de l'enseigne du processus."""
    script = """
import json
from pathlib import Path
from sorabel_rag.extraction import EXTRACTEURS
corpus = Path(__import__("sorabel_enseigne").enseigne_active().chemins.corpus)
statuts, pieds = {}, 0
for dossier, (extracteur, motif) in EXTRACTEURS.items():
    for chemin in sorted((corpus / dossier).glob(motif)):
        doc = extracteur(chemin)
        statuts[doc.qualite.statut] = statuts.get(doc.qualite.statut, 0) + 1
        pieds += any("Document Kiabi" in s.contenu for s in doc.sections)
print(json.dumps({"statuts": statuts, "pieds": pieds}))
"""
    sortie = subprocess.run(
        [sys.executable, "-c", script], cwd=RACINE, capture_output=True, text=True,
        encoding="utf-8", env={**__import__("os").environ, "SORABEL_ENSEIGNE": "kiabi"},
    )
    assert sortie.returncode == 0, sortie.stderr
    resultat = json.loads(sortie.stdout)
    assert resultat["statuts"] == {"ok": 175}
    assert resultat["pieds"] == 0
