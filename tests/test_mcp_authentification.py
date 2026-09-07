"""Validation des jetons. Aucun appel réseau : les clés sont injectées.

Deux émetteurs sont acceptés — l'assertion signée d'IAP, que le front relaie, et les jetons
de Google Identity Platform présentés par les clients MCP tiers. Un jeton valide chez l'un
mais destiné à l'autre doit être refusé : c'est la protection contre la confusion d'audience.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_server.authentification import VerificateurJeton

CLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
EMETTEURS = {
    "https://cloud.google.com/iap": "/projects/1/apps/sorabel",
    "https://securetoken.google.com/sorabel": "sorabel",
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _jeton(**surcharges) -> str:
    charge = {
        "iss": "https://cloud.google.com/iap",
        "aud": "/projects/1/apps/sorabel",
        "sub": "sub-123",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    charge.update(surcharges)
    return jwt.encode(charge, CLE, algorithm="RS256")


def _verificateur() -> VerificateurJeton:
    return VerificateurJeton(EMETTEURS, recuperer_cles=lambda _: CLE.public_key())


@pytest.mark.anyio
async def test_jeton_valide_donne_le_sujet():
    acces = await _verificateur().verify_token(_jeton())
    assert acces is not None
    assert acces.subject == "sub-123"


@pytest.mark.anyio
async def test_jeton_expire_est_refuse():
    jeton = _jeton(exp=int(time.time()) - 10)
    assert await _verificateur().verify_token(jeton) is None


@pytest.mark.anyio
async def test_emetteur_inconnu_est_refuse():
    jeton = _jeton(iss="https://attaquant.example")
    assert await _verificateur().verify_token(jeton) is None


@pytest.mark.anyio
async def test_audience_d_un_autre_emetteur_est_refusee():
    # Confusion d'audience : un jeton IAP valide, mais présenté avec l'audience de l'autre
    # émetteur, ne doit pas ouvrir la porte.
    jeton = _jeton(aud="sorabel")
    assert await _verificateur().verify_token(jeton) is None


@pytest.mark.anyio
async def test_jeton_illisible_est_refuse():
    assert await _verificateur().verify_token("pas-un-jeton") is None
