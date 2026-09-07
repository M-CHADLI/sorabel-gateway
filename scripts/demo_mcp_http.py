"""Serveur MCP HTTP de démonstration — SANS authentification.

Objectif unique : tester la Sorabel Data Gateway depuis un playground MCP en ligne
(mcpplaygroundonline ou équivalent) en quelques minutes, avant que l'authentification OAuth
réelle (Google Identity Platform, tâches 9-11 de gcp-vitrine) ne soit provisionnée sur GCP.

Ce script n'est PAS le serveur de production. `mcp_server/serveur.py` reste le seul point
d'entrée déployé : il exige un jeton OAuth valide, résout le profil depuis un dépôt
d'identités, et journalise chaque appel. Ici, le profil est fixé une fois pour toutes au
lancement, en clair, sans aucune vérification d'identité — exactement ce que le chantier GCP
existe pour supprimer. À n'exposer que le temps d'une démonstration, jamais en production.

Usage :
    python scripts/demo_mcp_http.py --profil admin
    ngrok http 8080   # dans un second terminal — donne l'URL publique à coller
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre
from mcp_server.tools import enregistrer_tools

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_GOUVERNANCE_DB = RACINE / "gouvernance" / "gouvernance.db"


def construire_serveur_demo(profil: str) -> FastMCP:
    matrice = charger_matrice(CHEMIN_GOUVERNANCE_DB)
    perimetre_fige = Perimetre(profil, matrice)

    mcp = FastMCP(
        name="sorabel-data-gateway-demo",
        instructions=(
            f"DÉMO SANS AUTHENTIFICATION — profil figé sur {profil!r} au lancement. "
            "Ne reflète pas le serveur de production, qui exige un jeton OAuth."
        ),
        host="0.0.0.0",
        port=8080,
    )
    enregistrer_tools(mcp, lambda: perimetre_fige)
    return mcp


if __name__ == "__main__":
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--profil", required=True, choices=["support", "commercial", "dev", "admin"]
    )
    arguments = analyseur.parse_args()

    print(f"\n⚠️  Démo SANS authentification — profil figé : {arguments.profil}")
    print("    Serveur MCP sur http://0.0.0.0:8080/mcp")
    print("    Dans un autre terminal : ngrok http 8080\n")

    construire_serveur_demo(arguments.profil).run(transport="streamable-http")
