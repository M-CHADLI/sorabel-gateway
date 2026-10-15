"""L'URL publique d'un serveur MCP fixe où il publie ses métadonnées de ressource protégée.

kiabi-mcp est déployé avec une URL publique suffixée /mcp (`_KIABI_MCP_URL`, cloudbuild.yaml),
sorabel-mcp avec une URL nue (`_SORABEL_URL_PUBLIQUE`). Le SDK MCP place les métadonnées au
chemin RFC 9728 de chacune et l'annonce dans l'en-tête WWW-Authenticate d'un refus : c'est ce
comportement, dont dépendent l'amorçage et la vérification de docs/EXPLOITATION.md §10, que
ces tests figent — application construite en mémoire, aucun appel réseau.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import httpx
import pytest

from gouvernance.seed import peupler
from mcp_server.serveur import construire_serveur


def _application(monkeypatch, tmp_path, url_publique: str):
    monkeypatch.setenv("SORABEL_TRANSPORT", "http")
    monkeypatch.setenv("SORABEL_OIDC_ISSUER", "https://issuer.exemple.test")
    monkeypatch.setenv("SORABEL_OIDC_AUDIENCE", "sorabel-test")
    monkeypatch.setenv("SORABEL_OIDC_JWKS", "https://issuer.exemple.test/jwks")
    monkeypatch.setenv("SORABEL_URL_PUBLIQUE", url_publique)
    monkeypatch.delenv("SORABEL_IAP_AUDIENCE", raising=False)
    monkeypatch.delenv("SORABEL_DEPOT", raising=False)
    monkeypatch.delenv("SORABEL_PROFIL", raising=False)
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    return construire_serveur(chemin_gouvernance_db=chemin).streamable_http_app()


def _requetes(application, *requetes: tuple[str, str]) -> list[httpx.Response]:
    """Requêtes servies en mémoire par l'application ASGI, sans socket ni réseau.
    httpx plutôt que starlette.testclient : ce dernier lève à l'import un avertissement de
    dépréciation d'anyio, qui polluerait la sortie de la suite."""

    async def envoyer():
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://serveur.test") as client:
            return [
                await client.request(methode, chemin, json={} if methode == "POST" else None)
                for methode, chemin in requetes
            ]

    return asyncio.run(envoyer())


@pytest.mark.parametrize(
    ("url_publique", "metadonnees"),
    [
        pytest.param(
            "https://kiabi-mcp.exemple.test/mcp",
            "https://kiabi-mcp.exemple.test/.well-known/oauth-protected-resource/mcp",
            id="kiabi-mcp-url-suffixee-mcp",
        ),
        pytest.param(
            "https://sorabel-mcp.exemple.test",
            "https://sorabel-mcp.exemple.test/.well-known/oauth-protected-resource",
            id="sorabel-mcp-url-nue",
        ),
    ],
)
def test_metadonnees_publiees_au_chemin_rfc_9728_de_l_url_publique(
    monkeypatch, tmp_path, url_publique, metadonnees
):
    application = _application(monkeypatch, tmp_path, url_publique)
    refus, reponse = _requetes(application, ("POST", "/mcp"), ("GET", urlsplit(metadonnees).path))

    # Sans jeton, refus avant tout tool, et l'en-tête dit au client où lire les métadonnées.
    assert refus.status_code == 401
    assert f'resource_metadata="{metadonnees}"' in refus.headers["www-authenticate"]

    assert reponse.status_code == 200
    # Le serveur se déclare sous l'URL que le front appelle (pydantic ajoute « / » à une URL
    # nue, d'où la comparaison sans la barre finale).
    assert reponse.json()["resource"].rstrip("/") == url_publique
    assert reponse.json()["authorization_servers"] == ["https://issuer.exemple.test/"]


def test_url_publique_vide_le_serveur_refuse_de_demarrer(monkeypatch, tmp_path):
    # Premier passage de l'amorçage (_KIABI_MCP_URL encore vide) : la révision ne démarre pas
    # plutôt que de publier des métadonnées fausses — docs/EXPLOITATION.md §10.3, étape 1.
    with pytest.raises(ValueError):
        _application(monkeypatch, tmp_path, "")
