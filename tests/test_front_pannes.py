"""Pannes du pont local et de la passerelle HTTP : jamais une trace à l'écran, jamais un
refus d'accès à la place d'une panne, et une session morte ne reste pas en cache.

Aucun réseau, aucun sous-processus : les sessions sont des doublures, ou de vraies
`_SessionPersistante` dont l'ouverture est remplacée par une coroutine locale.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading

import httpx
import pytest

from front import mcp_client, passerelle, routage


@pytest.fixture(autouse=True)
def mode_local(monkeypatch):
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setattr(routage, "enseignes_disponibles", lambda: ["kiabi", "sorabel"])


# --- routage : la branche locale ----------------------------------------------------------


def test_routage_local_traduit_une_exception_en_statut_erreur(monkeypatch, capsys):
    def explose(profil, tool, arguments, enseigne=None):
        raise RuntimeError("Traceback secret : C:\\Users\\quelquun\\serveur.py")

    monkeypatch.setattr(mcp_client, "appeler", explose)
    resultat = routage.appeler(
        "kiabi", "check_stock", {"ref": "REF-1024"}, assertion=None, profil="support"
    )
    assert resultat == {"statut": "erreur", "message": "Serveur MCP local indisponible."}
    # Le détail reste côté serveur (sortie standard du front), pas dans le retour.
    assert "secret" in capsys.readouterr().out


def test_routage_local_ne_confond_pas_une_panne_avec_un_refus(monkeypatch):
    def delai(profil, tool, arguments, enseigne=None):
        raise TimeoutError("délai")

    monkeypatch.setattr(mcp_client, "appeler", delai)
    resultat = routage.appeler("sorabel", "get_schema", {}, assertion=None, profil="dev")
    assert resultat["statut"] == "erreur"


# --- mcp_client : une session qui lève est retirée du cache et arrêtée --------------------


class FausseSession:
    def __init__(self):
        self.arretee = False

    def appeler(self, tool, arguments):
        raise ConnectionError("le serveur MCP est mort")

    def arreter(self):
        self.arretee = True


def test_session_qui_leve_a_l_appel_est_retiree_du_cache(monkeypatch):
    morte = FausseSession()
    monkeypatch.setattr(mcp_client, "_sessions", {("support", "kiabi"): morte})

    with pytest.raises(ConnectionError):
        mcp_client.appeler("support", "check_stock", {}, enseigne="kiabi")

    assert ("support", "kiabi") not in mcp_client._sessions
    assert morte.arretee


def test_reessayer_relance_un_serveur_neuf(monkeypatch):
    creees = []

    class Neuve:
        def __init__(self, profil, enseigne=None):
            creees.append(self)

        def appeler(self, tool, arguments):
            return {"statut": "ok"}

        def arreter(self):
            pass

    morte = FausseSession()
    monkeypatch.setattr(mcp_client, "_sessions", {("support", "kiabi"): morte})
    monkeypatch.setattr(mcp_client, "_SessionPersistante", Neuve)

    # Premier clic : le front reçoit une erreur normale.
    erreur = routage.appeler("kiabi", "check_stock", {}, assertion=None, profil="support")
    assert erreur["statut"] == "erreur"
    assert creees == []
    # « Réessayer » : une session neuve, pas la morte.
    ok = routage.appeler("kiabi", "check_stock", {}, assertion=None, profil="support")
    assert ok == {"statut": "ok"}
    assert len(creees) == 1


def test_une_autre_session_du_cache_n_est_pas_retiree(monkeypatch):
    """Entre l'échec et le nettoyage, un autre thread a pu recréer la session : on ne
    retire que l'instance qui a levé."""
    morte, neuve = FausseSession(), FausseSession()
    monkeypatch.setattr(mcp_client, "_sessions", {("support", None): neuve})
    mcp_client._abandonner("support", None, morte)
    assert mcp_client._sessions == {("support", None): neuve}
    assert morte.arretee and not neuve.arretee


def _fil(nom: str) -> threading.Thread:
    return next(t for t in threading.enumerate() if t.name == nom)


