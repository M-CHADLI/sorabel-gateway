"""Client LLM partagé : Azure AI Foundry (déploiement GPT-5.4-mini).

Un seul point d'appel pour la génération RAG (chantier 1) et Text-to-SQL (chantier 2) — un
seul endroit à changer si le déploiement ou le fournisseur change.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_client = None


def _variable_requise(nom: str) -> str:
    valeur = os.environ.get(nom)
    if not valeur:
        raise RuntimeError(
            f"{nom} manquante : copier .env.example vers .env et renseigner "
            "les identifiants Azure AI Foundry."
        )
    return valeur


def obtenir_client():
    """Chargé paresseusement : les modules qui importent ce fichier n'ont pas tous
    besoin d'un appel LLM — les tests unitaires du RAG et du SQL le monkeypatchent."""
    global _client
    if _client is None:
        from openai import AzureOpenAI

        _client = AzureOpenAI(
            azure_endpoint=_variable_requise("AZURE_OPENAI_ENDPOINT"),
            api_key=_variable_requise("AZURE_OPENAI_API_KEY"),
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
    return _client


def completer(messages: list[dict], **kwargs) -> str:
    """Un tour de conversation → le texte de la réponse. `messages` au format OpenAI
    ([{"role": "system"|"user"|"assistant", "content": str}, ...])."""
    deploiement = _variable_requise("AZURE_OPENAI_DEPLOYMENT")
    reponse = obtenir_client().chat.completions.create(
        model=deploiement, messages=messages, **kwargs
    )
    return reponse.choices[0].message.content
