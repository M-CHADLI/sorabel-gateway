"""La recette `front:` du Makefile : poste local sans IAP, jamais exposé au réseau.

Lu en texte, sans lancer `make` : la recette est la première défense, celle de
`front/app_client.py` (qui refuse de démarrer si `server.address` n'est pas la boucle locale)
est la seconde.
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
MAKEFILE = (RACINE / "Makefile").read_text(encoding="utf-8")


def _recette_front() -> str:
    lignes = MAKEFILE.splitlines()
    debut = next(i for i, ligne in enumerate(lignes) if re.match(r"front:", ligne))
    recette = []
    for ligne in lignes[debut + 1 :]:
        if not ligne.startswith("\t"):
            break
        recette.append(ligne)
    return "\n".join(recette)


def test_la_recette_front_ecoute_sur_la_boucle_locale():
    recette = _recette_front()
    assert "--server.address=127.0.0.1" in recette
    assert "SORABEL_FRONT_LOCAL=1" in recette
    assert "streamlit run front/app_client.py" in recette


def test_la_recette_front_construit_les_donnees_de_chaque_enseigne_presente():
    recette = _recette_front()
    assert "$(ENSEIGNES_PRESENTES)" in recette
    assert "donnees" in recette
    assert re.search(r"^ENSEIGNES_PRESENTES\s*:?=.*enseignes/\*/enseigne\.toml", MAKEFILE, re.M)


def test_l_aide_de_front_le_dit():
    ligne = next(l for l in MAKEFILE.splitlines() if re.match(r"front:.*##", l))
    assert "127.0.0.1" in ligne
    assert "enseigne" in ligne
