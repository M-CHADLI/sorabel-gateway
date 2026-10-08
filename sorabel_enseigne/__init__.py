"""Une enseigne : un jeu de données et des textes métier, servis par le même moteur.

Seul lecteur de `SORABEL_ENSEIGNE` et de `enseignes/<nom>/enseigne.toml`. Volontairement
sans dépendance vers les autres paquets du projet : `sorabel_rag` et `sorabel_sql`
l'importent sans rien tirer de `gouvernance`.

Le moteur lit `enseigne_active()` — une enseigne par processus, figée au démarrage : un
serveur MCP Kiabi n'a jamais les données Sorabel à portée. Le front mutualisé, qui ne
détient aucune donnée, choisit par session avec `enseigne(nom)`.
"""

from __future__ import annotations

import functools
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_ENSEIGNES = RACINE / "enseignes"
ENSEIGNE_PAR_DEFAUT = "sorabel"


@dataclass(frozen=True)
class Chemins:
    corpus: Path
    canonique: Path
    chroma: Path
    base_sql: Path
    gouvernance: Path
    journal: Path


@dataclass(frozen=True)
class Enseigne:
    nom: str
    libelle: str
    chemins: Chemins
    collection: str
    presentation: str
    pied_de_page: str
    nom_base: str
    commentaires_sql: Mapping[str, str]


def charger_enseigne(chemin_toml: Path) -> Enseigne:
    """Les chemins relatifs du `.toml` sont résolus depuis la racine du dépôt, pas depuis le
    dossier de l'enseigne : c'est ce qui permet à Sorabel de garder `data/` tel quel."""
    chemin_toml = Path(chemin_toml)
    with chemin_toml.open("rb") as fichier:
        brut = tomllib.load(fichier)
    try:
        chemins = brut["chemins"]
        resultat = Enseigne(
            nom=brut["nom"],
            libelle=brut["libelle"],
            chemins=Chemins(**{champ.name: RACINE / chemins[champ.name] for champ in fields(Chemins)}),
            collection=brut["rag"]["collection"],
            presentation=brut["rag"]["presentation"],
            pied_de_page=brut["extraction"]["pied_de_page"],
            nom_base=brut["sql"]["nom_base"],
            commentaires_sql=MappingProxyType(dict(brut["sql"].get("commentaires", {}))),
        )
    except KeyError as cle:
        raise ValueError(f"{chemin_toml} : clé manquante {cle}") from None
    if not resultat.pied_de_page.strip():
        # `ligne.startswith("")` est toujours vrai : un pied de page vide ferait écarter à
        # l'extraction toute la section Identification des fiches, sans aucune erreur.
        raise ValueError(f"{chemin_toml} : extraction.pied_de_page ne peut pas être vide")
    return resultat


def enseignes_disponibles() -> list[str]:
    return sorted(chemin.parent.name for chemin in DOSSIER_ENSEIGNES.glob("*/enseigne.toml"))


@functools.lru_cache(maxsize=None)
def enseigne(nom: str) -> Enseigne:
    disponibles = enseignes_disponibles()
    if nom not in disponibles:
        # Jamais de repli sur Sorabel : une démonstration sur les mauvaises données est
        # pire qu'un échec franc au démarrage.
        raise ValueError(f"enseigne inconnue : {nom!r} — disponibles : {', '.join(disponibles)}")
    resultat = charger_enseigne(DOSSIER_ENSEIGNES / nom / "enseigne.toml")
    if resultat.nom != nom:
        raise ValueError(f"enseignes/{nom}/enseigne.toml déclare nom = {resultat.nom!r}")
    return resultat


def enseigne_active() -> Enseigne:
    return enseigne(os.environ.get("SORABEL_ENSEIGNE") or ENSEIGNE_PAR_DEFAUT)
