"""Chaque module du moteur lit son enseigne dans sorabel_enseigne, et nulle part ailleurs.

Vérifié dans un interpréteur neuf : les constantes sont évaluées à l'import, et le
processus de test a déjà importé ces modules avec l'enseigne sorabel (tests/conftest.py).
"""

import json
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