def test_l_echec_du_demarrage_arrete_le_thread_et_la_boucle(monkeypatch):
    async def ouvrir(self):
        raise OSError("le serveur ne démarre pas")

    monkeypatch.setattr(mcp_client._SessionPersistante, "_ouvrir", ouvrir)

    with pytest.raises(OSError):
        mcp_client._SessionPersistante("support", "kiabi")

    fil = _fil("mcp-kiabi-support")
    fil.join(timeout=10)
    assert not fil.is_alive()


def test_une_vraie_session_qui_leve_a_l_appel_est_arretee(monkeypatch):
    async def ouvrir(self):
        self._outils = ["check_stock"]

    async def appeler(self, tool, arguments):
        raise ConnectionError("tube fermé")

    monkeypatch.setattr(mcp_client._SessionPersistante, "_ouvrir", ouvrir)
    monkeypatch.setattr(mcp_client._SessionPersistante, "_appeler", appeler)
    monkeypatch.setattr(mcp_client, "_sessions", {})

    resultat = routage.appeler("kiabi", "check_stock", {}, assertion=None, profil="commercial")
    assert resultat == {"statut": "erreur", "message": "Serveur MCP local indisponible."}
    assert mcp_client._sessions == {}
    fil = _fil("mcp-kiabi-commercial")
    fil.join(timeout=10)
    assert not fil.is_alive()


# --- passerelle : l'erreur de transport arrive dans un ExceptionGroup ---------------------


def _faux_client_qui_leve(monkeypatch, exception):
    import mcp.client.streamable_http as streamable_http

    @contextlib.asynccontextmanager
    async def faux_client(url, headers=None):
        raise exception
        yield  # pragma: no cover — fait de la fonction un générateur

    monkeypatch.setattr(streamable_http, "streamablehttp_client", faux_client)


def test_erreur_de_transport_enveloppee_dans_un_groupe_devient_un_statut_erreur(monkeypatch):
    _faux_client_qui_leve(
        monkeypatch, ExceptionGroup("x", [httpx.ConnectError("jeton-secret-abc injoignable")])
    )
    resultat = passerelle.appeler("jeton-secret-abc", "check_stock", {"ref": "REF-1024"})
    assert resultat["statut"] == "erreur"
    assert "jeton-secret-abc" not in resultat["message"]


def test_groupe_imbrique_contenant_une_panne_de_transport(monkeypatch):
    groupe = ExceptionGroup("externe", [ExceptionGroup("interne", [httpx.ReadTimeout("lent")])])
    _faux_client_qui_leve(monkeypatch, groupe)
    resultat = passerelle.appeler("jeton-abc", "check_stock", {})
    assert resultat["statut"] == "erreur"


def test_groupe_avec_un_statut_http_d_erreur(monkeypatch):
    requete = httpx.Request("POST", "https://mcp.exemple/mcp")
    reponse = httpx.Response(502, request=requete)
    erreur = httpx.HTTPStatusError("502", request=requete, response=reponse)
    _faux_client_qui_leve(monkeypatch, ExceptionGroup("x", [erreur]))
    assert passerelle.appeler("jeton-abc", "check_stock", {})["statut"] == "erreur"


def test_groupe_sans_panne_de_transport_remonte_tel_quel(monkeypatch):
    """Un bogue n'est pas une panne réseau : le masquer par un message poli le cacherait."""
    _faux_client_qui_leve(monkeypatch, ExceptionGroup("x", [ValueError("bogue")]))
    with pytest.raises(ExceptionGroup) as excursion:
        passerelle.appeler("jeton-abc", "check_stock", {})
    assert excursion.group_contains(ValueError)


# --- passerelle : une URL vide n'est pas « pas d'URL » ------------------------------------


def test_une_url_vide_ne_retombe_pas_sur_sorabel(monkeypatch):
    import mcp.client.streamable_http as streamable_http

    class _Arret(Exception):
        pass

    vues = []

    @contextlib.asynccontextmanager
    async def faux_client(url, headers=None):
        vues.append(url)
        raise _Arret
        yield  # pragma: no cover

    monkeypatch.setattr(streamable_http, "streamablehttp_client", faux_client)
    monkeypatch.setattr(passerelle, "URL_MCP", "https://sorabel.exemple/mcp")

    async def consommer(url):
        with pytest.raises(_Arret):
            async for _ in passerelle._session("jeton-abc", url):
                pass

    asyncio.run(consommer(""))
    asyncio.run(consommer(None))
    assert vues == ["", "https://sorabel.exemple/mcp"]
