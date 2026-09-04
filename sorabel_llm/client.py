"""Client LLM partagé : Azure AI Foundry (déploiement GPT-5.4-mini).

Un seul point d'appel pour la génération RAG (chantier 1) et Text-to-SQL (chantier 2) — un
seul endroit à changer si le déploiement ou le fournisseur change.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_client = None


def _variable_requise(nom: str, *alias: str) -> str:
    """`alias` accepte les autres noms rencontrés pour la même variable : les .env
    partagés entre projets nomment souvent le déploiement AZURE_OPENAI_DEPLOYMENT_NAME."""
    for candidat in (nom, *alias):
        valeur = os.environ.get(candidat)
        if valeur:
            return valeur
    noms = " / ".join((nom, *alias))
    raise RuntimeError(
        f"{noms} manquante : copier .env.example vers .env et renseigner "
        "les identifiants Azure AI Foundry."
    )


def _base_url(brut: str) -> str:
    """Ramène l'endpoint à la racine de l'API v1 (`.../openai/v1`).

    La ressource est un projet Azure AI Foundry (`*.services.ai.azure.com`) : elle sert
    l'API « v1 » compatible OpenAI (`/openai/v1/chat/completions`, déploiement passé en
    `model`), et non le chemin data-plane historique d'Azure OpenAI
    (`/openai/deployments/<déploiement>/chat/completions?api-version=...`) — d'où le 404
    obtenu avec le client `AzureOpenAI`. On accepte l'endpoint avec ou sans le suffixe.
    """
    url = brut.strip().rstrip("/")
    return url if url.endswith("/openai/v1") else f"{url}/openai/v1"


def obtenir_client():
    """Chargé paresseusement : les modules qui importent ce fichier n'ont pas tous
    besoin d'un appel LLM — les tests unitaires du RAG et du SQL le monkeypatchent."""
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(
            base_url=_base_url(_variable_requise("AZURE_OPENAI_ENDPOINT")),
            api_key=_variable_requise("AZURE_OPENAI_API_KEY"),
        )
    return _client


def completer(messages: list[dict], **kwargs) -> str:
    """Un tour de conversation → le texte de la réponse. `messages` au format OpenAI
    ([{"role": "system"|"user"|"assistant", "content": str}, ...])."""
    deploiement = _variable_requise("AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT_NAME")
    reponse = obtenir_client().chat.completions.create(
        model=deploiement, messages=messages, **kwargs
    )
    return reponse.choices[0].message.content
