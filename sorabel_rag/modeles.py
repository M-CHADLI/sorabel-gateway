"""Modèles du document canonique.

Un document canonique est une **fonction pure de son fichier source** : rien de ce qu'il
contient ne dépend des autres documents du corpus. Les propriétés qui dépendent de
l'ensemble (quelle version est courante) vivent dans le manifeste, pas ici.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Incrémenter à chaque changement d'une règle d'extraction : invalide tout le cache.
SCHEMA_VERSION = 2

MOTIF_REFERENCE = re.compile(r"REF-\d{4}")

TYPE_FICHE = "fiche_technique"
TYPE_NOTICE = "notice"
TYPE_NOTE = "note_interne"
TYPE_SAV = "procedure_sav"


@dataclass
class Section:
    """Une section structurelle du document, frontière de chunk potentielle."""

    titre: str
    contenu: str

    def n_caracteres(self) -> int:
        return len(self.contenu)


@dataclass
class Qualite:
    """Résultat des contrôles d'extraction. `bloquant` empêche l'indexation."""

    alertes: list[str] = field(default_factory=list)

    @property
    def statut(self) -> str:
        if any(a in ALERTES_BLOQUANTES for a in self.alertes):
            return "bloquant"
        return "alerte" if self.alertes else "ok"

    @property
    def indexable(self) -> bool:
        return self.statut != "bloquant"


ALERTES_BLOQUANTES = {"texte_vide", "reference_absente"}

LIBELLES_ALERTES = {
    "texte_vide": "aucun texte extrait",
    "texte_court": "texte anormalement court pour ce type",
    "aucune_section": "aucune frontière structurelle détectée",
    "reference_absente": "référence attendue mais introuvable",
    "date_absente": "aucune date exploitable",
    "titre_absent": "aucun titre exploitable",
}


@dataclass
class DocumentCanonique:
    """La forme de référence d'un document, quel que soit son format d'origine."""

    doc_id: str
    titre: str
    type_document: str
    version: str
    source_path: str
    hash_source: str
    hash_texte: str
    extrait_le: str
    schema_version: int = SCHEMA_VERSION

    reference: str | None = None
    references_citees: list[str] = field(default_factory=list)
    date: str | None = None
    # Clé de regroupement des versions : `reference` pour les PDF, la famille pour le SAV.
    cle_groupe: str = ""
    # Champs propres à un type (fabricant, catégorie, auteur…), jamais indexés en filtre.
    attributs: dict[str, str] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)
    qualite: Qualite = field(default_factory=Qualite)

    @property
    def texte(self) -> str:
        """Le document entier, sections recollées — base du chunking et de l'affichage."""
        morceaux = []
        for s in self.sections:
            morceaux.append(f"{s.titre}\n{s.contenu}" if s.titre else s.contenu)
        return "\n\n".join(morceaux).strip()

    def en_dict(self) -> dict:
        d = asdict(self)
        d["qualite"] = {"statut": self.qualite.statut, "alertes": self.qualite.alertes}
        return d

    @classmethod
    def depuis_dict(cls, d: dict) -> DocumentCanonique:
        d = dict(d)
        d["sections"] = [Section(**s) for s in d.get("sections", [])]
        d["qualite"] = Qualite(alertes=d.get("qualite", {}).get("alertes", []))
        return cls(**d)


def hacher_fichier(chemin: Path) -> str:
    """SHA-256 des octets du fichier source — pilote le cache d'extraction."""
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def hacher_texte(texte: str, *identifiants: str | None) -> str:
    """SHA-256 de ce qui rend un document distinguable — détecte les vrais doublons.

    Le corps seul ne suffit pas, dans les deux sens :

    - les 80 notices ont un corps **identique** au mot près (le texte d'installation est
      générique) ; seuls le titre et la référence les distinguent. Hacher le corps seul en
      supprimerait 79 ;
    - deux notes d'alerte qualité peuvent avoir le même corps à deux dates différentes : ce
      sont deux incidents distincts, pas un doublon.

    D'où l'inclusion du titre, de la référence et de la date dans l'empreinte.
    """
    parties = [texte, *(i or "" for i in identifiants)]
    normalise = re.sub(r"\s+", " ", "␟".join(parties)).strip().lower()
    return hashlib.sha256(normalise.encode("utf-8")).hexdigest()


def extraire_references(texte: str, sauf: str | None = None) -> list[str]:
    """Toutes les références citées dans un texte, dédoublonnées, ordre d'apparition."""
    vues: dict[str, None] = {}
    for r in MOTIF_REFERENCE.findall(texte):
        if r != sauf:
            vues[r] = None
    return list(vues)


def cle_de_tri_version(version: str) -> tuple[int, ...]:
    """`2.10` est postérieur à `2.9` — un tri alphabétique dirait l'inverse."""
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return (0,)
