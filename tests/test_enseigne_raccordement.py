"""Chaque module du moteur lit son enseigne dans sorabel_enseigne, et nulle part ailleurs.

Vérifié dans un interpréteur neuf : les constantes sont évaluées à l'import, et le
processus de test a déjà importé ces modules avec l'enseigne sorabel (tests/conftest.py).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Remplace `enseignes/` par le dossier temporaire AVANT tout import du moteur.
PREAMBULE = """
import json, os, sys
from pathlib import Path
import sorabel_enseigne
sorabel_enseigne.DOSSIER_ENSEIGNES = Path(sys.argv[1])
os.environ["SORABEL_ENSEIGNE"] = "essai"
"""

SCRIPT_CHEMINS = PREAMBULE + """
from front import depot
from gouvernance import journal
from mcp_server import serveur
from sorabel_rag import index, ingestion
from sorabel_sql import execution
print(json.dumps({
    "corpus": str(ingestion.CORPUS),
    "canonique": str(ingestion.SORTIE),
    "chroma": str(index.DOSSIER_CHROMA),
    "bm25": str(index.CHEMIN_BM25),
    "collection": index.NOM_COLLECTION,
    "base_sql": str(execution.CHEMIN_DB),
    "gouvernance_serveur": str(serveur.CHEMIN_GOUVERNANCE_DB),
    "gouvernance_front": str(depot.CHEMIN_GOUVERNANCE_DB),
    "journal": str(journal.CHEMIN_JOURNAL),
}))
"""


def _executer(script: str, dossier: Path) -> dict:
    sortie = subprocess.run(
        [sys.executable, "-c", script, str(dossier)],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8",
    )
    assert sortie.returncode == 0, sortie.stderr
    return json.loads(sortie.stdout)


def test_chaque_module_lit_ses_chemins_dans_l_enseigne_active(tmp_path, ecrire_enseigne):
    donnees = tmp_path / "donnees"
    ecrire_enseigne(tmp_path, "essai", donnees.as_posix())
    assert _executer(SCRIPT_CHEMINS, tmp_path) == {
        "corpus": str(donnees / "corpus"),
        "canonique": str(donnees / "canonique"),
        "chroma": str(donnees / "chroma"),
        "bm25": str(donnees / "chroma" / "bm25.pkl"),
        "collection": "essai_docs",
        "base_sql": str(donnees / "essai.db"),
        "gouvernance_serveur": str(donnees / "gouvernance.db"),
        "gouvernance_front": str(donnees / "gouvernance.db"),
        "journal": str(donnees / "appels.jsonl"),
    }


SCRIPT_TEXTES = PREAMBULE + """
from sorabel_rag import extraction
from sorabel_rag import generation as generation_rag
from sorabel_sql import generation as generation_sql
from sorabel_sql import schema, tools
tools.generer = lambda question, perimetre: None
print(json.dumps({
    "prompt_rag": generation_rag.PROMPT_SYSTEME,
    "prompt_sql": generation_sql.PROMPT_SYSTEME,
    "pied_de_page": extraction.PIED_DE_PAGE,
    "schema_stocks": schema._table_commentee("stocks", frozenset()),
    "hors_schema": tools.ask_database("question quelconque", None)["message"],
}))
"""


def test_chaque_module_lit_ses_textes_dans_l_enseigne_active(tmp_path, ecrire_enseigne):
    ecrire_enseigne(tmp_path, "essai", (tmp_path / "donnees").as_posix())
    textes = _executer(SCRIPT_TEXTES, tmp_path)
    assert textes["prompt_rag"].startswith("Tu es l'assistant documentaire de essai. ")
    assert "LECTURE SEULE sur la base essai. Règles strictes" in textes["prompt_sql"]
    assert textes["pied_de_page"] == "Document essai"
    assert "  entrepot TEXT,  -- ENTREPOT-essai" in textes["schema_stocks"]
    assert textes["hors_schema"] == "Cette question ne correspond à aucune table de la base essai."
    assert "Sorabel" not in textes["prompt_rag"] + textes["prompt_sql"] + textes["schema_stocks"]


def test_changer_d_enseigne_entre_deux_imports_est_refuse(tmp_path, ecrire_enseigne):
    """Le scénario `.env` : `load_dotenv()` s'exécute à l'import de `sorabel_rag.index`, après
    que d'autres modules ont déjà figé leurs constantes sur l'enseigne d'origine. Sans refus,
    le processus mêlerait deux enseignes (chemins de l'une, collection de l'autre)."""
    ecrire_enseigne(tmp_path, "essai", (tmp_path / "donnees").as_posix())
    script = PREAMBULE + """
from gouvernance import journal
os.environ["SORABEL_ENSEIGNE"] = "sorabel"
from sorabel_rag import index
"""
    sortie = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8",
        # Sous Windows, stderr du fils sort en cp1252 par défaut : le message accentué
        # ferait échouer le décodage UTF-8 côté test.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert sortie.returncode != 0
    assert "ValueError" in sortie.stderr
    assert "essai" in sortie.stderr and "sorabel" in sortie.stderr
