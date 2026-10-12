"""`python -m sorabel_enseigne liste` : les enseignes disponibles.
`python -m sorabel_enseigne make <nom>` : les variables Make d'une enseigne.

Les chemins sont écrits RELATIFS à la racine du dépôt : Make ne sait pas manipuler un
chemin contenant une espace, et la racine en contient (« Sorabel - l'agent augmenté… »).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import RACINE, enseigne, enseignes_disponibles


def _relatif(chemin: Path) -> str:
    # Normalisé AVANT le relatif : `relative_to` est lexical, et `data/../../voisin` « est
    # dans » le dépôt tout en désignant son voisin. Make recevrait un chemin avec des `..`
    # que `rm -rf` suit sans broncher.
    normalise = Path(os.path.normpath(chemin))
    try:
        return normalise.relative_to(RACINE).as_posix()
    except ValueError:
        raise SystemExit(f"{chemin} est hors du dépôt : Make ne peut pas l'utiliser") from None


def _dossier_regenerable_autorise(relatif: str) -> bool:
    """`data/<…>` ou `enseignes/<nom>/data/<…>`, jamais ces racines elles-mêmes : `rm -rf data`
    emporterait le corpus et les bases d'une enseigne."""
    parties = Path(relatif).parts
    if parties[:1] == ("data",):
        return len(parties) >= 2
    if parties[:1] == ("enseignes",) and parties[2:3] == ("data",):
        return len(parties) >= 4
    return False


def _verifier_cibles_de_reset(chemins) -> None:
    """`make reset-donnees` fait `rm -rf` sur le dossier du manifeste, celui de l'index et la
    base de gouvernance. La validation de `charger_enseigne` est une liste noire (elle ne
    connaît que les chemins de l'enseigne) : `canonique = ".git"` ou `"sorabel_rag"` la passe.
    Ici, côté Make, on exige une liste blanche. `charger_enseigne` reste tolérant : ses tests
    écrivent des enseignes dans des dossiers temporaires, sans rapport avec Make."""
    cibles = {"canonique": chemins.canonique, "chroma": chemins.chroma}
    for cle, dossier in cibles.items():
        relatif = _relatif(dossier)
        if not _dossier_regenerable_autorise(relatif):
            raise SystemExit(
                f"chemins.{cle} = {relatif!r} : make reset-donnees l'effacerait en entier ; "
                "un dossier régénérable doit être sous data/ ou enseignes/<nom>/data/"
            )
        # Sous data/, donc autorisé, mais à l'intérieur du corpus : `rm -rf` le mutilerait.
        # `charger_enseigne` ne voit que le sens inverse (un dossier qui contient le corpus).
        if Path(os.path.normpath(dossier)).is_relative_to(Path(os.path.normpath(chemins.corpus))):
            raise SystemExit(
                f"chemins.{cle} = {relatif!r} est dans chemins.corpus : "
                "make reset-donnees effacerait une partie du corpus"
            )
    # Le chemin de gouvernance est lui aussi sous `rm -rf` : un dossier le ferait emporter
    # tout ce qu'il contient.
    gouvernance = Path(os.path.normpath(chemins.gouvernance))
    for cle in ("corpus", "canonique", "chroma", "base_sql", "journal"):
        if Path(os.path.normpath(getattr(chemins, cle))).is_relative_to(gouvernance):
            raise SystemExit(
                f"chemins.gouvernance ({_relatif(gouvernance)}) est ou contient chemins.{cle} : "
                "make reset-donnees l'effacerait"
            )


def variables_make(nom: str) -> str:
    """Les noms `_manifeste.json` et `bm25.pkl` répètent ceux de sorabel_rag : ce module ne
    peut pas l'importer sans tirer tout le moteur dans chaque appel de Make."""
    chemins = enseigne(nom).chemins
    variables = {
        "GOUVERNANCE_DB": chemins.gouvernance,
        "MANIFESTE": chemins.canonique / "_manifeste.json",
        "INDEX": chemins.chroma / "bm25.pkl",
        "CORPUS_DIR": chemins.corpus,
        "JOURNAL": chemins.journal,
    }
    # Les relatifs d'abord : un chemin hors du dépôt garde son message « hors du dépôt ».
    ecrit = "".join(f"{cle} := {_relatif(valeur)}\n" for cle, valeur in variables.items())
    _verifier_cibles_de_reset(chemins)
    return ecrit


def main(arguments: list[str]) -> int:
    if arguments == ["liste"]:
        print("\n".join(enseignes_disponibles()))
        return 0
    if len(arguments) == 2 and arguments[0] == "make":
        print(variables_make(arguments[1]), end="")
        return 0
    print("usage : python -m sorabel_enseigne liste | make <enseigne>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    # Sous Windows, stdout en mode texte traduit \n en \r\n : redirigé vers .make/<nom>.mk,
    # chaque chemin finirait par \r et Make ne trouverait plus aucun fichier.
    sys.stdout.reconfigure(newline="\n")
    sys.exit(main(sys.argv[1:]))
