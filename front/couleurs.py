"""Palette dérivée de la couleur d'accent d'une enseigne.

Une enseigne ne déclare que `couleur_accent` et `couleur_fond` ; les teintes voisines de la
feuille de style (accent foncé, voile, bordure, début de dégradé, ombres, anneau de focus)
en découlent. Sans cette dérivation, un accent Kiabi laisserait des ombres, un bouton et un
focus encore bleus Sorabel : l'enseigne ne serait habillée qu'à moitié.

Les coefficients sont calibrés pour que l'accent Sorabel (`#2563EB`) redonne, à l'octet, les
valeurs d'origine de la feuille de style — la production ne doit pas bouger d'un pixel.
`tests/test_front_couleurs.py` le garde contre la feuille du tag `sorabel-v1`.

Module pur (stdlib seulement) : il s'importe en test sans lancer Streamlit.
"""

from __future__ import annotations

import colorsys

# Marqueurs de la feuille de style, remplacés par `habiller`. Des marqueurs plutôt qu'un
# `str.format` : chaque accolade CSS devrait sinon être doublée.
MARQUEURS = (
    "__ACCENT__",
    "__ACCENT_FONCE__",
    "__ACCENT_VOILE__",
    "__ACCENT_BORD__",
    "__ACCENT_CLAIR__",
    "__ACCENT_RVB__",
    "__FOND__",
)


def _rvb(couleur: str) -> tuple[int, int, int]:
    return tuple(int(couleur[i : i + 2], 16) for i in (1, 3, 5))


def _hex(rvb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rvb


def _teinte(couleur: str, *, decalage_teinte: float = 0.0, luminosite: float = 1.0,
            saturation: float = 1.0, vers_blanc: float = 0.0) -> str:
    """Variante de `couleur` en HLS : teinte décalée (degrés), luminosité et saturation
    multipliées, puis éclaircie de `vers_blanc` (0 = inchangée, 1 = blanc).

    La teinte et la saturation sont conservées par défaut : un voile ou une ombre doit rester
    de la même famille que l'accent, c'est ce qui les rend lisibles comme « son » halo.
    """
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in _rvb(couleur)))
    h = (h + decalage_teinte / 360) % 1
    l = min(1.0, max(0.0, l * luminosite))
    l = l + (1 - l) * vers_blanc
    s = min(1.0, max(0.0, s * saturation))
    return _hex(tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s)))


def palette(accent: str, fond: str) -> dict[str, str]:
    """Valeur de chaque marqueur de `MARQUEURS` pour un accent et un fond donnés."""
    rouge, vert, bleu = _rvb(accent)
    return {
        "__ACCENT__": accent,
        # Plus sombre et très légèrement décalé vers l'indigo : à teinte constante, un bleu
        # assombri tire vers le terne.
        "__ACCENT_FONCE__": _teinte(accent, decalage_teinte=3, luminosite=0.9, saturation=0.92),
        # Fonds de pastille et de source : l'accent presque blanc, légèrement saturé pour
        # ne pas virer au gris.
        "__ACCENT_VOILE__": _teinte(accent, vers_blanc=0.93, saturation=1.15),
        "__ACCENT_BORD__": _teinte(accent, vers_blanc=0.85, saturation=1.2),
        # Haut du dégradé des boutons : à peine plus clair que l'accent, pour le relief.
        "__ACCENT_CLAIR__": _teinte(accent, vers_blanc=0.055, saturation=1.02),
        # Composantes pour `rgba(...)` : les ombres et l'anneau de focus portent l'accent.
        "__ACCENT_RVB__": f"{rouge},{vert},{bleu}",
        "__FOND__": fond,
    }


def habiller(style: str, accent: str, fond: str) -> str:
    """`style` aux couleurs de l'enseigne : chaque marqueur remplacé par sa valeur."""
    for marqueur, valeur in palette(accent, fond).items():
        style = style.replace(marqueur, valeur)
    return style
