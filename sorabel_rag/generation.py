"""Génération de réponse RAG : retrieval + appel LLM + citations construites en code.

Les citations ne sont JAMAIS demandées au LLM : elles sont dérivées des métadonnées des
chunks réellement passés au prompt (titre, référence, date) — contrainte non négociable.
"""

from __future__ import annotations

from sorabel_enseigne import Enseigne, enseigne_active
from sorabel_llm.client import completer

from .chunking import texte_complet
from .recherche import SEUIL_REFUS, Resultat, rechercher

PROMPT_SYSTEME = (
    f"Tu es {enseigne_active().presentation}. "
    "Réponds à la question UNIQUEMENT à partir des extraits fournis ci-dessous, en français. "
    "Si les extraits ne permettent pas de répondre complètement, dis-le explicitement. "
    "Ne cite jamais tes sources toi-même : elles sont ajoutées automatiquement par le système."
)


def seuil_refus_de(enseigne: Enseigne) -> float:
    """Un seuil se calibre sur un corpus : une enseigne qui a mesuré le sien le déclare
    (`rag.seuil_refus`), les autres gardent celui du moteur, mesuré sur Sorabel."""
    return SEUIL_REFUS if enseigne.seuil_refus is None else enseigne.seuil_refus


# Figé à l'import, comme PROMPT_SYSTEME : une enseigne par processus.
SEUIL_REFUS_ENSEIGNE = seuil_refus_de(enseigne_active())


def _construire_prompt(question: str, resultats: list[Resultat]) -> list[dict]:
    extraits = "\n\n---\n\n".join(
        texte_complet(r.metadonnees, r.texte) for r in resultats
    )
    return [
        {"role": "system", "content": PROMPT_SYSTEME},
        {"role": "user", "content": f"Extraits :\n\n{extraits}\n\nQuestion : {question}"},
    ]


def _construire_citations(resultats: list[Resultat]) -> list[dict]:
    """Une citation par document source, dédoublonnée, dans l'ordre de première apparition."""
    vues: dict[str, dict] = {}
    for r in resultats:
        doc_id = r.metadonnees.get("doc_id", r.chunk_id)
        if doc_id not in vues:
            vues[doc_id] = {
                "titre": r.titre,
                "reference": r.reference or None,
                "date": r.metadonnees.get("date") or None,
                "type_document": r.metadonnees.get("type_document", ""),
            }
    return list(vues.values())


def repondre(question: str, k: int = 5, perimetre=None) -> dict:
    """Le tool `answer_question` du catalogue MCP (chantier 1).

    `perimetre=None` : aucune restriction de collection (comportement de la Phase 2). Un
    `Perimetre` réel (Phase 4) restreint le retrieval aux collections autorisées du profil —
    appliqué DANS le retrieval, pas en post-filtrage des résultats (E5)."""
    collections = perimetre.collections_autorisees() if perimetre is not None else None
    resultats = rechercher(
        question, k=k, config="hybride_rerank", collections_autorisees=collections
    )
    if not resultats or resultats[0].score < SEUIL_REFUS_ENSEIGNE:
        return {
            "statut": "hors_corpus",
            "message": "Je ne trouve pas de réponse à cette question dans le corpus documentaire.",
        }

    reponse = completer(_construire_prompt(question, resultats))
    return {
        "statut": "ok",
        "reponse": reponse,
        "citations": _construire_citations(resultats),
        "chunks_utilises": [r.chunk_id for r in resultats],
    }
