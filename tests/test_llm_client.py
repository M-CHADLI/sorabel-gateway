"""Client LLM partagé (Azure AI Foundry) : erreurs de configuration et appel."""

import pytest

from sorabel_llm import client as llm_client


def test_variable_manquante_leve_une_erreur_explicite(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    with pytest.raises(RuntimeError, match="AZURE_OPENAI_DEPLOYMENT"):
        llm_client._variable_requise("AZURE_OPENAI_DEPLOYMENT")


class _CompletionsFactice:
    def __init__(self):
        self.appels = []

    def create(self, **kwargs):
        self.appels.append(kwargs)
        return _ReponseFactice("réponse factice")


class _ChatFactice:
    def __init__(self):
        self.completions = _CompletionsFactice()


class _ClientFactice:
    def __init__(self):
        self.chat = _ChatFactice()


class _MessageFactice:
    def __init__(self, contenu):
        self.content = contenu


class _ChoixFactice:
    def __init__(self, contenu):
        self.message = _MessageFactice(contenu)


class _ReponseFactice:
    def __init__(self, contenu):
        self.choices = [_ChoixFactice(contenu)]


def test_completer_appelle_le_deploiement_configure_et_retourne_le_texte(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4-mini-test")
    client_factice = _ClientFactice()
    monkeypatch.setattr(llm_client, "obtenir_client", lambda: client_factice)

    resultat = llm_client.completer([{"role": "user", "content": "bonjour"}])

    assert resultat == "réponse factice"
    appel = client_factice.chat.completions.appels[0]
    assert appel["model"] == "gpt-5.4-mini-test"
    assert appel["messages"] == [{"role": "user", "content": "bonjour"}]
