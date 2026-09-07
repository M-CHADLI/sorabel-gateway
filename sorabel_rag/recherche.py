"""Retrieval : dense, hybride (RRF), hybride + rerank.

Les trois configurations coexistent volontairement dans le même module : E6 exige de
comparer la recherche avancée à la recherche dense initiale sur le même index et les mêmes
questions. Une baseline qu'on ne peut plus exécuter ne prouve rien.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import numpy as np
from dotenv import load_dotenv

load_dotenv()

from sorabel_llm.client import completer

from .index import (
    charger_bm25,
    encoder_requete,
    ouvrir_collection,
    tokeniser,
)
from .chunking import texte_complet
from .modeles import MOTIF_REFERENCE

PROFONDEUR = 30  # candidats par moteur avant fusion — réglable via l'éval (Recall@N)
K_RRF = 60  # constante de l'article d'origine (Cormack et al., 2009)

# Les scores RRF valent ~1/61 ≈ 0,016. Un bonus de cet ordre de grandeur mille fois
# supérieur agit comme un filtre : les documents dont la référence est le SUJET passent
# devant tout le reste, sans pour autant exclure les autres de la liste — la question
# « REF-8842 est-il compatible triphasé ? » peut trouver sa réponse ailleurs.
BONUS_REFERENCE_SUJET = 1.0
BONUS_REFERENCE_CITEE = 0.1

# Reranking confié au LLM de génération, en un seul appel « listwise » (tous les candidats
# notés ensemble). Deux prédécesseurs écartés :
#   - `bge-reranker-v2-m3` en local : ~34 s par recherche sur CPU, l'essentiel du temps de
#     réponse ;
#   - `Cohere-rerank-v4.0-fast` sur Foundry : rapide (~2,8 s) mais le quota du déploiement
#     tombe en 429 dès deux recherches consécutives, ce qui interdit jusqu'à la calibration
#     du seuil.
# Historique plus ancien : `mmarco-mMiniLMv2` notait une question hors corpus (« capitale de
# l'Australie », −4,49) AU-DESSUS de questions couvertes (−6,02) ; ses scores n'étant pas
# comparables d'une question à l'autre, aucun seuil de refus n'en était tirable, donc pas
# d'E1. Le LLM, lui, note sur un barème explicite et donne 0 partout hors corpus.
MODELE_RERANKER = "llm-listwise"

# Barème du prompt : 1,0 répond directement, 0,5 sujet proche, 0,0 sans rapport. Une
# question hors corpus obtient 0 sur tous les candidats, d'où un seuil franc à mi-chemin
# entre « sans rapport » et « sujet proche ».
SEUIL_REFUS = 0.3

# Le prompt porte tous les candidats : on tronque chacun pour borner la taille d'entrée
# sans perdre l'amorce, seule partie qui sert à juger la pertinence.
LONGUEUR_EXTRAIT_RERANK = 700

# Les échecs observés sont transitoires (JSON tronqué) : une seconde tentative suffit
# presque toujours.
TENTATIVES_RERANK = 3


class RerankIndisponible(RuntimeError):
    """Le reranking n'a pas abouti : panne technique, à ne pas confondre avec un refus
    documentaire (`hors_corpus`), qui, lui, signifie que le corpus ne couvre pas le sujet."""

PROMPT_RERANK = """Tu notes la pertinence de chaque document pour répondre à la question.

Barème :
- 1.0 : le document répond directement à la question
- 0.5 : le document traite d'un sujet proche sans répondre
- 0.0 : le document est sans rapport avec la question

Note CHAQUE document indépendamment ; plusieurs documents peuvent avoir la même note. Si
aucun document ne concerne la question, mets 0.0 partout — ne cherche pas à en favoriser un.

