"""Pont entre Streamlit et le serveur MCP : une connexion stdio de courte durée par appel.

Streamlit ré-exécute le script à chaque interaction : pas de session MCP persistante possible
entre deux clics. Le coût (rechargement des modèles d'embedding à chaque appel RAG) est
accepté pour un front de test — cf. Global Constraints du plan.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Streamlit exécute le script utilisateur dans un thread secondaire. Sur Windows, un
# event loop asyncio créé hors du thread principal peut hériter d'une politique
# SelectorEventLoop (posée par une dépendance tierce, ex. Tornado) qui ne sait pas créer
# de sous-processus (`asyncio.subprocess` requiert ProactorEventLoop sous Windows) — le
# lancement de `python -m mcp_server.serveur` échoue alors silencieusement côté client,
# qui voit juste la connexion stdio se refermer aussitôt.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

RACINE = Path(__file__).resolve().parent.parent


def _parametres(profil: str) -> StdioServerParameters:
    # On hérite de l'environnement au lieu de le remplacer : un env réduit au seul
    # SORABEL_PROFIL prive le sous-processus de SYSTEMROOT/PATH, et Python ne peut alors
    # plus initialiser Winsock sous Windows (`OSError: [WinError 10106]` à l'import de
    # `_overlapped`) — le serveur meurt avant d'avoir répondu au handshake MCP.
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.serveur"],
        env={**os.environ, "SORABEL_PROFIL": profil},
        cwd=str(RACINE),
    )


async def _lister_async(profil: str) -> list[str]:
    async with stdio_client(_parametres(profil)) as (lecture, ecriture):
        async with ClientSession(lecture, ecriture) as session:
            await session.initialize()
            outils = await session.list_tools()
            return sorted(t.name for t in outils.tools)


async def _appeler_async(profil: str, tool: str, arguments: dict) -> dict:
    async with stdio_client(_parametres(profil)) as (lecture, ecriture):
        async with ClientSession(lecture, ecriture) as session:
            await session.initialize()
            outils = await session.list_tools()
            noms = {t.name for t in outils.tools}
            if tool not in noms:
                return {
                    "statut": "non_autorise",
                    "message": f"le profil {profil!r} n'a pas accès au tool {tool!r}",
                }
            resultat = await session.call_tool(tool, arguments)
            bloc = resultat.content[0] if resultat.content else None
            if bloc is None or not hasattr(bloc, "text"):
                return {"erreur": "réponse MCP sans contenu textuel"}
            return json.loads(bloc.text)


def lister_tools(profil: str) -> list[str]:
    return asyncio.run(_lister_async(profil))


def appeler(profil: str, tool: str, arguments: dict) -> dict:
    return asyncio.run(_appeler_async(profil, tool, arguments))
