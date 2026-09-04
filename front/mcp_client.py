"""Pont entre Streamlit et le serveur MCP : une session stdio persistante par profil.

Streamlit ré-exécute le script à chaque interaction, donc une session ouverte dans le fil
d'exécution du script ne survivrait pas au clic suivant. La session est donc tenue par un
thread dédié qui possède sa propre boucle asyncio : le sous-processus serveur reste vivant
entre deux appels, et les modèles d'embedding et de reranking ne sont chargés qu'une fois.

Sans ça, chaque question rechargeait intégralement le pipeline RAG (plusieurs dizaines de
secondes par appel) — c'était la cause de l'apparente « boucle infinie » du front.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from contextlib import AsyncExitStack
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

# Le premier appel paie le démarrage du serveur et le chargement des modèles RAG ; les
# suivants tapent dans un processus déjà chaud.
DELAI_DEMARRAGE = 300.0
DELAI_APPEL = 300.0


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


class _SessionPersistante:
    """Une session MCP maintenue ouverte dans un thread à part.

    Les contextes asynchrones (`stdio_client`, `ClientSession`) doivent vivre dans la boucle
    qui les a créés : on les ouvre via une `AsyncExitStack` conservée en attribut, plutôt
    qu'avec `async with`, pour qu'ils survivent à la coroutine d'ouverture.
    """

    def __init__(self, profil: str):
        self.profil = profil
        self._boucle = asyncio.new_event_loop()
        self._pile: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._outils: list[str] = []
        threading.Thread(target=self._tourner, daemon=True, name=f"mcp-{profil}").start()
        self._soumettre(self._ouvrir(), DELAI_DEMARRAGE)

    def _tourner(self) -> None:
        asyncio.set_event_loop(self._boucle)
        self._boucle.run_forever()

    def _soumettre(self, coroutine, delai: float):
        return asyncio.run_coroutine_threadsafe(coroutine, self._boucle).result(timeout=delai)

    async def _ouvrir(self) -> None:
        self._pile = AsyncExitStack()
        lecture, ecriture = await self._pile.enter_async_context(
            stdio_client(_parametres(self.profil))
        )
        self._session = await self._pile.enter_async_context(ClientSession(lecture, ecriture))
        await self._session.initialize()
        outils = await self._session.list_tools()
        self._outils = sorted(t.name for t in outils.tools)

    async def _appeler(self, tool: str, arguments: dict) -> dict:
        assert self._session is not None
        resultat = await self._session.call_tool(tool, arguments)
        bloc = resultat.content[0] if resultat.content else None
        if bloc is None or not hasattr(bloc, "text"):
            return {"statut": "erreur", "message": "réponse MCP sans contenu textuel"}
        try:
            return json.loads(bloc.text)
        except json.JSONDecodeError:
            # Une exception levée dans un tool remonte en texte brut, pas en JSON : on la
            # présente comme un statut d'erreur exploitable plutôt que de casser l'appelant.
            return {"statut": "erreur", "message": bloc.text}

    def outils(self) -> list[str]:
        return list(self._outils)

    def appeler(self, tool: str, arguments: dict) -> dict:
        if tool not in self._outils:
            return {
                "statut": "non_autorise",
                "message": f"le profil {self.profil!r} n'a pas accès au tool {tool!r}",
            }
        return self._soumettre(self._appeler(tool, arguments), DELAI_APPEL)


_sessions: dict[str, _SessionPersistante] = {}
_verrou = threading.Lock()


def _session(profil: str) -> _SessionPersistante:
    with _verrou:
        if profil not in _sessions:
            _sessions[profil] = _SessionPersistante(profil)
        return _sessions[profil]


def lister_tools(profil: str) -> list[str]:
    return _session(profil).outils()


def appeler(profil: str, tool: str, arguments: dict) -> dict:
    return _session(profil).appeler(tool, arguments)
