"""Garde-fou statique : l'image Docker ne contient que la configuration de Sorabel.

Une enseigne de démonstration (corpus, base, index) ne doit jamais entrer dans l'image de
production : seul `enseignes/sorabel/enseigne.toml` y est copié, jamais le dossier
`enseignes/` ni un `COPY . .` qui l'embarquerait. Aucun appel à docker.
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
AUTORISE = "enseignes/sorabel/enseigne.toml"
# Sources qui embarqueraient `enseignes/` par ricochet.
TROP_LARGES = {".", "./", "*", "./*", "enseignes", "enseignes/"}


def _sources_par_etape() -> list[list[str]]:
    """Sources de chaque COPY/ADD, une liste par étape (blocs séparés par `FROM`), y compris
    celles d'un `--from` : copier `/app/enseignes/` depuis l'étape précédente vaudrait autant."""
    etapes: list[list[str]] = []
    texte = (RACINE / "Dockerfile").read_text(encoding="utf-8")
    # Les continuations de ligne (`\`) font une seule instruction.
    for ligne in texte.replace("\\\n", " ").splitlines():
        ligne = ligne.strip()
        if re.match(r"FROM\s", ligne, re.IGNORECASE):
            etapes.append([])
        elif re.match(r"(COPY|ADD)\s", ligne, re.IGNORECASE):
            arguments = [a for a in ligne.split()[1:] if not a.startswith("--")]
            etapes[-1].extend(arguments[:-1])
    return etapes


def _normalise(source: str) -> str:
    return source.removeprefix("./").removeprefix("/app/")


def test_le_dockerfile_a_des_etapes_et_des_copy():
    etapes = _sources_par_etape()
    assert len(etapes) >= 2
    assert all(etapes)


def test_seul_le_toml_de_sorabel_est_copie_depuis_enseignes():
    for numero, sources in enumerate(_sources_par_etape(), start=1):
        for source in sources:
            normalisee = _normalise(source)
            if normalisee.startswith("enseignes/"):
                assert normalisee == AUTORISE, (
                    f"étape {numero} : COPY de {source!r} — seul {AUTORISE} peut entrer dans "
                    "l'image (le corpus d'une autre enseigne n'a rien à y faire)"
                )


def test_aucune_source_trop_large_ne_ramene_enseignes():
    for numero, sources in enumerate(_sources_par_etape(), start=1):
        for source in sources:
            assert _normalise(source) not in TROP_LARGES, (
                f"étape {numero} : COPY de {source!r} embarquerait enseignes/"
            )


def test_le_toml_de_sorabel_est_bien_copie_dans_chaque_etape():
    """Sans lui, `sorabel_enseigne` lève au démarrage : le garde-fou ne doit pas pouvoir
    être satisfait en ne copiant plus rien."""
    for sources in _sources_par_etape():
        assert AUTORISE in [_normalise(s) for s in sources]
