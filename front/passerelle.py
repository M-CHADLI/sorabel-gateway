"""Pont HTTP entre Streamlit et le serveur MCP déployé.

Le front ne fabrique aucun jeton : Identity-Aware Proxy authentifie la personne avant que
la requête n'atteigne Streamlit et dépose une assertion signée dans un en-tête. La
passerelle la recopie telle quelle vers le serveur MCP, qui la valide. Streamlit ne
manipule donc jamais de secret d'identité — c'est ce qui rend ce chemin sûr sans qu'on ait
à écrire de flux OAuth côté interface.
"""

from __future__ import annotations

import asyncio
import json
import os

ENTETE_IAP = "x-goog-iap-jwt-assertion"
URL_MCP = os.environ.get("SORABEL_URL_MCP", "http://localhost:8080/mcp")
DELAI = 300.0


def _entetes() -> dict:
    """Isolé pour être remplaçable en test : `st.context` n'existe qu'en session."""
    import streamlit as st

    return dict(st.context.headers or {})


def assertion_iap() -> str | None:
    entetes = {cle.lower(): valeur for cle, valeur in _entetes().items()}
    return entetes.get(ENTETE_IAP)


def sujet_du_jeton(assertion: str | None) -> str | None:
    """Lit le `sub` sans vérifier la signature — le front n'est pas juge.

    C'est le serveur MCP qui valide et décide ; le front n'a besoin du sujet que pour
    afficher qui est connecté et demander son profil au dépôt. Un jeton forgé ne donnerait
    donc rien de plus qu'un écran mal rempli : aucun appel de tool ne passerait.
    """
    if not assertion:
        return None
    import jwt

    try:
        return jwt.decode(assertion, options={"verify_signature": False}).get("sub")
    except jwt.PyJWTError:
        return None


async def _session(assertion: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    entetes = {"Authorization": f"Bearer {assertion}"}
    async with streamablehttp_client(URL_MCP, headers=entetes) as (lecture, ecriture, _):
        async with ClientSession(lecture, ecriture) as session:
            await session.initialize()
            yield session


async def _appeler_distant(assertion: str, tool: str | None, arguments: dict | None):
    async for session in _session(assertion):
        if tool is None:
            outils = await session.list_tools()
            return sorted(o.name for o in outils.tools)
        resultat = await session.call_tool(tool, arguments or {})
        bloc = resultat.content[0] if resultat.content else None
        if bloc is None or not hasattr(bloc, "text"):
            return {"statut": "erreur", "message": "réponse MCP sans contenu textuel"}
        try:
            return json.loads(bloc.text)
        except json.JSONDecodeError:
            return {"statut": "erreur", "message": bloc.text}


def _executer(coroutine):
    """Exécute l'appel réseau et traduit les pannes de transport en retour normal.

    Une panne (timeout, connexion refusée, DNS en échec) n'est pas un refus d'accès :
    on ne la confond donc jamais avec `{"statut": "non_autorise", ...}`, réservé à
    l'absence d'identité. `{"statut": "erreur", ...}` est déjà la convention du projet
    pour les pannes techniques (voir `front/mcp_client.py`) — on l'applique ici aussi,
    sans jamais recopier l'assertion dans le message renvoyé à l'appelant.
    """
    import httpx

    try:
        return asyncio.run(asyncio.wait_for(coroutine, timeout=DELAI))
    except (asyncio.TimeoutError, TimeoutError):
        return {"statut": "erreur", "message": "Le serveur ne répond pas (délai dépassé)."}
    except httpx.TransportError:
        # Englobe ConnectError (connexion refusée, DNS en échec) et ConnectTimeout :
        # ce sont les exceptions que lève httpx, socle HTTP de streamablehttp_client.
        return {"statut": "erreur", "message": "Impossible de joindre le serveur MCP."}


def lister_tools(assertion: str | None) -> list[str]:
    if not assertion:
        return []
    resultat = _executer(_appeler_distant(assertion, None, None))
    # En cas de panne réseau, `_executer` renvoie un dict `{"statut": "erreur", ...}` au
    # lieu de la liste attendue : liste vide, même comportement que `assertion=None`,
    # pour ne pas casser le contrat de retour (`list[str]`) de cette fonction.
    return resultat if isinstance(resultat, list) else []


def appeler(assertion: str | None, tool: str, arguments: dict) -> dict:
    if not assertion:
        return {
            "statut": "non_autorise",
            "message": "Session non authentifiée : rechargez la page.",
        }
    return _executer(_appeler_distant(assertion, tool, arguments))
