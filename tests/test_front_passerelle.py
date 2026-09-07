"""La passerelle relaie l'assertion IAP sans jamais la fabriquer ni la modifier."""

import asyncio

import httpx
import pytest

from front import passerelle


def test_assertion_lue_dans_l_entete(monkeypatch):
    monkeypatch.setattr(
        passerelle, "_entetes", lambda: {"X-Goog-IAP-JWT-Assertion": "jeton-abc"}
    )
    assert passerelle.assertion_iap() == "jeton-abc"


def test_entete_absent_donne_none(monkeypatch):
    monkeypatch.setattr(passerelle, "_entetes", lambda: {})
    assert passerelle.assertion_iap() is None


def test_entete_insensible_a_la_casse(monkeypatch):
    # Les serveurs HTTP normalisent la casse des en-têtes de façons variées.
    monkeypatch.setattr(passerelle, "_entetes", lambda: {"x-goog-iap-jwt-assertion": "jeton-abc"})
    assert passerelle.assertion_iap() == "jeton-abc"


def test_sujet_lu_sans_verifier_la_signature():
    """Le front lit le sujet pour l'afficher et interroger le dépôt ; il ne VÉRIFIE rien.

    La vérification est faite par le serveur MCP, qui seul décide. Décoder ici sans
    vérifier est donc sûr — à condition que rien de sensible n'en dépende côté front.
    """
    import jwt

    jeton = jwt.encode({"sub": "sub-123", "aud": "peu-importe"}, "secret", algorithm="HS256")
    assert passerelle.sujet_du_jeton(jeton) == "sub-123"


def test_sujet_de_none_est_none():
    assert passerelle.sujet_du_jeton(None) is None


def test_sujet_d_un_jeton_illisible_est_none():
    assert passerelle.sujet_du_jeton("pas-un-jeton") is None


def test_appel_sans_assertion_ne_contacte_pas_le_serveur(monkeypatch):
    appels = []
    monkeypatch.setattr(passerelle, "_appeler_distant", lambda *a, **k: appels.append(a))
    resultat = passerelle.appeler(None, "check_stock", {"ref": "REF-8842"})
    assert resultat["statut"] == "non_autorise"
    assert appels == []


def _distant_qui_leve(exception):
    """Remplace `_appeler_distant` par une coroutine qui lève `exception` une fois attendue."""

    async def _coroutine(*a, **k):
        raise exception

    return _coroutine


def test_timeout_donne_un_statut_erreur_pas_une_exception(monkeypatch):
    monkeypatch.setattr(
        passerelle, "_appeler_distant", _distant_qui_leve(asyncio.TimeoutError())
    )
    resultat = passerelle.appeler("jeton-secret-abc", "check_stock", {"ref": "REF-8842"})
    assert resultat["statut"] == "erreur"
    assert "jeton-secret-abc" not in resultat["message"]


def test_erreur_de_connexion_donne_un_statut_erreur_pas_une_exception(monkeypatch):
    monkeypatch.setattr(
        passerelle,
        "_appeler_distant",
        _distant_qui_leve(httpx.ConnectError("connexion refusée")),
    )
    resultat = passerelle.appeler("jeton-secret-abc", "check_stock", {"ref": "REF-8842"})
    assert resultat["statut"] == "erreur"
    assert "jeton-secret-abc" not in resultat["message"]


def test_lister_tools_en_panne_reseau_renvoie_une_liste_vide(monkeypatch):
    monkeypatch.setattr(
        passerelle,
        "_appeler_distant",
        _distant_qui_leve(httpx.ConnectTimeout("délai de connexion dépassé")),
    )
    resultat = passerelle.lister_tools("jeton-secret-abc")
    assert resultat == []
