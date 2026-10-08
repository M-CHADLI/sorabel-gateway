"""Garde-fou statique : l'image Docker copie tout ce que le code importe.

Le Dockerfile copie une liste fermée de dossiers. Un paquet ajouté au code mais oublié dans
le Dockerfile ne casse aucun test et ne se voit qu'au démarrage du conteneur. On compare donc,
sans jamais appeler docker, les imports réels aux `COPY` de chaque étape.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PAQUETS = {
    dossier.name
    for dossier in RACINE.iterdir()
    if dossier.is_dir() and (dossier / "__init__.py").exists() and dossier.name != "tests"
}


def _imports_du_projet(fichier: Path) -> set[str]:
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    noms: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
            noms.add(noeud.module.split(".")[0])
    return noms & PAQUETS


def _fermeture(depart: set[str]) -> set[str]:
    """Paquets atteignables depuis `depart` : on scanne tous les `.py` de chaque paquet."""
    vus: set[str] = set()
    a_voir = set(depart)
    while a_voir:
        paquet = a_voir.pop()
        if paquet in vus:
            continue
        vus.add(paquet)
        for fichier in (RACINE / paquet).rglob("*.py"):
            a_voir |= _imports_du_projet(fichier) - vus
    return vus


def _etapes() -> list[list[str]]:
    """Sources des `COPY` sans `--from`, une liste par étape (blocs séparés par `FROM`)."""
    etapes: list[list[str]] = []
    for ligne in (RACINE / "Dockerfile").read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if re.match(r"FROM\s", ligne, re.IGNORECASE):
            etapes.append([])
        elif re.match(r"COPY\s", ligne, re.IGNORECASE):
            arguments = ligne.split()[1:]
            if any(a.startswith("--from") for a in arguments):
                continue
            arguments = [a for a in arguments if not a.startswith("--")]
            etapes[-1].extend(arguments[:-1])
    return etapes


def _premiers_composants(sources: list[str]) -> set[str]:
    return {source.strip("/").split("/")[0] for source in sources}


def test_etape_finale_copie_la_fermeture_de_mcp_server_et_front():
    attendus = _fermeture({"mcp_server", "front"})
    copies = _premiers_composants(_etapes()[-1])
    assert attendus - copies == set(), f"paquets non copies dans l'image servie : {attendus - copies}"


def test_etape_index_copie_la_fermeture_des_scripts_de_construction():
    departs: set[str] = set()
    for script in ("seed_gouvernance.py", "ingerer.py", "indexer.py"):
        departs |= _imports_du_projet(RACINE / "scripts" / script)
    attendus = _fermeture(departs)
    copies = _premiers_composants(_etapes()[0])
    assert attendus - copies == set(), f"paquets non copies a l'etape index : {attendus - copies}"


def test_toml_de_l_enseigne_copie_avec_le_paquet_sans_jamais_copier_enseignes_entier():
    for sources in _etapes():
        normalisees = {source.strip("/") for source in sources}
        # Le corpus d'une future enseigne ne doit jamais entrer dans l'image.
        assert "enseignes" not in normalisees
        if "sorabel_enseigne" in _premiers_composants(sources):
            assert "enseignes/sorabel/enseigne.toml" in normalisees
