"""Lance l'ingestion du corpus : sources -> canoniques + manifeste + rapport qualite."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sorabel_rag.ingestion import SORTIE, ingerer

if __name__ == "__main__":
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--forcer", action="store_true", help="ignore le cache et reextrait tout le corpus"
    )
    arguments = analyseur.parse_args()

    documents, manifeste = ingerer(forcer=arguments.forcer)
    indexables = sum(1 for d in documents if d.qualite.indexable)
    print(f"{len(documents)} documents traites, {indexables} indexables")
    print(f"{len(manifeste['groupes'])} groupes de versions")
    print(f"-> {SORTIE}")
    print(f"-> {SORTIE / '_rapport.md'}")
