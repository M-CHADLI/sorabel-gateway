"""Garde-fous statiques sur `front/` : cohérence des défauts et absence de chemin direct
vers le pipeline.

`front/app_client.py` exécute Streamlit à l'import : tout ce qui suit lit le source par AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from sorabel_enseigne import CLES_FRONT

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_FRONT = RACINE / "front"
FICHIERS_FRONT = sorted(DOSSIER_FRONT.glob("*.py"))

# Paquets dont l'import donnerait au front un chemin vers les données ou la décision d'accès.
INTERDITS = {"sorabel_rag", "sorabel_sql", "sorabel_llm", "mcp_server"}


def test_defauts_front_couvrent_exactement_les_cles_admises():
    """Une clé admise sans défaut ferait un `KeyError` en pleine session ; un défaut sans clé
    admise serait inatteignable depuis `enseigne.toml`."""
    arbre = ast.parse((DOSSIER_FRONT / "app_client.py").read_text(encoding="utf-8"))
    defauts = next(
        noeud.value
        for noeud in arbre.body
        if isinstance(noeud, ast.Assign)
        and any(isinstance(c, ast.Name) and c.id == "DEFAUTS_FRONT" for c in noeud.targets)
    )
    cles = {ast.literal_eval(cle) for cle in defauts.keys}
    assert cles == set(CLES_FRONT)


def test_front_contient_les_fichiers_attendus():
    # Si le glob ne trouvait rien, le test d'imports ci-dessous passerait pour de mauvaises
    # raisons.
    noms = {fichier.name for fichier in FICHIERS_FRONT}
    assert {"app_client.py", "routage.py", "passerelle.py", "mcp_client.py", "depot.py"} <= noms


@pytest.mark.parametrize("fichier", FICHIERS_FRONT, ids=lambda f: f.name)
def test_aucun_import_du_pipeline_dans_front(fichier):
    """Tout appel de tool passe par `front/routage.py` vers un serveur MCP, qui applique la
    matrice et journalise. Un import de `sorabel_rag` ou `sorabel_sql` en rouvrirait le
    contournement qui a déjà existé."""
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    importes = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            importes.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
            importes.add(noeud.module.split(".")[0])
    assert not importes & INTERDITS, f"{fichier.name} importe {sorted(importes & INTERDITS)}"
