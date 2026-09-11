"""Client MCP authentifié par un vrai flux OAuth Google — preuve du Resource Server.

Ni `mcp_client.py` (stdio, aucune authentification) ni `demo_mcp_http.py` (HTTP, profil figé
sans authentification) ne testent la voie que ce script exerce : un client MCP tiers, distinct
d'Identity-Aware Proxy et du front, qui s'authentifie lui-même auprès de Google et présente le
jeton à `sorabel-mcp` déployé. `mcp_server/authentification.py::VerificateurJeton` doit
l'accepter exactement comme il accepterait un vrai client MCP (Claude Desktop, un agent tiers).

Piège rencontré en vitrine (2026-09-09) : Google délivre à l'échange de code deux jetons
distincts — un `access_token` opaque (pensé pour appeler les API Google, illisible), et un
`id_token` (un vrai JWT signé, avec `iss`/`aud`/`sub`). Un client OAuth générique (MCP Inspector
compris) envoie l'`access_token` par convention ; `VerificateurJeton` décode localement un JWT,
donc rejette l'opaque sans même atteindre sa propre journalisation. Ce script envoie
explicitement l'`id_token` comme jeton porteur, pour isoler : le serveur valide-t-il
correctement un vrai jeton, indépendamment de ce qu'un client tiers choisit d'envoyer ?

Usage :
    python scripts/mcp_client_oauth.py \
        --url https://sorabel-mcp-<PROJECT_NUMBER>.<region>.run.app/mcp \
        --client-id <ID>.apps.googleusercontent.com \
        --client-secret <SECRET>

Le secret n'est jamais écrit sur disque ni journalisé : passé en argument (ou variable
d'environnement `SORABEL_OAUTH_CLIENT_SECRET`), lu une fois, gardé en mémoire.
"""

from __future__ import annotations

import argparse
import asyncio
import http.server
import os
import urllib.parse
import webbrowser

import httpx
import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL_AUTORISATION = "https://accounts.google.com/o/oauth2/v2/auth"
URL_JETON = "https://oauth2.googleapis.com/token"
PORT_LOCAL = 8765


class _GestionnaireRedirection(http.server.BaseHTTPRequestHandler):
    """Capture le `code` renvoyé par Google sur `http://localhost:PORT_LOCAL`.

    Attribut de classe plutôt que variable globale : `http.server` instancie un
    gestionnaire par requête, il faut un endroit qui survit à cette instanciation.
    """

    code: str | None = None

    def do_GET(self) -> None:  # noqa: N802 - nom imposé par http.server
        requete = urllib.parse.urlparse(self.path)
        parametres = urllib.parse.parse_qs(requete.query)
        _GestionnaireRedirection.code = (parametres.get("code") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Authentification reçue, vous pouvez fermer cet onglet.".encode())

    def log_message(self, *args) -> None:  # noqa: D102 - silencieux par conception
        pass


def _obtenir_code(client_id: str) -> str:
    redirection = f"http://localhost:{PORT_LOCAL}"
    parametres = {
        "client_id": client_id,
        "redirect_uri": redirection,
        "response_type": "code",
        "scope": "openid email",
    }
    url = f"{URL_AUTORISATION}?{urllib.parse.urlencode(parametres)}"
    print(f"Ouverture du navigateur pour l'authentification Google…\n{url}\n")
    webbrowser.open(url)

    serveur = http.server.HTTPServer(("localhost", PORT_LOCAL), _GestionnaireRedirection)
    while _GestionnaireRedirection.code is None:
        serveur.handle_request()
    serveur.server_close()
    return _GestionnaireRedirection.code


def _echanger_code(code: str, client_id: str, client_secret: str) -> dict:
    reponse = httpx.post(
        URL_JETON,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": f"http://localhost:{PORT_LOCAL}",
            "grant_type": "authorization_code",
        },
        timeout=15.0,
    )
    reponse.raise_for_status()
    return reponse.json()


async def _appeler_serveur(url: str, jeton: str) -> None:
    entetes = {"Authorization": f"Bearer {jeton}"}
    async with streamablehttp_client(url, headers=entetes) as (lecture, ecriture, _):
        async with ClientSession(lecture, ecriture) as session:
            await session.initialize()
            outils = await session.list_tools()
            print(f"\nsorabel-mcp a accepté le jeton — {len(outils.tools)} tools visibles :")
            for outil in sorted(outils.tools, key=lambda o: o.name):
                print(f"  - {outil.name}")


def main() -> None:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--url", required=True, help="URL /mcp de sorabel-mcp déployé")
    analyseur.add_argument("--client-id", required=True)
    analyseur.add_argument(
        "--client-secret", default=os.environ.get("SORABEL_OAUTH_CLIENT_SECRET")
    )
    arguments = analyseur.parse_args()
    if not arguments.client_secret:
        analyseur.error(
            "--client-secret manquant (ou variable SORABEL_OAUTH_CLIENT_SECRET)"
        )

    code = _obtenir_code(arguments.client_id)
    jetons = _echanger_code(code, arguments.client_id, arguments.client_secret)

    id_token = jetons["id_token"]
    charge = jwt.decode(id_token, options={"verify_signature": False})
    print("id_token reçu (signature non vérifiée ici, juste affichée) :")
    print(f"  iss = {charge.get('iss')}")
    print(f"  aud = {charge.get('aud')}")
    print(f"  sub = {charge.get('sub')}")
    print(
        f"\naccess_token reçu aussi, mais volontairement ignoré : "
        f"{jetons['access_token'][:12]}… (opaque, non-JWT — c'est lui qu'un client "
        f"OAuth générique enverrait par défaut, et que VerificateurJeton rejette)"
    )

    asyncio.run(_appeler_serveur(arguments.url, id_token))


if __name__ == "__main__":
    main()
