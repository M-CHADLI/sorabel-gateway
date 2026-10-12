"""Choix du serveur MCP qui répond pour une enseigne.

Le front ne détient aucune donnée et n'applique aucune règle d'accès : il choisit seulement
*quel* serveur MCP interroger. Chaque serveur ne sert qu'une enseigne (figée par processus,
voir `sorabel_enseigne.enseigne_active`) et applique lui-même la matrice d'accès, journal
compris. Ce module n'importe donc rien de `sorabel_rag` ni de `sorabel_sql` : un chemin
direct vers le pipeline contournerait la gouvernance.

Deux modes :

- HTTP (production) : chaque enseigne a son serveur déployé, joint par `front.passerelle`
  avec l'assertion IAP de la personne. Une enseigne n'est servie que si son URL est
  configurée — Sorabel garde l'URL historique (`SORABEL_URL_MCP`).
- local (`SORABEL_FRONT_LOCAL=1`, démonstration sur poste) : pas d'IAP, chaque enseigne est
  servie par un serveur stdio lancé par `front.mcp_client`, avec le profil choisi. Le
  serveur applique toujours la matrice de ce profil.
"""

from __future__ import annotations

import os

from sorabel_enseigne import ENSEIGNE_PAR_DEFAUT, enseignes_disponibles

from front import passerelle

# Identité affichée en mode local : sans IAP, il n'y a pas de sujet à lire dans un jeton.
SUJET_LOCAL = "local:developpeur"


def _variable_url(nom: str) -> str:
    return f"SORABEL_URL_MCP_{nom.upper()}"


def mode_local() -> bool:
    if os.environ.get("SORABEL_FRONT_LOCAL") != "1":
        return False
    if "K_SERVICE" in os.environ:
        # Cloud Run pose toujours K_SERVICE. Le mode local se passe d'IAP et laisse choisir
        # le profil à l'écran : actif en production, il donnerait à n'importe quel visiteur
        # le profil de son choix. On refuse de démarrer plutôt que de servir ainsi.
        raise RuntimeError(
            "SORABEL_FRONT_LOCAL=1 est interdit sur Cloud Run (K_SERVICE défini) : "
            "le mode local contourne Identity-Aware Proxy."
        )
    return True


def enseignes_servies() -> list[str]:
    disponibles = enseignes_disponibles()
    if mode_local():
        servies = list(disponibles)
    else:
        # Une URL vide ne joindrait rien : on la traite comme absente.
        servies = [
            nom
            for nom in disponibles
            if nom == ENSEIGNE_PAR_DEFAUT or os.environ.get(_variable_url(nom))
        ]
    # Sorabel en tête : c'est l'enseigne de production, choisie par défaut à l'écran.
    return sorted(servies, key=lambda nom: (nom != ENSEIGNE_PAR_DEFAUT, nom))


def url_mcp(nom: str) -> str:
    url = os.environ.get(_variable_url(nom))
    if url:
        return url
    if nom == ENSEIGNE_PAR_DEFAUT:
        # Lu à l'appel, pas à l'import : c'est la valeur que la production utilise déjà.
        return passerelle.URL_MCP
    # Jamais de repli sur l'URL Sorabel : une question Kiabi partirait vers les données
    # Sorabel, sous l'apparence d'une réponse normale.
    raise ValueError(f"aucune URL MCP pour l'enseigne {nom!r} : définir {_variable_url(nom)}")


def appeler(
    enseigne: str,
    tool: str,
    arguments: dict,
    *,
    assertion: str | None,
    profil: str | None,
) -> dict:
    servies = enseignes_servies()
    if enseigne not in servies:
        return {
            "statut": "erreur",
            "message": (
                f"l'enseigne {enseigne!r} n'est pas servie par ce front "
                f"(servies : {', '.join(servies) or 'aucune'})"
            ),
        }
    if mode_local():
        if not profil:
            # Même convention que la passerelle sans assertion : sans identité, pas d'appel.
            return {
                "statut": "non_autorise",
                "message": "Aucun profil choisi : sélectionnez un profil.",
            }
        # Import différé : le pont stdio pose une politique de boucle asyncio à l'import,
        # inutile au chemin HTTP de production.
        from front import mcp_client

        try:
            return mcp_client.appeler(profil, tool, arguments, enseigne=enseigne)
        except Exception as erreur:
            # Démarrage du serveur impossible, processus mort, délai dépassé : c'est une
            # panne, jamais un refus. Le détail (chemin, trace) reste côté serveur — l'écran
            # n'en a pas besoin et un message d'exception brut pourrait citer des chemins.
            print(f"serveur MCP local ({enseigne}, {profil}) : échec — {erreur!r}")
            return {"statut": "erreur", "message": "Serveur MCP local indisponible."}
    return passerelle.appeler(assertion, tool, arguments, url=url_mcp(enseigne))
