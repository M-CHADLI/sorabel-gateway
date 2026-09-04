"""Client MCP unique : `--profil {support,commercial,dev,admin}`.

Même code, même serveur, même séquence d'appels — seul le profil change. C'est ce qui rend
le contraste entre profils démontrable : avec quatre clients différents, on ne pourrait pas
écarter l'hypothèse que la différence de réponse vient du client plutôt que de la matrice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RACINE = Path(__file__).resolve().parent.parent


async def _appeler(session: ClientSession, tool: str, arguments: dict) -> dict:
    resultat = await session.call_tool(tool, arguments)
    bloc = resultat.content[0] if resultat.content else None
    if bloc is None or not hasattr(bloc, "text"):
        return {"erreur": "réponse MCP sans contenu textuel"}
    return json.loads(bloc.text)


async def demo(profil: str) -> None:
    parametres = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.serveur"],
        # Hériter de l'environnement, ne pas le remplacer : sans SYSTEMROOT/PATH, le
        # sous-processus ne peut pas initialiser Winsock sous Windows (WinError 10106).
        env={**os.environ, "SORABEL_PROFIL": profil},
        cwd=str(RACINE),
    )
    async with stdio_client(parametres) as (lecture, ecriture):
        async with ClientSession(lecture, ecriture) as session:
            await session.initialize()
            outils = await session.list_tools()
            noms_outils = sorted(t.name for t in outils.tools)
            print(f"\n=== profil : {profil} — tools disponibles : {noms_outils} ===")

            print(f"\n[{profil}] search_docs('politique tarifaire')")
            resultat = await _appeler(session, "search_docs", {"requete": "politique tarifaire"})
            titres = [r["titre"] for r in resultat.get("resultats", [])]
            print(f"  titres trouvés : {titres}")

            if "ask_database" in noms_outils:
                print(f"\n[{profil}] ask_database('quelle est la marge sur REF-1024 ?')")
                print(" ", await _appeler(session, "ask_database", {"question": "quelle est la marge sur REF-1024 ?"}))

                print(f"\n[{profil}] ask_database('combien de commandes en avril ?')")
                print(" ", await _appeler(session, "ask_database", {"question": "combien de commandes en avril ?"}))

                print(f"\n[{profil}] ask_database('supprime les commandes de test')")
                print(" ", await _appeler(session, "ask_database", {"question": "supprime les commandes de test"}))

            print(f"\n[{profil}] get_schema()")
            schema = await _appeler(session, "get_schema", {})
            print("  contient marge_pct :", "marge_pct" in schema.get("schema", ""))


if __name__ == "__main__":
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--profil", required=True, choices=["support", "commercial", "dev", "admin"]
    )
    arguments = analyseur.parse_args()
    asyncio.run(demo(arguments.profil))
