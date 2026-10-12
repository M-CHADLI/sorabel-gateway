"""Le poste de travail en MODE PRODUCTION (IAP, transport HTTP), rendu par `streamlit.testing`.

`tests/test_front_app_enseigne.py` tourne en mode local ; celui-ci est le seul à vérifier le
parcours de production : l'assertion IAP lue dans l'en-tête est relayée telle quelle à
chaque appel, vers l'URL du serveur MCP de l'enseigne de session — jamais celle d'une autre.

Aucun réseau : `front.passerelle.appeler` est remplacée par une doublure qui enregistre
l'assertion et l'URL reçues. L'assertion et le sujet sont posés en remplaçant
`assertion_iap` et `sujet_du_jeton` ; le dépôt d'identités est en mémoire.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import front.depot
import front.passerelle
import front.routage

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = RACINE / "front" / "app_client.py"

ASSERTION = "jeton"
SUJET = "iap:utilisateur"
URL_SORABEL = "https://sorabel.exemple/mcp"
URL_KIABI = "https://kiabi.exemple/mcp"

TOUS_LES_TOOLS = frozenset(
    {
        "search_docs",
        "answer_question",
        "get_document",
        "list_sources",
        "ask_database",
        "get_schema",
        "check_stock",
        "order_status",
    }
)


class DepotMemoire:
    """Même contrat que `DepotIdentitesSqlite`, en mémoire."""

    def __init__(self):
        self.profils: dict[str, str] = {}

    def profil_de(self, sujet):
        return self.profils.get(sujet)

    def attribuer(self, sujet, profil, source):
        self.profils[sujet] = profil


class Appels(list):
    """Liste des appels reçus par la passerelle, qui porte aussi le dépôt en mémoire."""

    def __init__(self, depot: DepotMemoire):
        super().__init__()
        self.depot = depot


@pytest.fixture
def appels_http(monkeypatch):
    """Production : IAP présent, aucun mode local, un dépôt en mémoire, une passerelle
    doublée. Renvoie la liste des appels reçus par la passerelle."""
    for variable in ("SORABEL_FRONT_LOCAL", "K_SERVICE", "SORABEL_URL_MCP_KIABI",
                     "SORABEL_URL_MCP_SORABEL"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(front.passerelle, "assertion_iap", lambda: ASSERTION)
    monkeypatch.setattr(front.passerelle, "sujet_du_jeton", lambda assertion: SUJET)
    monkeypatch.setattr(front.passerelle, "URL_MCP", URL_SORABEL)
    memoire = DepotMemoire()
    monkeypatch.setattr(front.depot, "depot_identites", lambda: memoire)
    monkeypatch.setattr(front.depot, "tools_accordes", lambda profil: TOUS_LES_TOOLS)

    enregistres = Appels(memoire)

    def appeler(assertion, tool, arguments, url=None):
        enregistres.append({"assertion": assertion, "tool": tool, "url": url})
        return {"statut": "erreur", "message": "doublure de test"}

    monkeypatch.setattr(front.passerelle, "appeler", appeler)
    return enregistres


def textes(application: AppTest) -> str:
    morceaux = []
    for famille in ("markdown", "caption", "info", "warning", "error", "subheader"):
        morceaux.extend(str(element.value) for element in getattr(application, famille))
    return "\n".join(morceaux)


def boutons(application: AppTest) -> set[str]:
    return {bouton.key for bouton in application.button if bouton.key}


def lancer(**etat) -> AppTest:
    application = AppTest.from_file(str(SCRIPT), default_timeout=30)
    for cle, valeur in etat.items():
        application.session_state[cle] = valeur
    application.run()
    assert not application.exception, [e.value for e in application.exception]
    return application


def consulter_un_produit(application: AppTest) -> None:
    application.text_input(key="ref_produit").input("REF-1024")
    application.button(key="btn_produit").click().run()
    assert not application.exception, [e.value for e in application.exception]


# --- une seule enseigne servie : la production Sorabel -----------------------------------


def test_production_sorabel_n_affiche_aucune_page_de_choix(appels_http, monkeypatch):
    monkeypatch.setattr(front.routage, "enseignes_disponibles", lambda: ["sorabel"])
    application = lancer()
    rendu = textes(application)
    assert "Choisir une enseigne" not in rendu
    assert "Bienvenue sur la Sorabel Data Gateway" in rendu
    assert application.session_state["enseigne"] == "sorabel"
    # Le bandeau de démonstration, pas celui du mode local : un IAP authentifie bien la
    # personne, seul son profil est libre.
    assert any("Mode démonstration" in info.value for info in application.info)
    assert not any("Mode local" in info.value for info in application.info)
    assert not application.warning
    assert appels_http == []


def test_production_sorabel_relaie_l_assertion_vers_l_url_de_production(
    appels_http, monkeypatch
):
    monkeypatch.setattr(front.routage, "enseignes_disponibles", lambda: ["sorabel"])
    application = lancer()
    application.button(key="choisir_support").click().run()
    assert not application.exception
    assert appels_http.depot.profil_de(SUJET) == "support"
    # Une fois inscrit : poste Sorabel d'origine, sans bascule d'enseigne.
    assert "### Sorabel Data Gateway" in textes(application)
    assert "btn_enseigne" not in boutons(application)
    assert appels_http == []  # rien n'a été demandé avant la consultation

    consulter_un_produit(application)
    assert [appel["tool"] for appel in appels_http] == [
        "check_stock",
        "ask_database",
        "answer_question",
    ]
    assert all(appel["assertion"] == ASSERTION for appel in appels_http)
    assert all(appel["url"] == front.passerelle.URL_MCP == URL_SORABEL for appel in appels_http)


# --- deux enseignes servies en HTTP -------------------------------------------------------


def test_production_a_deux_enseignes_envoie_kiabi_vers_l_url_kiabi(appels_http, monkeypatch):
    monkeypatch.setattr(front.routage, "enseignes_disponibles", lambda: ["kiabi", "sorabel"])
    monkeypatch.setenv("SORABEL_URL_MCP_KIABI", URL_KIABI)
    appels_http.depot.attribuer(SUJET, "support", source="test")

    application = lancer()
    assert "Choisir une enseigne" in textes(application)
    application.button(key="enseigne_kiabi").click().run()
    assert not application.exception
    assert application.session_state["enseigne"] == "kiabi"

    consulter_un_produit(application)
    assert [appel["tool"] for appel in appels_http] == [
        "check_stock",
        "ask_database",
        "answer_question",
    ]
    assert all(appel["assertion"] == ASSERTION for appel in appels_http)
    assert all(appel["url"] == URL_KIABI for appel in appels_http)


def test_production_a_deux_enseignes_garde_l_url_sorabel_pour_sorabel(appels_http, monkeypatch):
    monkeypatch.setattr(front.routage, "enseignes_disponibles", lambda: ["kiabi", "sorabel"])
    monkeypatch.setenv("SORABEL_URL_MCP_KIABI", URL_KIABI)
    appels_http.depot.attribuer(SUJET, "support", source="test")

    application = lancer(enseigne="sorabel")
    consulter_un_produit(application)
    assert appels_http, "aucun appel enregistré"
    assert all(appel["url"] == URL_SORABEL for appel in appels_http)
    assert all(appel["assertion"] == ASSERTION for appel in appels_http)


def test_production_sans_url_kiabi_ne_propose_pas_kiabi(appels_http, monkeypatch):
    """Kiabi existe dans le dépôt mais n'a pas de serveur : pas de carte, donc aucune
    question Kiabi ne peut partir vers les données Sorabel."""
    monkeypatch.setattr(front.routage, "enseignes_disponibles", lambda: ["kiabi", "sorabel"])
    application = lancer()
    assert application.session_state["enseigne"] == "sorabel"
    assert "Choisir une enseigne" not in textes(application)
    assert "enseigne_kiabi" not in boutons(application)
