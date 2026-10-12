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
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_ENSEIGNES = RACINE / "enseignes"
ENSEIGNE_PAR_DEFAUT = "sorabel"

# Libellés des types de document dans l'en-tête des chunks, ceux d'avant le socle
# multi-enseigne : une enseigne ne déclare dans `[rag.libelles_types]` que ceux qu'elle
# change. Les codes répètent ceux de sorabel_rag/modeles.py, que ce module ne peut pas
# importer ; tests/test_enseigne_libelles_types.py les tient alignés.
LIBELLES_TYPES_PAR_DEFAUT = {
    "fiche_technique": "Fiche technique",
    "notice": "Notice d'installation",
    "note_interne": "Note interne",
    "procedure_sav": "Procédure SAV",
}

# Nom de l'enseigne du processus, posé au premier appel réussi d'`enseigne_active()`.
_ENSEIGNE_FIGEE: str | None = None

# Clés admises dans la table `[front]`. Le front porte les valeurs par défaut (les textes
# Sorabel actuels) : une clé mal orthographiée passerait sinon inaperçue, et une
# démonstration afficherait le texte Sorabel sans la moindre erreur.
CLES_FRONT = (
    "titre_page",
    "nom_produit",
    "mention",
    "resume_corpus",
    "couleur_accent",
    "couleur_fond",
    "references_exemple",
    "questions_exemple",
    "question_sql_exemple",
    "commande_exemple",
    "document_exemple",
)

# Les couleurs finissent dans une feuille de style injectée telle quelle par le front : une
# valeur arbitraire y ouvrirait une règle CSS de plus, ou fermerait la balise `<style>`.
MOTIF_COULEUR = re.compile(r"#[0-9A-Fa-f]{6}")

# Familles de clés de `[front]`, pour valider le type de chaque valeur au chargement.
_CLES_COULEUR = ("couleur_accent", "couleur_fond")
_CLES_LISTE = ("references_exemple", "questions_exemple")
# `mention` est la seule clé qui peut être vide : c'est le défaut Sorabel (aucun bandeau).
_CLES_TEXTE_VIDE_ADMIS = ("mention",)


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
    libelles_types: Mapping[str, str]
    pied_de_page: str
    nom_base: str
    commentaires_sql: Mapping[str, str]
    front: Mapping[str, object]


def _valider_front(table: dict, chemin_toml: Path) -> None:
    """Un type ou un format inutilisable doit échouer ici, en nommant la clé, plutôt que de
    lever une erreur obscure (ou pire, d'afficher un texte vide) au milieu d'une session."""

    def erreur(cle: str, attendu: str) -> ValueError:
        return ValueError(f"{chemin_toml} : [front] {cle} = {table[cle]!r} — attendu : {attendu}")

    for cle, valeur in table.items():
        if cle in _CLES_LISTE:
            if not isinstance(valeur, list) or not valeur:
                raise erreur(cle, "une liste non vide de chaînes")
            if not all(isinstance(element, str) and element.strip() for element in valeur):
                raise erreur(cle, "des chaînes non vides")
            if len(set(valeur)) != len(valeur):
                # Un doublon donnerait deux boutons d'exemple de même clé côté front.
                raise erreur(cle, "des valeurs distinctes")
        elif not isinstance(valeur, str):
            raise erreur(cle, "une chaîne")
        elif cle in _CLES_COULEUR:
            if not MOTIF_COULEUR.fullmatch(valeur):
                raise erreur(cle, "une couleur #RRGGBB")
        elif not valeur.strip() and cle not in _CLES_TEXTE_VIDE_ADMIS:
            raise erreur(cle, "une chaîne non vide")


def _lire_front(brut: dict, chemin_toml: Path) -> Mapping[str, object]:
    """Listes TOML converties en tuples : une enseigne est partagée par cache entre toutes
    les sessions du front, une liste mutable modifiée par l'une le serait pour toutes."""
    table = brut.get("front", {})
    if not isinstance(table, dict):
        raise ValueError(f"{chemin_toml} : [front] doit être une table")
    inconnues = sorted(set(table) - set(CLES_FRONT))
    if inconnues:
        raise ValueError(
            f"{chemin_toml} : clé inconnue dans [front] : {', '.join(inconnues)} — "
            f"admises : {', '.join(CLES_FRONT)}"
        )
    _valider_front(table, chemin_toml)
    return MappingProxyType(
        {cle: tuple(valeur) if isinstance(valeur, list) else valeur for cle, valeur in table.items()}
    )


