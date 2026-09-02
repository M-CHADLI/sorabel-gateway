"""Chunking puis indexation : canoniques -> Chroma (dense) + BM25 (lexical)."""

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sorabel_rag.chunking import chunker_corpus
from sorabel_rag.index import indexer
from sorabel_rag.ingestion import SORTIE
from sorabel_rag.modeles import DocumentCanonique


def charger_canoniques():
    documents = []
    for chemin in sorted(glob.glob(str(SORTIE / "*.json"))):
        if Path(chemin).name.startswith("_"):
            continue
        documents.append(
            DocumentCanonique.depuis_dict(json.loads(Path(chemin).read_text(encoding="utf-8")))
        )
    manifeste = json.loads((SORTIE / "_manifeste.json").read_text(encoding="utf-8"))
    return documents, manifeste


if __name__ == "__main__":
    documents, manifeste = charger_canoniques()
    chunks = chunker_corpus(documents, manifeste)
    print(f"{len(documents)} documents -> {len(chunks)} chunks")
    bilan = indexer(chunks)
    print(f"indexes : {bilan['chunks']} chunks | {bilan['dimensions']} dims | {bilan['modele']}")
