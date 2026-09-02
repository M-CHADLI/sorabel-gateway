"""Canoniques + manifeste → chunks prêts à indexer.

La règle générale est structurelle (§2 du dossier de conception) : une section = un chunk,
redécoupe au-dessus de 500 tokens, fusion en dessous de 100. Sur *ce* corpus, mesuré, le
document le plus long fait ~250 tokens : la redécoupe ne se déclenche jamais et la fusion
s'applique partout. Résultat : 400 documents → 400 chunks.

La règle reste écrite et testée — elle se déclenchera le jour où un document plus long
entrera dans le corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .modeles import (
    TYPE_FICHE,
    TYPE_NOTE,
    TYPE_NOTICE,
    TYPE_SAV,
    DocumentCanonique,
    Section,
)

TAILLE_MAX = 500  # tokens — e5 tronque silencieusement au-delà de 512
TAILLE_MIN = 100  # tokens — en dessous, le vecteur n'est plus discriminant

# Ratio caractères/token mesuré sur du français. Le corpus étant très court (max ~250
# tokens), aucune décision de découpe ne se joue près du seuil : l'approximation suffit et
# évite de charger un tokenizer de 2 Go pour compter.
CARACTERES_PAR_TOKEN = 3.5

LIBELLES_TYPE = {
    TYPE_FICHE: "Fiche technique",
    TYPE_NOTICE: "Notice d'installation",
    TYPE_NOTE: "Note interne",
    TYPE_SAV: "Procédure SAV",
}


def compter_tokens(texte: str) -> int:
    return max(1, round(len(texte) / CARACTERES_PAR_TOKEN))


@dataclass
class Chunk:
    """Unité indexée. `texte` part à l'embedding, `texte_brut` est ce qu'on affiche."""

    chunk_id: str
    doc_id: str
    index: int
    section: str
    texte: str
    texte_brut: str
    n_tokens: int
    metadonnees: dict = field(default_factory=dict)


def entete_depuis_metadonnees(meta: dict) -> str:
    """L'en-tête contextuelle reconstruite depuis les métadonnées d'un chunk.

    Sur ce corpus, l'en-tête est le seul discriminant réel : les 80 notices ont un corps
    identique au mot près, et les procédures SAV partagent la même trame. Sans titre ni
    référence, elles sont littéralement indistinguables.

    Elle doit donc être présente partout où un modèle lit le chunk — à l'embedding, dans
    l'index BM25, **et à l'entrée du reranker**. Chroma ne stockant que `texte_brut` dans
    son champ `documents`, on la reconstruit ici plutôt que de dupliquer le texte complet.
    """
    type_document = meta.get("type_document", "")
    libelle = LIBELLES_TYPE.get(type_document, type_document)
    morceaux = [libelle]
    if meta.get("reference"):
        morceaux.append(meta["reference"])
    if meta.get("version"):
        morceaux.append(f"v{meta['version']}")
    entete = " ".join(morceaux)
    # Les titres SAV commencent déjà par « Procédure SAV — » : ne pas le répéter.
    titre = meta.get("titre", "")
    if titre.lower().startswith(libelle.lower()):
        titre = titre[len(libelle):].lstrip(" —-:")
    if titre:
        entete += f" — {titre}"
    if meta.get("section"):
        entete += f" — section « {meta['section']} »"
    return f"[{entete}]"


def texte_complet(meta: dict, texte_brut: str) -> str:
    """Le chunk tel qu'il a été indexé : en-tête + corps."""
    return f"{entete_depuis_metadonnees(meta)}\n{texte_brut}"


def construire_entete(document: DocumentCanonique, section: str | None) -> str:
    """L'en-tête contextuelle, préfixée au chunk AVANT embedding."""
    return entete_depuis_metadonnees(
        {
            "type_document": document.type_document,
            "reference": document.reference or "",
            "version": document.version,
            "titre": document.titre,
            "section": section or "",
        }
    )


def _redecouper(section: Section) -> list[Section]:
    """Section trop longue : on coupe aux paragraphes, jamais au milieu d'une phrase."""
    paragraphes = [p.strip() for p in re.split(r"\n\s*\n", section.contenu) if p.strip()]
    morceaux: list[Section] = []
    courant: list[str] = []
    for paragraphe in paragraphes:
        candidat = "\n\n".join(courant + [paragraphe])
        if courant and compter_tokens(candidat) > TAILLE_MAX:
            morceaux.append(Section(section.titre, "\n\n".join(courant)))
            courant = [paragraphe]
        else:
            courant.append(paragraphe)
    if courant:
        morceaux.append(Section(section.titre, "\n\n".join(courant)))
    return morceaux or [section]