Réponds UNIQUEMENT par un JSON de la forme {"scores": [{"i": <index>, "s": <note>}]},
contenant une entrée pour TOUS les documents, sans texte autour."""

# Une requête réduite à une référence vise le document principal du produit, pas une note
# qui la mentionne en passant. BM25 classe l'inverse : il normalise par la longueur.
PREFERENCE_TYPE_SUR_REFERENCE_SEULE = {"fiche_technique": 0.02, "notice": 0.01}

# Une "collection" de gouvernance n'est pas une collection Chroma : c'est un regroupement
# métier (chantier 3) qui se traduit en filtre sur type_document (+ sous_type pour distinguer
# les deux familles de notes — cf. docs/conception.md, chantier MCP §2).
SOUS_TYPES_OPERATIONNELS = frozenset({"logistique", "alerte_qualite", "retour_terrain"})
SOUS_TYPES_CONFIDENTIELS = frozenset({"politique_tarifaire", "reunion_achat"})

CONDITION_COLLECTION: dict[str, dict] = {
    "fiches": {"type_document": "fiche_technique"},
    "notices": {"type_document": "notice"},
    "sav": {"type_document": "procedure_sav"},
    "notes_operationnelles": {
        "$and": [
            {"type_document": "note_interne"},
            {"sous_type": {"$in": sorted(SOUS_TYPES_OPERATIONNELS)}},
        ]
    },
    "notes_confidentielles": {
        "$and": [
            {"type_document": "note_interne"},
            {"sous_type": {"$in": sorted(SOUS_TYPES_CONFIDENTIELS)}},
        ]
    },
}


def filtre_collections(collections_autorisees: frozenset[str] | None) -> dict | None:
    """`None` = aucune restriction (profil non gouverné, comportement historique)."""
    if collections_autorisees is None:
        return None
    conditions = [
        CONDITION_COLLECTION[c] for c in collections_autorisees if c in CONDITION_COLLECTION
    ]
    if not conditions:
        return {"type_document": "__aucune_collection_autorisee__"}  # ne matche jamais
    return conditions[0] if len(conditions) == 1 else {"$or": conditions}



@dataclass
class Resultat:
    chunk_id: str
    texte: str
    score: float
    metadonnees: dict
    scores_detail: dict = field(default_factory=dict)

    @property
    def reference(self) -> str:
        return self.metadonnees.get("reference", "")

    @property
    def titre(self) -> str:
        return self.metadonnees.get("titre", "")


def detecter_references(requete: str) -> list[str]:
    """Information certaine : l'utilisateur a nommé la référence, inutile de la deviner."""
    return list(dict.fromkeys(MOTIF_REFERENCE.findall(requete.upper())))


def _est_reference_seule(requete: str, references: list[str]) -> bool:
    """La requête ne contient rien d'autre que des références et de la ponctuation."""
    reste = MOTIF_REFERENCE.sub(" ", requete.upper())
    return bool(references) and not re.search(r"[A-Za-zÀ-ÿ]{3,}", reste)


def _filtre_chroma(
    inclure_versions_anciennes: bool,
    type_document: str | None,
    collections_autorisees: frozenset[str] | None = None,
) -> dict | None:
    conditions = []
    if not inclure_versions_anciennes:
        conditions.append({"est_version_courante": True})
    if type_document:
        conditions.append({"type_document": type_document})
    filtre_gouvernance = filtre_collections(collections_autorisees)
    if filtre_gouvernance:
        conditions.append(filtre_gouvernance)
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def _rangs(ordre: list[str]) -> dict[str, int]:
    return {chunk_id: rang for rang, chunk_id in enumerate(ordre, start=1)}


