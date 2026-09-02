"""Orchestration de l'ingestion : sources → canoniques → manifeste → rapport qualité.

Trois sorties, toutes sur disque et toutes lisibles à la main :

    canonique/<doc_id>.json   un document canonique par fichier source
    canonique/_manifeste.json les propriétés qui dépendent du corpus entier
    canonique/_rapport.md     le contrôle qualité, à lire AVANT d'indexer
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .extraction import EXTRACTEURS
from .modeles import (
    LIBELLES_ALERTES,
    SCHEMA_VERSION,
    DocumentCanonique,
    cle_de_tri_version,
    hacher_fichier,
)

RACINE = Path(__file__).resolve().parent.parent
CORPUS = RACINE / "data" / "data" / "corpus"
SORTIE = RACINE / "data" / "canonique"


@dataclass
class Bilan:
    extraits: int = 0
    depuis_cache: int = 0
    bloquants: int = 0
    doublons: int = 0


def _chemin_canonique(doc_id: str) -> Path:
    """`fiche_technique:REF-1024:v2.1` → un nom de fichier valide sous Windows."""
    return SORTIE / f"{doc_id.replace(':', '__')}.json"


def _indexer_cache() -> dict[str, dict]:
    """`source_path` → canonique déjà écrit. Construit en une passe : on ne connaît le
    `doc_id` qu'après extraction, donc le chemin source est le seul lien stable avant."""
    index: dict[str, dict] = {}
    for candidat in SORTIE.glob("*.json"):
        if candidat.name.startswith("_"):
            continue
        try:
            donnees = json.loads(candidat.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # canonique corrompu : on le ré-extraira
        if "source_path" in donnees:
            index[donnees["source_path"]] = donnees
    return index


def _cache_valide(chemin_source: Path, donnees: dict | None) -> DocumentCanonique | None:
    """Le canonique est réutilisable si la source ET les règles d'extraction sont inchangées.

    Le second garde-fou est indispensable : sans lui, modifier une règle d'extraction
    laisserait des canoniques périmés en place, et on déboguerait sur des données obsolètes.
    """
    if not donnees:
        return None
    if donnees.get("schema_version") != SCHEMA_VERSION:
        return None
    if donnees.get("hash_source") != hacher_fichier(chemin_source):
        return None
    return DocumentCanonique.depuis_dict(donnees)


def extraire_corpus(forcer: bool = False) -> tuple[list[DocumentCanonique], Bilan]:
    SORTIE.mkdir(parents=True, exist_ok=True)
    documents: list[DocumentCanonique] = []
    bilan = Bilan()
    hashs_vus: dict[str, str] = {}
    index_cache = {} if forcer else _indexer_cache()

    for dossier, (extracteur, motif) in EXTRACTEURS.items():
        for chemin in sorted((CORPUS / dossier).glob(motif)):
            cle_source = str(chemin).replace("\\", "/")
            depuis_cache = _cache_valide(chemin, index_cache.get(cle_source))

            if depuis_cache:
                document = depuis_cache
                bilan.depuis_cache += 1
            else:
                document = extracteur(chemin)
                _chemin_canonique(document.doc_id).write_text(
                    json.dumps(document.en_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                bilan.extraits += 1

            if document.hash_texte in hashs_vus:
                document.qualite.alertes.append("doublon_contenu")
                bilan.doublons += 1
            else:
                hashs_vus[document.hash_texte] = document.doc_id

            if not document.qualite.indexable:
                bilan.bloquants += 1
            documents.append(document)

    return documents, bilan


def construire_manifeste(documents: list[DocumentCanonique]) -> dict:
    """Les propriétés qui dépendent du corpus entier — jamais dans un canonique.

    Savoir si `v2.1` est la version courante suppose de connaître toutes les autres
    versions du groupe. Mettre cette information dans le canonique obligerait à réécrire
    des fichiers dont la source n'a pas bougé, et rendrait le cache impossible.
    """
    groupes: dict[str, list[DocumentCanonique]] = defaultdict(list)
    for document in documents:
        if document.qualite.indexable:
            groupes[document.cle_groupe].append(document)

    manifeste = {
        "schema_version": SCHEMA_VERSION,
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "groupes": {},
    }
    for cle, membres in sorted(groupes.items()):
        membres.sort(key=lambda d: cle_de_tri_version(d.version))
        courant = membres[-1]
        manifeste["groupes"][cle] = {
            "type_document": courant.type_document,
            "reference": courant.reference,
            "titre": courant.titre,
            "versions": [d.version for d in membres],
            "version_courante": courant.version,
            "doc_id_courant": courant.doc_id,
            "doc_ids": [d.doc_id for d in membres],
        }
    return manifeste


def ecrire_rapport(documents: list[DocumentCanonique], bilan: Bilan, manifeste: dict) -> str:
    par_type = Counter(d.type_document for d in documents)
    alertes = Counter(a for d in documents for a in d.qualite.alertes)
    en_alerte = [d for d in documents if d.qualite.alertes]
    multi_versions = {
        cle: groupe for cle, groupe in manifeste["groupes"].items() if len(groupe["versions"]) > 1
    }
    sans_reference = [d for d in documents if not d.reference]

    lignes = [
        "# Rapport d'extraction",
        "",
        f"Généré le {manifeste['genere_le']} · schema_version {SCHEMA_VERSION}",
        "",
        "## Bilan",
        "",
        "| | |",
        "|---|---|",
        f"| Documents traités | {len(documents)} |",
        f"| Extraits | {bilan.extraits} |",
        f"| Repris du cache | {bilan.depuis_cache} |",
        f"| Groupes de versions | {len(manifeste['groupes'])} |",
        f"| Groupes multi-versions | {len(multi_versions)} |",
        f"| **Bloquants (non indexés)** | **{bilan.bloquants}** |",
        f"| Doublons de contenu | {bilan.doublons} |",
        f"| Sans référence produit | {len(sans_reference)} |",
        "",
        "## Par type",
        "",
        "| Type | Documents | Car. médian |",
        "|---|---|---|",
    ]
    for type_document, nombre in sorted(par_type.items()):
        tailles = sorted(len(d.texte) for d in documents if d.type_document == type_document)
        median = tailles[len(tailles) // 2] if tailles else 0
        lignes.append(f"| `{type_document}` | {nombre} | {median} |")

    lignes += ["", "## Alertes", ""]
    if not alertes:
        lignes.append("Aucune alerte : les 400 documents sont extraits proprement.")
    else:
        lignes += ["| Alerte | Occurrences | Sens |", "|---|---|---|"]
        for nom, nombre in alertes.most_common():
            lignes.append(f"| `{nom}` | {nombre} | {LIBELLES_ALERTES.get(nom, '—')} |")
        lignes += ["", "### Documents concernés", ""]
        for document in en_alerte[:40]:
            lignes.append(
                f"- `{document.doc_id}` — {', '.join(document.qualite.alertes)} "
                f"({document.source_path})"
            )
        if len(en_alerte) > 40:
            lignes.append(f"- … et {len(en_alerte) - 40} autres")

    lignes += ["", "## Groupes multi-versions", ""]
    lignes += ["| Groupe | Versions | Courante |", "|---|---|---|"]
    for cle, groupe in sorted(multi_versions.items())[:20]:
        lignes.append(
            f"| `{cle}` | {', '.join(groupe['versions'])} | **{groupe['version_courante']}** |"
        )
    if len(multi_versions) > 20:
        lignes.append(f"| … | {len(multi_versions) - 20} autres groupes | |")

    return "\n".join(lignes) + "\n"


def ingerer(forcer: bool = False) -> tuple[list[DocumentCanonique], dict]:
    documents, bilan = extraire_corpus(forcer=forcer)
    manifeste = construire_manifeste(documents)
    (SORTIE / "_manifeste.json").write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (SORTIE / "_rapport.md").write_text(
        ecrire_rapport(documents, bilan, manifeste), encoding="utf-8"
    )
    return documents, manifeste
