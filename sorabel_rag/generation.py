"""Génération de réponse RAG : retrieval + appel LLM + citations construites en code.

Les citations ne sont JAMAIS demandées au LLM : elles sont dérivées des métadonnées des
chunks réellement passés au prompt (titre, référence, date) — contrainte non négociable.
"""

from __future__ import annotations

from sorabel_llm.client import completer

from .chunking import texte_complet
from .recherche import SEUIL_REFUS, Resultat, rechercher

PROMPT_SYSTEME = (
    "Tu es l'assistant documentaire de Sorabel, distributeur B2B de matériel électrique. "
    "Réponds à la question UNIQUEMENT à partir des extraits fournis ci-dessous, en français. "
    "Si les extraits ne permettent pas de répondre complètement, dis-le explicitement. "
    "Ne cite jamais tes sources toi-même : elles sont ajoutées automatiquement par le système."
)


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


def repondre(question: str, k: int = 5) -> dict:
    """Le tool `answer_question` du catalogue MCP (chantier 1)."""
    resultats = rechercher(question, k=k, config="hybride_rerank")
    if not resultats or resultats[0].score < SEUIL_REFUS:
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
