"""Garde-fou statique : ce que l'image Docker embarque du dossier `enseignes/`.

L'image est commune à toutes les enseignes servies (décision de déploiement : `kiabi-mcp` est
servi par la même image que `sorabel-mcp`). Ce qui entre dans l'image servie est donc limité à
la configuration, la base SQL et l'index de chaque enseigne — JAMAIS un corpus (il n'existe
que dans l'étape de construction de l'index), ni `enseignes/` en bloc, ni un `COPY . .` qui
l'embarquerait. Aucun appel à docker.
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
AUTORISE = "enseignes/sorabel/enseigne.toml"
# Configuration, base SQL et index d'une enseigne : ce que le serveur lit à l'exécution.
SERVI = re.compile(
    r"^enseignes/[a-z0-9_-]+/(enseigne\.toml|data/[a-z0-9_-]+\.db|data/(canonique|chroma)/)$"
)
# Le corpus n'entre que dans l'étape qui construit l'index.
CORPUS = re.compile(r"^enseignes/[a-z0-9_-]+/data/corpus(/.*)?$")
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


def test_l_etape_servie_ne_copie_que_config_base_et_index_des_enseignes():
    derniere = _sources_par_etape()[-1]
    for source in derniere:
        normalisee = _normalise(source)
        if normalisee.startswith("enseignes/"):
            assert SERVI.match(normalisee), (
                f"étape servie : COPY de {source!r} — seuls la configuration, la base SQL et "
                "l'index d'une enseigne peuvent entrer dans l'image servie, jamais son corpus"
            )
            assert not CORPUS.match(normalisee)


def test_aucune_etape_ne_copie_le_corpus_hors_de_celle_qui_construit_l_index():
    etapes = _sources_par_etape()
    for numero, sources in enumerate(etapes[1:], start=2):
        for source in sources:
            assert not CORPUS.match(_normalise(source)), (
                f"étape {numero} : COPY du corpus {source!r} dans l'image servie"
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