def rechercher(
    requete: str,
    k: int = 5,
    config: str = "hybride_rerank",
    profondeur: int = PROFONDEUR,
    type_document: str | None = None,
    inclure_versions_anciennes: bool = False,
    collections_autorisees: frozenset[str] | None = None,
) -> list[Resultat]:
    """`config` ∈ {dense, hybride, hybride_rerank} — les trois configurations de l'éval.
    `collections_autorisees` : `None` = aucune restriction ; sinon un sous-ensemble de
    {fiches, notices, sav, notes_operationnelles, notes_confidentielles} (gouvernance, E5)."""
    collection = ouvrir_collection()
    filtre = _filtre_chroma(inclure_versions_anciennes, type_document, collections_autorisees)

    # ---- moteur dense ----------------------------------------------------------------
    vecteur = encoder_requete(requete)
    reponse = collection.query(
        query_embeddings=[vecteur],
        n_results=profondeur,
        where=filtre,
        include=["metadatas", "documents", "distances"],
    )
    ids_dense = reponse["ids"][0]
    infos: dict[str, dict] = {
        chunk_id: {"texte": texte, "metadonnees": meta, "cosinus": 1 - distance}
        for chunk_id, texte, meta, distance in zip(
            ids_dense, reponse["documents"][0], reponse["metadatas"][0], reponse["distances"][0]
        )
    }

    if config == "dense":
        return [
            Resultat(chunk_id, infos[chunk_id]["texte"], infos[chunk_id]["cosinus"],
                     infos[chunk_id]["metadonnees"], {"cosinus": infos[chunk_id]["cosinus"]})
            for chunk_id in ids_dense[:k]
        ]

    # ---- moteur lexical --------------------------------------------------------------
    bm25, tous_ids = charger_bm25()
    scores_bm25 = bm25.get_scores(tokeniser(requete))
    ordre_bm25 = np.argsort(scores_bm25)[::-1]

    autorises = _ids_autorises(collection, filtre)
    ids_bm25: list[str] = []
    for position in ordre_bm25:
        chunk_id = tous_ids[position]
        if autorises is not None and chunk_id not in autorises:
            continue
        ids_bm25.append(chunk_id)
        if len(ids_bm25) >= profondeur:
            break

    manquants = [chunk_id for chunk_id in ids_bm25 if chunk_id not in infos]
    if manquants:
        complement = collection.get(ids=manquants, include=["metadatas", "documents"])
        for chunk_id, texte, meta in zip(
            complement["ids"], complement["documents"], complement["metadatas"]
        ):
            infos[chunk_id] = {"texte": texte, "metadonnees": meta, "cosinus": 0.0}

    # ---- fusion RRF ------------------------------------------------------------------
    rangs_dense, rangs_bm25 = _rangs(ids_dense), _rangs(ids_bm25)
    scores: dict[str, float] = {}
    detail: dict[str, dict] = {}
    for chunk_id in set(ids_dense) | set(ids_bm25):
        rrf = 0.0
        if chunk_id in rangs_dense:
            rrf += 1 / (K_RRF + rangs_dense[chunk_id])
        if chunk_id in rangs_bm25:
            rrf += 1 / (K_RRF + rangs_bm25[chunk_id])
        scores[chunk_id] = rrf
        detail[chunk_id] = {
            "rrf": rrf,
            "rang_dense": rangs_dense.get(chunk_id),
            "rang_bm25": rangs_bm25.get(chunk_id),
        }

    # ---- références détectées : filtre déguisé en bonus ------------------------------
    references = detecter_references(requete)
    reference_seule = _est_reference_seule(requete, references)
    for reference in references:
        for chunk_id, info in infos.items():
            meta = info["metadonnees"]
            if meta.get("reference") == reference:
                scores[chunk_id] += BONUS_REFERENCE_SUJET
                detail[chunk_id]["reference_sujet"] = True
                if reference_seule:
                    scores[chunk_id] += PREFERENCE_TYPE_SUR_REFERENCE_SEULE.get(
                        meta.get("type_document", ""), 0.0
                    )
            elif reference in (meta.get("references_citees") or "").split("|"):
                scores[chunk_id] += BONUS_REFERENCE_CITEE
                detail[chunk_id]["reference_citee"] = True

    classes = sorted(scores, key=scores.get, reverse=True)

    if config == "hybride":
        return [
            Resultat(chunk_id, infos[chunk_id]["texte"], scores[chunk_id],
                     infos[chunk_id]["metadonnees"], detail[chunk_id])
            for chunk_id in classes[:k]
        ]

    # ---- reranking cross-encoder -----------------------------------------------------
    candidats = classes[:profondeur]
    # `infos[...]["texte"]` vient du champ `documents` de Chroma, qui ne contient que
    # `texte_brut`. Le donner tel quel au reranker le prive de l'en-tête contextuelle —
    # donc du titre, seul élément qui distingue deux procédures SAV à la trame identique.
    scores_rerank = _reranker_scores(
        requete,
        [texte_complet(infos[c]["metadonnees"], infos[c]["texte"]) for c in candidats],
    )
    for chunk_id, score in zip(candidats, scores_rerank):
        detail[chunk_id]["rerank"] = float(score)

    # Le score du reranker sert à DEUX choses qu'il faut garder distinctes :
    #   - le classement, où le bonus de référence doit continuer à peser (le cross-encoder
    #     ignore lui aussi qu'un identifiant est un identifiant) ;
    #   - le seuil de refus (E1), qui doit lire le score brut, non bonifié — sans quoi la
    #     seule présence d'une référence dans la question suffirait à faire répondre.
    # D'où un tri sur un couple, et non sur une somme qui mélangerait les deux rôles.
    candidats.sort(
        key=lambda c: (detail[c].get("reference_sujet", False), detail[c]["rerank"]),
        reverse=True,
    )
    for chunk_id in candidats:
        detail[chunk_id]["score_final"] = detail[chunk_id]["rerank"]

    return [
        Resultat(chunk_id, infos[chunk_id]["texte"], detail[chunk_id]["rerank"],
                 infos[chunk_id]["metadonnees"], detail[chunk_id])
        for chunk_id in candidats[:k]
    ]