def _libelles_types(chemin_toml: Path, surcharges: Mapping) -> Mapping[str, str]:
    inconnus = sorted(set(surcharges) - set(LIBELLES_TYPES_PAR_DEFAUT))
    if inconnus:
        # Une faute de frappe ignorée (« notices ») laisserait le libellé par défaut en
        # place sans le moindre signal.
        raise ValueError(
            f"{chemin_toml} : rag.libelles_types, type de document inconnu : "
            f"{', '.join(inconnus)} — types connus : {', '.join(LIBELLES_TYPES_PAR_DEFAUT)}"
        )
    nettoyes = {}
    for type_document, libelle in surcharges.items():
        if not isinstance(libelle, str) or not libelle.strip():
            # Le libellé ouvre l'en-tête de chaque chunk : vide, il effacerait le type de
            # document du texte embeddé comme du prompt, sans aucune erreur.
            raise ValueError(
                f"{chemin_toml} : rag.libelles_types.{type_document} doit être un texte non vide"
            )
        if any(interdit in libelle for interdit in ("\n", "\r", "]")):
            # L'en-tête est `[<libellé> <réf> v<version> — <titre>]` sur sa propre ligne, que
            # le prompt et le découpage relisent : un saut de ligne le casserait en deux, un
            # `]` le refermerait avant la référence.
            raise ValueError(
                f"{chemin_toml} : rag.libelles_types.{type_document} ne peut contenir ni saut "
                "de ligne ni « ] » : il s'insère dans l'en-tête « [libellé REF vX — titre] »"
            )
        # Sans les espaces de bordure : ils se retrouveraient doublés dans l'en-tête.
        nettoyes[type_document] = libelle.strip()
    return MappingProxyType({**LIBELLES_TYPES_PAR_DEFAUT, **nettoyes})


def _verifier_dossiers_regenerables(chemin_toml: Path, chemins: Chemins) -> None:
    """`make reset-donnees` efface `canonique` et `chroma` en entier (rm -rf) : aucun des deux
    ne doit être la racine du dépôt, ni contenir un autre chemin de l'enseigne. Avec
    `chroma = "data"`, il emporterait le corpus et la base SQL de Sorabel ; avec
    `canonique = "gouvernance"`, le code du paquet du même nom."""
    regenerables = ("canonique", "chroma")
    # Tous les autres chemins, pas une liste recopiée : un chemin ajouté à `Chemins` est
    # protégé d'office.
    preserves = [champ.name for champ in fields(Chemins) if champ.name not in regenerables]
    for cle in regenerables:
        # Normalisé : `rm -rf data/corpus/..` efface `data/`. La casse, elle, est déjà
        # ignorée par pathlib sous Windows, comme par son système de fichiers.
        dossier = Path(os.path.normpath(getattr(chemins, cle)))
        if RACINE.is_relative_to(dossier):
            raise ValueError(
                f"{chemin_toml} : chemins.{cle} ({dossier}) est la racine du dépôt ou la "
                "contient — make reset-donnees l'effacerait en entier"
            )
        for preserve in preserves:
            if Path(os.path.normpath(getattr(chemins, preserve))).is_relative_to(dossier):
                raise ValueError(
                    f"{chemin_toml} : chemins.{cle} ({dossier}) est ou contient "
                    f"chemins.{preserve} — make reset-donnees l'effacerait"
                )


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
            libelles_types=_libelles_types(chemin_toml, brut["rag"].get("libelles_types", {})),
            pied_de_page=brut["extraction"]["pied_de_page"],
            nom_base=brut["sql"]["nom_base"],
            commentaires_sql=MappingProxyType(dict(brut["sql"].get("commentaires", {}))),
            front=_lire_front(brut, chemin_toml),
        )
    except KeyError as cle:
        raise ValueError(f"{chemin_toml} : clé manquante {cle}") from None
    _verifier_dossiers_regenerables(chemin_toml, resultat.chemins)
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
    """Enseigne du processus, figée au premier appel réussi.

    Les modules du moteur évaluent leurs constantes (chemins, textes) à l'import, et trois
    d'entre eux appellent `load_dotenv()` à l'import : un `SORABEL_ENSEIGNE` posé dans `.env`
    arriverait après que d'autres modules ont déjà lu la variable. Sans verrou, le processus
    serait moitié une enseigne, moitié l'autre. On refuse donc tout changement de valeur en
    cours de processus. Le nom n'est figé qu'après validation : une enseigne inconnue ne
    verrouille rien."""
    global _ENSEIGNE_FIGEE
    nom = os.environ.get("SORABEL_ENSEIGNE") or ENSEIGNE_PAR_DEFAUT
    if _ENSEIGNE_FIGEE is not None and nom != _ENSEIGNE_FIGEE:
        raise ValueError(
            f"SORABEL_ENSEIGNE a changé en cours de processus : {_ENSEIGNE_FIGEE!r} au premier "
            f"appel, {nom!r} maintenant — un `.env` chargé après le démarrage en est la cause "
            "probable. Exporter la variable avant de lancer le processus."
        )
    resultat = enseigne(nom)
    _ENSEIGNE_FIGEE = nom
    return resultat
