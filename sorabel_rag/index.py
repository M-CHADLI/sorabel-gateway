"""Les deux index de la recherche hybride : Chroma (dense) et BM25 (lexical).

Ils sont volontairement séparés. Un modèle unique produisant les deux signaux (BGE-m3)
existe, mais il rendrait impossible d'isoler l'apport de chaque moteur — or E6 demande
précisément de *mesurer et documenter* le gain de l'hybride sur le dense seul.
"""

from __future__ import annotations

import json
import pickle
import re
import unicodedata
from pathlib import Path

from .chunking import Chunk

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CHROMA = RACINE / "data" / "chroma"
CHEMIN_BM25 = RACINE / "data" / "chroma" / "bm25.pkl"
NOM_COLLECTION = "sorabel_docs"

# `-base` : 768 dimensions, ~1,1 Go. `-large` (1024 dims) est meilleur mais double le poids
# pour un corpus de 400 chunks où le lexical porte déjà l'essentiel du signal discriminant.
MODELE_EMBEDDING = "intfloat/multilingual-e5-base"

# e5 exige ces préfixes : il a été entraîné ainsi. Les omettre dégrade nettement les scores.
PREFIXE_PASSAGE = "passage: "
PREFIXE_REQUETE = "query: "

# `ref-8842` reste UN token : c'est tout l'intérêt du lexical ici. Un découpage naïf sur les
# caractères non alphanumériques le casserait en « ref » + « 8842 », et ferait perdre à BM25
# exactement la précision qui justifie sa présence.
MOTIF_TOKEN = re.compile(r"ref-\d{4}|[a-z0-9]+")


def _plier_accents(texte: str) -> str:
    """« endommagé » et « endommage » doivent produire le même token.

    Le corpus est intégralement accentué, les utilisateurs ne le seront pas toujours. Le
    pliage s'applique des deux côtés — index et requête — donc ne dégrade rien. Il ne
    concerne que BM25 : côté dense, plier les accents du corpus appauvrirait le texte
    embeddé, et le modèle e5 gère lui-même les variantes.
    """
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def tokeniser(texte: str) -> list[str]:
    return MOTIF_TOKEN.findall(_plier_accents(texte.lower()))


_modele = None


def charger_modele():
    """Chargé paresseusement : l'ingestion et le chunking n'ont pas besoin du modèle."""
    global _modele
    if _modele is None:
        from sentence_transformers import SentenceTransformer

        _modele = SentenceTransformer(MODELE_EMBEDDING)
    return _modele


def encoder_passages(textes: list[str]):
    modele = charger_modele()
    return modele.encode(
        [PREFIXE_PASSAGE + t for t in textes],
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=32,
    )


def encoder_requete(texte: str):
    modele = charger_modele()
    return modele.encode(PREFIXE_REQUETE + texte, normalize_embeddings=True)


def ouvrir_collection(creer: bool = False):
    import chromadb

    DOSSIER_CHROMA.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(DOSSIER_CHROMA))
    if creer:
        try:
            client.delete_collection(NOM_COLLECTION)
        except Exception:
            pass
        return client.create_collection(
            NOM_COLLECTION, metadata={"hnsw:space": "cosine"}
        )
    return client.get_collection(NOM_COLLECTION)


def indexer(chunks: list[Chunk]) -> dict:
    """Construit les deux index à partir des mêmes chunks, dans le même ordre."""
    collection = ouvrir_collection(creer=True)
    vecteurs = encoder_passages([c.texte for c in chunks])

    collection.add(
        ids=[c.chunk_id for c in chunks],
        embeddings=[v.tolist() for v in vecteurs],
        documents=[c.texte_brut for c in chunks],
        metadatas=[c.metadonnees for c in chunks],
    )

    # BM25 indexe `texte` (en-tête comprise) : titre et référence doivent être atteignables
    # lexicalement, c'est le seul discriminant entre les 80 notices au corps identique.
    from rank_bm25 import BM25Okapi

    corpus_tokenise = [tokeniser(c.texte) for c in chunks]
    CHEMIN_BM25.parent.mkdir(parents=True, exist_ok=True)
    with CHEMIN_BM25.open("wb") as fichier:
        pickle.dump(
            {
                "bm25": BM25Okapi(corpus_tokenise),
                "chunk_ids": [c.chunk_id for c in chunks],
                "modele_embedding": MODELE_EMBEDDING,
            },
            fichier,
        )

    return {
        "chunks": len(chunks),
        "dimensions": len(vecteurs[0]),
        "modele": MODELE_EMBEDDING,
    }


def charger_bm25() -> tuple:
    with CHEMIN_BM25.open("rb") as fichier:
        donnees = pickle.load(fichier)
    return donnees["bm25"], donnees["chunk_ids"]
