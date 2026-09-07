"""Serveur MCP stdio : résout le profil, charge et valide la matrice au démarrage, enregistre
les tools autorisés.

`resoudre_profil` est le SEUL point qui dépend du transport (ici, stdio : variable
d'environnement du sous-processus). Passer en HTTP/OAuth ne toucherait que cette fonction —
tout le reste (matrice, Perimetre, tools) est inchangé d'un transport à l'autre.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre

from .tools import enregistrer_tools

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_GOUVERNANCE_DB = RACINE / "gouvernance" / "gouvernance.db"


def resoudre_profil() -> str:
    profil = os.environ.get("SORABEL_PROFIL")
    if not profil:
        raise RuntimeError(
            "SORABEL_PROFIL doit être défini avant de lancer le serveur "
            "(ex. SORABEL_PROFIL=support python -m mcp_server.serveur)"
        )
    return profil


def construire_serveur(chemin_gouvernance_db: Path = CHEMIN_GOUVERNANCE_DB) -> FastMCP:
    matrice = charger_matrice(chemin_gouvernance_db)
    perimetre = Perimetre(resoudre_profil(), matrice)
    mcp = FastMCP(name="sorabel-data-gateway")
    # enregistrer_tools attend désormais un résolveur, appelé à chaque requête (Task 4) :
    # en stdio le périmètre est déjà fixé au démarrage, donc une fermeture triviale suffit.
    # L'adaptation complète (résolution depuis le jeton HTTP) est du ressort de la Task 5.
    enregistrer_tools(mcp, lambda: perimetre)
    return mcp


if __name__ == "__main__":
    construire_serveur().run(transport="stdio")