def _en_texte(section: Section) -> str:
    """Une section rendue en texte, titre inclus — la forme qu'elle prend dans un chunk."""
    return f"{section.titre}\n{section.contenu}".strip() if section.titre else section.contenu.strip()


def decouper_sections(document: DocumentCanonique) -> list[Section]:
    """Applique les trois règles : frontière structurelle, redécoupe, fusion.

    La fusion est un **remplissage glouton jusqu'à TAILLE_MAX**, pas un simple recollage des
    sections sous TAILLE_MIN. La nuance est décisive : s'arrêter à TAILLE_MIN couperait une
    notice de 208 tokens en deux chunks de ~100, alors que rien ne l'impose — le seuil qui
    contraint est le plafond du modèle, pas le plancher. TAILLE_MIN ne sert qu'à garantir
    qu'aucun fragment isolé ne reste sous le seuil de discrimination.
    """
    etendues: list[Section] = []
    for section in document.sections:
        if compter_tokens(section.contenu) > TAILLE_MAX:
            etendues.extend(_redecouper(section))
        else:
            etendues.append(section)

    groupes: list[list[Section]] = []
    for section in etendues:
        if groupes:
            candidat = "\n\n".join(_en_texte(s) for s in groupes[-1] + [section])
            if compter_tokens(candidat) <= TAILLE_MAX:
                groupes[-1].append(section)
                continue
        groupes.append([section])

    # Un dernier groupe resté sous le plancher est recollé au précédent : mieux vaut un
    # chunk un peu long qu'un fragment trop pauvre pour porter un vecteur discriminant.
    if len(groupes) > 1 and compter_tokens("\n\n".join(_en_texte(s) for s in groupes[-1])) < TAILLE_MIN:
        groupes[-2].extend(groupes.pop())

    fusionnees = [
        Section(
            titre=groupe[0].titre if len(groupe) == 1 else "",
            contenu="\n\n".join(_en_texte(s) for s in groupe) if len(groupe) > 1 else groupe[0].contenu,
        )
        for groupe in groupes
    ]
    return fusionnees or [Section("", document.texte)]


def chunker(document: DocumentCanonique, manifeste: dict) -> list[Chunk]:
    groupe = manifeste.get("groupes", {}).get(document.cle_groupe, {})
    est_courante = groupe.get("doc_id_courant") == document.doc_id
    anterieures = [v for v in groupe.get("versions", []) if v != document.version]

    sections = decouper_sections(document)
    # Un seul chunk : le nom de section n'apporte rien, l'en-tête porte déjà tout le contexte.
    section_unique = len(sections) == 1

    chunks: list[Chunk] = []
    for index, section in enumerate(sections):
        titre_section = "" if section_unique else section.titre
        texte_brut = section.contenu.strip()
        if not texte_brut:
            continue
        entete = construire_entete(document, titre_section or None)
        texte = f"{entete}\n{texte_brut}"
        chunks.append(
            Chunk(
                chunk_id=f"{document.doc_id}#{index}",
                doc_id=document.doc_id,
                index=index,
                section=titre_section,
                texte=texte,
                texte_brut=texte_brut,
                n_tokens=compter_tokens(texte),
                metadonnees={
                    "doc_id": document.doc_id,
                    "titre": document.titre,
                    "type_document": document.type_document,
                    "reference": document.reference or "",
                    # Chroma ne filtre pas sur des listes : chaîne + `contains` pour le boost.
                    "references_citees": "|".join(document.references_citees),
                    "version": document.version,
                    "est_version_courante": est_courante,
                    "versions_anterieures": "|".join(anterieures),
                    "date": document.date or "",
                    "section": titre_section,
                    "source_path": document.source_path,
                    "cle_groupe": document.cle_groupe,
                },
            )
        )
    return chunks


def chunker_corpus(documents: list[DocumentCanonique], manifeste: dict) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        if document.qualite.indexable:
            chunks.extend(chunker(document, manifeste))
    return chunks
