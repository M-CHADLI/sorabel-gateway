"""Les deux index de la recherche hybride : Chroma (dense) et BM25 (lexical).

Ils sont volontairement séparés. Un modèle unique produisant les deux signaux (BGE-m3)
existe, mais il rendrait impossible d'isoler l'apport de chaque moteur — or E6 demande
précisément de *mesurer et documenter* le gain de l'hybride sur le dense seul.
"""

from __future__ import annotations

import json
import os
import pickle
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

from .chunking import Chunk

load_dotenv()

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CHROMA = RACINE / "data" / "chroma"
CHEMIN_BM25 = RACINE / "data" / "chroma" / "bm25.pkl"
NOM_COLLECTION = "sorabel_docs"

# Embeddings servis par le déploiement Azure AI Foundry, plus en local : le CPU mettait
# une centaine de secondes à charger le modèle à chaque démarrage de processus.
# `text-embedding-3-small` renvoie 1536 dimensions, déjà normalisées (norme 1), ce que la
# collection Chroma attend puisqu'elle est configurée en distance cosinus.
MODELE_EMBEDDING = os.environ.get(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
)
# Lot volontairement modeste : 400 chunks passent en 4 requêtes, et un lot trop gros
# expose au refus pour dépassement de la limite de tokens par requête.
TAILLE_LOT_EMBEDDING = 128

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


_client_embedding = None


def _client():
    """Client OpenAI pointé sur le déploiement d'embeddings Foundry.

    L'endpoint et la clé peuvent être propres au déploiement d'embeddings (modèle servi en
    « serverless », hors de la ressource Azure OpenAI) ; à défaut on réutilise ceux de la
    génération, cas où tout est servi par la même ressource.
    """
    global _client_embedding
    if _client_embedding is None:
        from openai import OpenAI

        base = (
            os.environ.get("AZURE_EMBEDDING_ENDPOINT")
            or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        ).strip().rstrip("/")
        if not base:
            raise RuntimeError(
                "AZURE_EMBEDDING_ENDPOINT (ou AZURE_OPENAI_ENDPOINT) manquante : "
                "renseigner le .env pour l'accès aux embeddings."
            )
        cle = os.environ.get("AZURE_EMBEDDING_API_KEY") or os.environ.get(
            "AZURE_OPENAI_API_KEY"
        )
        if not cle:
            raise RuntimeError(
                "AZURE_EMBEDDING_API_KEY (ou AZURE_OPENAI_API_KEY) manquante."
            )
        if not base.endswith("/openai/v1"):
            base = f"{base}/openai/v1"
        _client_embedding = OpenAI(base_url=base, api_key=cle)
    return _client_embedding


def _encoder(textes: list[str]) -> list[list[float]]:
    """Encode par lots, en préservant l'ordre d'entrée.

    L'API peut renvoyer les objets dans le désordre : on se fie à `index`, jamais à la
    position dans la réponse — une inversion silencieuse associerait chaque vecteur au
    mauvais chunk, et l'index entier deviendrait faux sans erreur visible.
    """
    vecteurs: list[list[float]] = []
    for debut in range(0, len(textes), TAILLE_LOT_EMBEDDING):
        lot = textes[debut : debut + TAILLE_LOT_EMBEDDING]
        reponse = _client().embeddings.create(model=MODELE_EMBEDDING, input=lot)
        vecteurs.extend(d.embedding for d in sorted(reponse.data, key=lambda d: d.index))
    return vecteurs


def encoder_passages(textes: list[str]) -> list[list[float]]:
    return _encoder(textes)


def encoder_requete(texte: str) -> list[float]:
    return _encoder([texte])[0]


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
        embeddings=vecteurs,
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
