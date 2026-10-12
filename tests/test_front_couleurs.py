"""Palette de l'enseigne : le défaut reproduit la feuille de style Sorabel à l'octet.

La feuille de style vit dans `front/app_client.py`, qu'on ne peut pas importer sans lancer
Streamlit : `STYLE` est lu par AST. Le point de comparaison est la feuille du tag
`sorabel-v1`, lue dans git — pas une copie dans les tests, qui dériverait en silence.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from front import couleurs
from sorabel_enseigne import MOTIF_COULEUR

RACINE = Path(__file__).resolve().parent.parent
APP_CLIENT = RACINE / "front" / "app_client.py"


def _affectation(source: str, nom: str):
    for noeud in ast.parse(source).body:
        if isinstance(noeud, ast.Assign) and any(
            isinstance(cible, ast.Name) and cible.id == nom for cible in noeud.targets
        ):
            return ast.literal_eval(noeud.value)
    raise AssertionError(f"{nom} introuvable")


@pytest.fixture(scope="module")
def style() -> str:
    return _affectation(APP_CLIENT.read_text(encoding="utf-8"), "STYLE")


@pytest.fixture(scope="module")
def defauts() -> dict:
    return _affectation(APP_CLIENT.read_text(encoding="utf-8"), "DEFAUTS_FRONT")


@pytest.fixture(scope="module")
def style_v1() -> str:
    try:
        resultat = subprocess.run(
            ["git", "show", "sorabel-v1:front/app_client.py"],
            cwd=RACINE,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("tag sorabel-v1 indisponible")
    return _affectation(resultat.stdout.decode("utf-8"), "STYLE")


def test_le_defaut_reproduit_la_feuille_sorabel_v1_a_l_octet(style, style_v1, defauts):
    habille = couleurs.habiller(style, defauts["couleur_accent"], defauts["couleur_fond"])
    assert habille == style_v1


def test_la_feuille_ne_garde_aucune_teinte_sorabel_en_dur(style):
    """Chaque teinte dérivée de l'accent passe par un marqueur : un littéral oublié
    laisserait l'accent Sorabel dans l'habillage d'une autre enseigne."""
    for litteral in ("#2563EB", "#1D4ED8", "#EFF4FF", "#2F6BEE", "#DBE6FF", "37,99,235"):
        assert litteral not in style, litteral
    assert "#0D1526" not in style


def test_tous_les_marqueurs_servent_et_aucun_ne_survit(style):
    for marqueur in couleurs.MARQUEURS:
        assert marqueur in style, marqueur
    habille = couleurs.habiller(style, "#1E5BC6", "#0B2E6B")
    assert not any(marqueur in habille for marqueur in couleurs.MARQUEURS)


def test_une_autre_enseigne_est_habillee_de_bout_en_bout(style):
    habille = couleurs.habiller(style, "#1E5BC6", "#0B2E6B")
    assert "--accent:       #1E5BC6;" in habille
    assert "linear-gradient(185deg, #0B2E6B 0%" in habille
    # Ombres et anneau de focus portent l'accent de l'enseigne (30, 91, 198)...
    assert habille.count("rgba(30,91,198,") == 4
    # ... et plus rien ne rappelle le bleu Sorabel.
    for litteral in ("#2563EB", "#1D4ED8", "#EFF4FF", "#2F6BEE", "#DBE6FF", "37,99,235"):
        assert litteral not in habille, litteral


def test_la_palette_derivee_est_toujours_en_hex_valide():
    for accent in ("#000000", "#FFFFFF", "#1E5BC6", "#E4002B", "#7FFF00"):
        palette = couleurs.palette(accent, "#0B2E6B")
        for marqueur in ("__ACCENT_FONCE__", "__ACCENT_VOILE__", "__ACCENT_BORD__",
                         "__ACCENT_CLAIR__"):
            assert MOTIF_COULEUR.fullmatch(palette[marqueur]), (accent, marqueur)
