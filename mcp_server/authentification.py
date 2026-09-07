"""Validation des jetons entrants — le serveur MCP est un Resource Server, pas un émetteur.

Il n'y a rien à déchiffrer ni à stocker : on vérifie une signature, un émetteur, une
audience et une expiration, puis on rend le sujet. Tout le reste de la gouvernance part de
ce sujet.

Deux émetteurs sont acceptés, et l'audience est vérifiée **par émetteur** : accepter
n'importe quelle audience de n'importe quel émetteur rouvrirait la confusion d'audience,
c'est-à-dire la possibilité de rejouer ici un jeton émis pour un autre service.
"""

from __future__ import annotations

import logging

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier

# Tuple et non liste : la constante est partagée par tout le module et ne doit pas pouvoir
# être élargie par mégarde à l'exécution — un `ALGORITHMES.append("HS256")` ailleurs dans le
# processus suffirait à autoriser la confusion de type d'algorithme (clé publique rejouée
# comme secret HMAC).
ALGORITHMES = ("RS256", "ES256")

# Claims exigés dans le jeton signé. PyJWT ne valide `exp` que s'il est présent : sans cette
# exigence, un jeton sans `exp` serait accepté et n'expirerait jamais, donc irrévocable.
CLAIMS_REQUIS = ["exp", "iss", "aud", "sub"]

# Journalisation d'infrastructure sur stderr plutôt que `gouvernance.journaliser()` : ce
# dernier décrit un *appel de tool gouverné* (profil, tool, autorisé, entrées, n_lignes) et
# alimente la piste d'audit E4/E5. Une panne du fournisseur de clés n'est ni un appel de tool
# ni une décision d'accès ; l'y écrire polluerait l'audit avec des lignes aux champs vides et
# fausserait tout comptage d'appels. `logging` sur stderr est récupéré par Cloud Logging au
# même titre que stdout, avec une sévérité distincte.
_journal = logging.getLogger(__name__)


class ErreurConfigurationAuthentification(RuntimeError):
    """Configuration inutilisable : on refuse de démarrer plutôt que d'échouer en vol."""


class VerificateurJeton(TokenVerifier):
    def __init__(self, emetteurs: dict[str, str], recuperer_cles=None, jwks: dict[str, str] | None = None):
        """`emetteurs` : URL d'émetteur → audience attendue.

        `recuperer_cles(jeton) -> clé publique` est injectable pour les tests ; à défaut, les
        clés sont récupérées par JWKS et mises en cache par PyJWKClient.
        """
        self._emetteurs = emetteurs
        self._jwks = jwks or {}
        self._clients: dict[str, PyJWKClient] = {}

        if recuperer_cles is None:
            # Échec au démarrage : un émetteur accepté sans URL JWKS ne peut pas voir ses
            # jetons vérifiés. Découvrir cela au premier appel donnerait une erreur serveur
            # au lieu d'un 401 — et le code de statut trahirait alors quel émetteur est
            # correctement configuré.
            manquants = sorted(e for e in emetteurs if not self._jwks.get(e))
            if manquants:
                raise ErreurConfigurationAuthentification(
                    "URL JWKS manquante pour les émetteurs acceptés : " + ", ".join(manquants)
                )

        self._recuperer_cles = recuperer_cles or self._cles_par_jwks

    def _cles_par_jwks(self, jeton: str):
        emetteur = jwt.decode(jeton, options={"verify_signature": False})["iss"]
        url = self._jwks.get(emetteur)
        if not url:
            # Ne devrait pas arriver après la validation du constructeur, mais la fonction est
            # appelable seule : on lève une erreur explicite plutôt qu'un KeyError nu.
            raise ErreurConfigurationAuthentification(f"aucune URL JWKS pour l'émetteur {emetteur!r}")
        if emetteur not in self._clients:
            self._clients[emetteur] = PyJWKClient(url, cache_keys=True)
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
                algorithms=list(ALGORITHMES),
                audience=audience,
                issuer=emetteur,
                options={"require": CLAIMS_REQUIS},
            )
        except jwt.PyJWKClientError as erreur:
            # `PyJWKClientError` hérite de `PyJWTError` : sans ce cas dédié, une coupure vers
            # le fournisseur de clés serait indistinguable d'un jeton falsifié et l'astreinte
            # chercherait une compromission là où il y a une panne. Le client reçoit toujours
            # None (aucune fuite), mais le serveur trace l'incident. Jamais le jeton lui-même.
            _journal.error("JWKS indisponible pour l'émetteur %s : %s", emetteur, erreur)
            return None
        except jwt.PyJWTError:
            return None
        except Exception as erreur:  # noqa: BLE001 - filet de sécurité volontaire
            # Toute exception inattendue (configuration, réseau, bibliothèque tierce) doit
            # sortir en 401 maîtrisé et non en trace 500 : le code de statut ne doit rien
            # apprendre sur la configuration du serveur.
            _journal.exception("erreur inattendue à la vérification du jeton (émetteur %s) : %s", emetteur, erreur)
            return None

        # Égalité stricte : PyJWT accepte l'audience attendue dès qu'elle est *présente parmi*
        # une liste, donc un jeton portant les deux audiences satisferait les deux émetteurs à
        # la fois. Une audience en liste est refusée, même si elle contient la bonne valeur.
        if charge.get("aud") != audience:
            return None

        sujet = charge.get("sub")
        if not sujet:
            return None

        return AccessToken(
            token=token,
            # Repli acceptable *aujourd'hui* : la gouvernance ne s'appuie que sur `subject`
            # (le profil est résolu à partir du sujet), et `client_id` n'est ici qu'une
            # étiquette de traçabilité. Le piège de demain : si une règle d'accès, un quota ou
            # une facturation venait à se fonder sur `client_id`, tous les jetons dépourvus de
            # `azp` — l'assertion IAP en particulier — se retrouveraient regroupés sous une
            # même identité « émetteur », ce qui les rendrait indiscernables entre clients.
            client_id=charge.get("azp") or emetteur,
            # Décision de conception : aucun scope OAuth n'est dérivé du jeton. Les droits
            # viennent exclusivement de la matrice d'accès indexée par profil ; laisser un
            # scope entrer ici créerait une seconde source de vérité pour l'autorisation.
            scopes=[],
            expires_at=charge.get("exp"),
            subject=sujet,
            claims=charge,
        )
