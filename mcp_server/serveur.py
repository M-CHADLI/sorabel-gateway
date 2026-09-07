"""Serveur MCP : stdio en développement, HTTP streamable en production.

`resoudre_profil_stdio` et `resoudre_profil_http` sont les DEUX seuls points liés au
transport. Le reste — matrice, Perimetre, tools — est identique d'un mode à l'autre.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from gouvernance.identites import DepotIdentitesSqlite
from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre

from .authentification import VerificateurJeton
from .tools import enregistrer_tools

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_GOUVERNANCE_DB = RACINE / "gouvernance" / "gouvernance.db"


def transport() -> str:
    return os.environ.get("SORABEL_TRANSPORT", "stdio")


def resoudre_profil_stdio() -> str:
    profil = os.environ.get("SORABEL_PROFIL")
    if not profil:
        raise RuntimeError(
            "SORABEL_PROFIL doit être défini en transport stdio "
            "(ex. SORABEL_PROFIL=support python -m mcp_server.serveur)"
        )
    return profil


def resoudre_profil_http(depot, sujet: str) -> str:
    """Le profil vient du dépôt d'identités, jamais de l'appelant.

    Un sujet authentifié mais inconnu du dépôt n'obtient AUCUN profil par défaut : le
    serveur n'inscrit personne, c'est le front qui propose l'inscription.
    """
    profil = depot.profil_de(sujet)
    if profil is None:
        raise PermissionError(f"aucun profil attribué au sujet {sujet!r}")
    return profil


def _emetteurs() -> dict[str, str]:
    """URL d'émetteur → audience attendue, l'un pour IAP, l'autre pour les clients tiers."""
    emetteurs = {}
    if audience_iap := os.environ.get("SORABEL_IAP_AUDIENCE"):
        emetteurs["https://cloud.google.com/iap"] = audience_iap
    if emetteur := os.environ.get("SORABEL_OIDC_ISSUER"):
        emetteurs[emetteur] = os.environ["SORABEL_OIDC_AUDIENCE"]
    return emetteurs


def _choisir_depot_http(chemin_gouvernance_db: Path, matrice):
    """Choisit l'implémentation du dépôt d'identités pour le transport HTTP, selon
    `SORABEL_DEPOT` — même patron que `front.depot.depot_identites` (§5 de la conception
    GCP : Firestore est lu par le serveur et lu/écrit par le front, jamais l'inverse).

    N'est appelée qu'en HTTP : en stdio, personne ne configure Firestore pour une session
    de développement locale, et le profil ne vient de toute façon jamais du dépôt.

    Une variable oubliée ou mal orthographiée retomberait sinon silencieusement sur
    SQLite : chaque instance Cloud Run lirait alors sa propre copie figée dans l'image,
    invisible des attributions que le front écrit dans Firestore. D'où la trace sur
    stdout, cohérente avec `SORABEL_JOURNAL=stdout`.
    """
    if os.environ.get("SORABEL_DEPOT") == "firestore":
        # Import local : ne pas imposer cette dépendance au transport stdio, où elle
        # n'est jamais utilisée.
        from google.cloud import firestore

        from gouvernance.identites_firestore import DepotIdentitesFirestore

        print("construire_serveur : implémentation Firestore (SORABEL_DEPOT=firestore)")
        return DepotIdentitesFirestore(
            firestore.Client(), profils_valides=frozenset(matrice.profils)
        )

    valeur = os.environ.get("SORABEL_DEPOT")
    print(f"construire_serveur : implémentation SQLite (SORABEL_DEPOT={valeur!r})")
    return DepotIdentitesSqlite(chemin_gouvernance_db)


def construire_serveur(
    chemin_gouvernance_db: Path = CHEMIN_GOUVERNANCE_DB, depot_identites=None
) -> FastMCP:
    matrice = charger_matrice(chemin_gouvernance_db)

    if transport() == "stdio":
        perimetre_fige = Perimetre(resoudre_profil_stdio(), matrice)
        mcp = FastMCP(name="sorabel-data-gateway")
        enregistrer_tools(mcp, lambda: perimetre_fige)
        return mcp

    depot = depot_identites or _choisir_depot_http(chemin_gouvernance_db, matrice)

    def resolveur() -> Perimetre:
        acces = get_access_token()
        if acces is None:
            raise PermissionError("appel non authentifié")
        return Perimetre(resoudre_profil_http(depot, acces.subject), matrice)

    mcp = FastMCP(
        name="sorabel-data-gateway",
        token_verifier=VerificateurJeton(
            _emetteurs(),
            jwks={
                "https://cloud.google.com/iap": "https://www.gstatic.com/iap/verify/public_key-jwk",
                os.environ.get("SORABEL_OIDC_ISSUER", ""): os.environ.get("SORABEL_OIDC_JWKS", ""),
            },
        ),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(os.environ["SORABEL_OIDC_ISSUER"]),
            resource_server_url=AnyHttpUrl(os.environ["SORABEL_URL_PUBLIQUE"]),
            required_scopes=[],
        ),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
    enregistrer_tools(mcp, resolveur)
    return mcp


if __name__ == "__main__":
    mode = "stdio" if transport() == "stdio" else "streamable-http"
    construire_serveur().run(transport=mode)