def _ids_autorises(collection, filtre: dict | None) -> set[str] | None:
    """BM25 ne connaît pas les métadonnées : le filtre s'applique après coup, sur les ids."""
    if filtre is None:
        return None
    return set(collection.get(where=filtre, include=[])["ids"])


def _extraire_json(reponse: str) -> dict:
    """Isole l'objet JSON d'une réponse LLM, même entourée de texte ou d'un bloc Markdown."""
    debut, fin = reponse.find("{"), reponse.rfind("}")
    if debut == -1 or fin <= debut:
        raise ValueError("aucun objet JSON dans la réponse du reranker")
    return json.loads(reponse[debut : fin + 1])


def _reranker_scores(requete: str, textes: list[str]) -> list[float]:
    """Pertinence de chaque texte pour la requête, dans l'ordre d'entrée.

    Un seul appel pour tous les candidats : le modèle les compare entre eux, et le coût ne
    dépend pas de la profondeur. Un index absent de la réponse vaut 0 — mieux vaut refuser
    un document que le classer sur une note inventée.

    Une réponse inexploitable est retentée : l'échec est le plus souvent transitoire (JSON
    tronqué ou entouré de texte). Si toutes les tentatives échouent, on LÈVE — surtout pas
    des notes nulles, qui feraient passer une panne pour un « hors corpus » alors que le
    corpus contient peut-être la réponse. E1 exige que le client puisse distinguer un refus
    documentaire d'une défaillance technique ; les confondre trahirait les deux.
    """
    if not textes:
        return []

    extraits = "\n\n".join(
        f"[{i}] {texte[:LONGUEUR_EXTRAIT_RERANK]}" for i, texte in enumerate(textes)
    )
    messages = [
        {"role": "system", "content": PROMPT_RERANK},
        {"role": "user", "content": f"Question : {requete}\n\nDocuments :\n{extraits}"},
    ]

    derniere_erreur: Exception | None = None
    for _ in range(TENTATIVES_RERANK):
        try:
            notes = _extraire_json(completer(messages))["scores"]
        except Exception as erreur:  # réponse absente, tronquée, ou JSON malformé
            derniere_erreur = erreur
            continue
        scores = [0.0] * len(textes)
        for note in notes:
            indice = int(note["i"])
            if 0 <= indice < len(textes):
                scores[indice] = float(note["s"])
        return scores

    raise RerankIndisponible(
        f"le reranker n'a pas produit de notation exploitable en {TENTATIVES_RERANK} "
        f"tentatives : {derniere_erreur}"
    ) from derniere_erreur
