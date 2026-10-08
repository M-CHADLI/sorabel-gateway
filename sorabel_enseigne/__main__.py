"""`python -m sorabel_enseigne liste` : les enseignes disponibles.
`python -m sorabel_enseigne make <nom>` : les variables Make d'une enseigne.

Les chemins sont écrits RELATIFS à la racine du dépôt : Make ne sait pas manipuler un
chemin contenant une espace, et la racine en contient (« Sorabel - l'agent augmenté… »).
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import RACINE, enseigne, enseignes_disponibles


def _relatif(chemin: Path) -> str:
    try:
        return chemin.relative_to(RACINE).as_posix()
    except ValueError:
        raise SystemExit(f"{chemin} est hors du dépôt : Make ne peut pas l'utiliser") from None


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
    return "".join(f"{cle} := {_relatif(valeur)}\n" for cle, valeur in variables.items())


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
