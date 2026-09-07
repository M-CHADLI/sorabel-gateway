"""Validation des jetons entrants — le serveur MCP est un Resource Server, pas un émetteur.

Il n'y a rien à déchiffrer ni à stocker : on vérifie une signature, un émetteur, une
audience et une expiration, puis on rend le sujet. Tout le reste de la gouvernance part de
ce sujet.

Deux émetteurs sont acceptés, et l'audience est vérifiée **par émetteur** : accepter
n'importe quelle audience de n'importe quel émetteur rouvrirait la confusion d'audience,
c'est-à-dire la possibilité de rejouer ici un jeton émis pour un autre service.
"""

from __future__ import annotations

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier

ALGORITHMES = ["RS256", "ES256"]


class VerificateurJeton(TokenVerifier):
    def __init__(self, emetteurs: dict[str, str], recuperer_cles=None, jwks: dict[str, str] | None = None):
        """`emetteurs` : URL d'émetteur → audience attendue.

        `recuperer_cles(jeton) -> clé publique` est injectable pour les tests ; à défaut, les
        clés sont récupérées par JWKS et mises en cache par PyJWKClient.
        """
        self._emetteurs = emetteurs
        self._jwks = jwks or {}
        self._recuperer_cles = recuperer_cles or self._cles_par_jwks
        self._clients: dict[str, PyJWKClient] = {}

    def _cles_par_jwks(self, jeton: str):
        emetteur = jwt.decode(jeton, options={"verify_signature": False})["iss"]
        if emetteur not in self._clients:
            self._clients[emetteur] = PyJWKClient(self._jwks[emetteur], cache_keys=True)
        return self._clients[emetteur].get_signing_key_from_jwt(jeton).key

    async def verify_token(self, token: str) -> AccessToken | None:
        """Renvoie None sur tout jeton douteux — le SDK traduit cela en 401.

        On ne distingue pas les causes de rejet dans la valeur de retour : un attaquant
        n'apprend pas si c'est l'émetteur, l'audience ou la signature qui a échoué.
        """
        try:
            emetteur = jwt.decode(token, options={"verify_signature": False}).get("iss")
        except jwt.PyJWTError:
            return None

        audience = self._emetteurs.get(emetteur)
        if audience is None:
            return None

        try:
            charge = jwt.decode(
                token,
                self._recuperer_cles(token),
                algorithms=ALGORITHMES,
                audience=audience,
                issuer=emetteur,
            )
        except jwt.PyJWTError:
            return None

        sujet = charge.get("sub")
        if not sujet:
            return None

        return AccessToken(
            token=token,
            client_id=charge.get("azp") or emetteur,
            scopes=[],
            expires_at=charge.get("exp"),
            subject=sujet,
            claims=charge,
        )
