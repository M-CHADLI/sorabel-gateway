"""get_document et list_sources — accès direct aux documents canoniques et au manifeste.

Contrairement à search_docs/answer_question, ces deux tools ne passent pas par l'index
Chroma : ils lisent directement les fichiers produits par l'ingestion (chantier 1).
"""

from __future__ import annotations

import json

from .ingestion import SORTIE

COLLECTION_PAR_TYPE = {
    "fiche_technique": "fiches",
    "notice": "notices",
    "procedure_sav": "sav",
}
SOUS_TYPES_OPERATIONNELS = frozenset({"logistique", "alerte_qualite", "retour_terrain"})
SOUS_TYPES_CONFIDENTIELS = frozenset({"politique_tarifaire", "reunion_achat"})


def _collection_depuis_sous_type(sous_type: str) -> str | None:
    if sous_type in SOUS_TYPES_OPERATIONNELS:
        return "notes_operationnelles"
    if sous_type in SOUS_TYPES_CONFIDENTIELS:
        return "notes_confidentielles"
    return None


def _collection_du_document(type_document: str, attributs: dict) -> str | None:
    if type_document in COLLECTION_PAR_TYPE:
        return COLLECTION_PAR_TYPE[type_document]
    if type_document == "note_interne":
        return _collection_depuis_sous_type(attributs.get("sous_type", ""))
    return None


def _resoudre_doc_id_par_reference(reference: str, version: str | None) -> tuple[str | None, dict | None]:
    """`(doc_id, None)` si résolu, `(None, refus)` sinon. Une référence peut être partagée par
    plusieurs types de document (fiche technique ET notice) : sans version, la version
    courante du groupe unique est prise ; si plusieurs groupes matchent, c'est ambigu."""
    manifeste = json.loads((SORTIE / "_manifeste.json").read_text(encoding="utf-8"))
    candidats = {
        cle: groupe for cle, groupe in manifeste["groupes"].items()
        if groupe.get("reference") == reference
    }
    if not candidats:
        return None, {"statut": "hors_schema", "message": f"référence introuvable : {reference!r}"}
    if len(candidats) > 1:
        return None, {
            "statut": "hors_schema",
            "message": (
                f"référence {reference!r} ambiguë entre plusieurs types de document : "
                f"{', '.join(sorted(candidats))} — précisez un doc_id."
            ),
        }
    (groupe,) = candidats.values()
    if version is None:
        return groupe["doc_id_courant"], None
    correspondance = dict(zip(groupe["versions"], groupe["doc_ids"]))
    if version not in correspondance:
        return None, {
            "statut": "hors_schema",
            "message": f"version {version!r} introuvable pour {reference!r} "
                       f"(versions disponibles : {groupe['versions']})",
        }
    return correspondance[version], None


def obtenir_document(
    doc_id: str | None = None,
    reference: str | None = None,
    version: str | None = None,
    perimetre=None,
) -> dict:
    if doc_id is None and reference is None:
        return {
            "statut": "hors_schema",
            "message": "fournir doc_id, ou reference (+ version optionnelle)",
        }

    if doc_id is None:
        doc_id, refus = _resoudre_doc_id_par_reference(reference, version)
        if refus is not None:
            return refus

    chemin = SORTIE / f"{doc_id.replace(':', '__')}.json"
    if not chemin.exists():
        return {"statut": "hors_schema", "message": f"document introuvable : {doc_id!r}"}

    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    if perimetre is not None:
        collection = _collection_du_document(donnees["type_document"], donnees.get("attributs", {}))
        if collection is not None and collection not in perimetre.collections_autorisees():
            return {
                "statut": "non_autorise",
                "message": f"ce profil n'a pas accès à la collection {collection!r}",
            }

    return {"statut": "ok", "document": donnees}


def _collection_du_groupe(groupe: dict) -> str | None:
    type_document = groupe["type_document"]
    if type_document in COLLECTION_PAR_TYPE:
        return COLLECTION_PAR_TYPE[type_document]
    if type_document == "note_interne":
        chemin = SORTIE / f"{groupe['doc_id_courant'].replace(':', '__')}.json"
        if chemin.exists():
            attributs = json.loads(chemin.read_text(encoding="utf-8")).get("attributs", {})
            return _collection_depuis_sous_type(attributs.get("sous_type", ""))
    return None


def lister_sources(type_document: str | None = None, perimetre=None) -> dict:
    manifeste = json.loads((SORTIE / "_manifeste.json").read_text(encoding="utf-8"))
    collections_autorisees = perimetre.collections_autorisees() if perimetre is not None else None

    inventaire = []
    for cle, groupe in manifeste["groupes"].items():
        if type_document and groupe["type_document"] != type_document:
            continue
        if collections_autorisees is not None:
            collection = _collection_du_groupe(groupe)
            if collection is not None and collection not in collections_autorisees:
                continue
        inventaire.append({
            "cle_groupe": cle,
            "type_document": groupe["type_document"],
            "reference": groupe.get("reference"),
            "titre": groupe["titre"],
            "versions": groupe["versions"],
            "version_courante": groupe["version_courante"],
        })
    return {"statut": "ok", "sources": inventaire}
