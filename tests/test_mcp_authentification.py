"""Validation des jetons. Aucun appel réseau : les clés sont injectées.

Deux émetteurs sont acceptés — l'assertion signée d'IAP, que le front relaie, et les jetons
de Google Identity Platform présentés par les clients MCP tiers. Un jeton valide chez l'un
mais destiné à l'autre doit être refusé : c'est la protection contre la confusion d'audience.
"""

import logging
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_server import authentification
from mcp_server.authentification import ErreurConfigurationAuthentification, VerificateurJeton

CLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
IAP = "https://cloud.google.com/iap"
GIP = "https://securetoken.google.com/sorabel"
EMETTEURS = {
    IAP: "/projects/1/apps/sorabel",
    GIP: "sorabel",
}
JWKS = {
    IAP: "https://exemple.invalid/iap/jwks",
    GIP: "https://exemple.invalid/gip/jwks",
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _jeton(sans: tuple[str, ...] = (), **surcharges) -> str:
    charge = {
        "iss": IAP,
        "aud": "/projects/1/apps/sorabel",
        "sub": "sub-123",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    charge.update(surcharges)
    for claim in sans:
        charge.pop(claim, None)
    return jwt.encode(charge, CLE, algorithm="RS256")


def _verificateur() -> VerificateurJeton:
    return VerificateurJeton(EMETTEURS, recuperer_cles=lambda _: CLE.public_key())


@pytest.mark.anyio
async def test_jeton_valide_donne_le_sujet():
    acces = await _verificateur().verify_token(_jeton())
    assert acces is not None
    assert acces.subject == "sub-123"


@pytest.mark.anyio
async def test_jeton_valide_du_second_emetteur_est_accepte():
    # Le second émetteur n'était jamais exercé en cas passant : une erreur de configuration
    # sur sa ligne serait passée inaperçue, tous ses jetons étant refusés en silence.
    acces = await _verificateur().verify_token(_jeton(iss=GIP, aud="sorabel", sub="sub-gip"))
    assert acces is not None
    assert acces.subject == "sub-gip"


@pytest.mark.anyio
async def test_jeton_expire_est_refuse():
    jeton = _jeton(exp=int(time.time()) - 10)
    assert await _verificateur().verify_token(jeton) is None


@pytest.mark.anyio
async def test_jeton_sans_exp_est_refuse():
    # Sans claim `require`, PyJWT ne vérifie `exp` que s'il est présent : un jeton sans
    # expiration serait éternellement valable, donc irrévocable en cas d'exfiltration.
    assert await _verificateur().verify_token(_jeton(sans=("exp",))) is None


@pytest.mark.anyio
async def test_jeton_sans_sub_est_refuse():
    assert await _verificateur().verify_token(_jeton(sans=("sub",))) is None


@pytest.mark.anyio
async def test_jeton_sans_aud_est_refuse():
    assert await _verificateur().verify_token(_jeton(sans=("aud",))) is None


@pytest.mark.anyio
async def test_emetteur_inconnu_est_refuse():
    jeton = _jeton(iss="https://attaquant.example")
    assert await _verificateur().verify_token(jeton) is None


@pytest.mark.anyio
async def test_jeton_de_l_emetteur_a_presente_comme_venant_de_b_est_refuse():
    # Séparation stricte des deux émetteurs : un jeton réellement destiné à IAP (audience
    # IAP) mais présenté sous l'identité de GIP ne doit pas passer, et réciproquement.
    verificateur = _verificateur()
    assert await verificateur.verify_token(_jeton(iss=GIP, aud="/projects/1/apps/sorabel")) is None
    assert await verificateur.verify_token(_jeton(iss=IAP, aud="sorabel")) is None


@pytest.mark.anyio
async def test_audience_en_liste_contenant_la_bonne_valeur_est_refusee():
    # PyJWT accepte l'audience attendue dès qu'elle est *présente parmi* une liste : un jeton
    # portant les deux audiences satisferait alors les deux émetteurs à la fois. On exige
    # l'égalité stricte après le décodage signé.
    jeton = _jeton(aud=["/projects/1/apps/sorabel", "sorabel"])
    assert await _verificateur().verify_token(jeton) is None


@pytest.mark.anyio
async def test_jeton_illisible_est_refuse():
    assert await _verificateur().verify_token("pas-un-jeton") is None


@pytest.mark.anyio
async def test_scopes_toujours_vides():
    # Décision de conception verrouillée : les droits viennent de la matrice d'accès indexée
    # par profil, jamais des scopes du jeton — une seule source de vérité pour l'autorisation.
    acces = await _verificateur().verify_token(_jeton(scope="admin", scopes=["admin"]))
    assert acces is not None
    assert acces.scopes == []


# --- Configuration ---------------------------------------------------------------------


def test_emetteur_sans_url_jwks_echoue_au_demarrage():
    # Mieux vaut refuser de démarrer que découvrir le trou au premier appel : un KeyError en
    # vol donnerait un 500 au lieu d'un 401, et le code de statut trahirait quel émetteur est
    # réellement configuré.
    with pytest.raises(ErreurConfigurationAuthentification) as erreur:
        VerificateurJeton(EMETTEURS, jwks={IAP: JWKS[IAP]})
    assert GIP in str(erreur.value)


def test_jwks_vide_est_traite_comme_manquant():
    with pytest.raises(ErreurConfigurationAuthentification):
        VerificateurJeton({IAP: "aud"}, jwks={IAP: ""})


def test_configuration_complete_demarre():
    assert VerificateurJeton(EMETTEURS, jwks=JWKS) is not None


@pytest.mark.anyio
async def test_exception_inattendue_ne_s_echappe_pas():
    # Filet : toute erreur non prévue du chemin de récupération des clés doit ressortir en
    # refus maîtrisé (None), jamais en trace serveur.
    def exploser(_jeton_recu):
        raise RuntimeError("panne inattendue")

    verificateur = VerificateurJeton(EMETTEURS, recuperer_cles=exploser)
    assert await verificateur.verify_token(_jeton()) is None


@pytest.mark.anyio
async def test_panne_jwks_est_journalisee_sans_le_jeton(caplog):
    # Une panne du fournisseur de clés est indistinguable d'un refus de sécurité côté client
    # (None dans les deux cas) : elle doit au moins laisser une trace côté serveur, sinon
    # l'astreinte cherche une compromission là où il y a une coupure réseau.
    def couper(_jeton_recu):
        raise jwt.PyJWKClientError("point de terminaison JWKS injoignable")

    verificateur = VerificateurJeton(EMETTEURS, recuperer_cles=couper)
    jeton = _jeton()
    with caplog.at_level(logging.ERROR, logger="mcp_server.authentification"):
        assert await verificateur.verify_token(jeton) is None

    assert any("JWKS" in enregistrement.message for enregistrement in caplog.records)
    trace = caplog.text
    assert IAP in trace
    assert jeton not in trace  # jamais le jeton lui-même


# --- Récupération des clés par JWKS (chemin de production, sans réseau) ------------------


class _CleFactice:
    def __init__(self, cle):
        self.key = cle


class _ClientJwksFactice:
    """Doublure de PyJWKClient : mémorise les URL construites, ne fait aucun appel réseau."""

    urls: list[str] = []

    def __init__(self, uri, cache_keys=False, **_options):
        type(self).urls.append(uri)
        self.uri = uri
        self.appels = 0

    def get_signing_key_from_jwt(self, jeton):
        self.appels += 1
        return _CleFactice(CLE.public_key())


@pytest.fixture
def client_jwks_factice(monkeypatch):
    _ClientJwksFactice.urls = []
    monkeypatch.setattr(authentification, "PyJWKClient", _ClientJwksFactice)
    return _ClientJwksFactice


def test_cles_par_jwks_choisit_l_url_de_l_emetteur(client_jwks_factice):
    verificateur = VerificateurJeton(EMETTEURS, jwks=JWKS)

    verificateur._cles_par_jwks(_jeton())
    assert client_jwks_factice.urls == [JWKS[IAP]]

    verificateur._cles_par_jwks(_jeton(iss=GIP, aud="sorabel"))
    assert client_jwks_factice.urls == [JWKS[IAP], JWKS[GIP]]


def test_cles_par_jwks_reutilise_le_client_par_emetteur(client_jwks_factice):
    # Le cache est ce qui évite un appel réseau par requête entrante : un client par émetteur,
    # construit une seule fois.
    verificateur = VerificateurJeton(EMETTEURS, jwks=JWKS)
    verificateur._cles_par_jwks(_jeton(sub="a"))
    verificateur._cles_par_jwks(_jeton(sub="b"))

    assert client_jwks_factice.urls == [JWKS[IAP]]
    assert verificateur._clients[IAP].appels == 2


def test_cles_par_jwks_rend_bien_la_cle_de_signature(client_jwks_factice):
    verificateur = VerificateurJeton(EMETTEURS, jwks=JWKS)
    cle = verificateur._cles_par_jwks(_jeton())
    assert cle.public_numbers() == CLE.public_key().public_numbers()


def test_cles_par_jwks_emetteur_absent_leve_une_erreur_explicite(client_jwks_factice):
    # Anciennement un KeyError nu, non attrapé par `except jwt.PyJWTError` : trace 500.
    verificateur = VerificateurJeton(EMETTEURS, jwks=JWKS)
    with pytest.raises(ErreurConfigurationAuthentification):
        verificateur._cles_par_jwks(_jeton(iss="https://inconnu.example"))
    assert client_jwks_factice.urls == []


@pytest.mark.anyio
async def test_chemin_jwks_complet_valide_un_jeton(client_jwks_factice):
    # Bout en bout sur le chemin de production (JWKS), la doublure remplaçant le seul appel
    # réseau : c'est ce chemin-là qui tourne réellement, et qu'aucun test ne couvrait.
    verificateur = VerificateurJeton(EMETTEURS, jwks=JWKS)
    acces = await verificateur.verify_token(_jeton())
    assert acces is not None
    assert acces.subject == "sub-123"
