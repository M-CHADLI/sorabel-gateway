"""La passerelle relaie l'assertion IAP sans jamais la fabriquer ni la modifier."""

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
