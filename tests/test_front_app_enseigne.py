"""Le poste de travail multi-enseigne en MODE LOCAL, rendu par `streamlit.testing` sans
serveur MCP réel.

Tout ce fichier tourne avec `SORABEL_FRONT_LOCAL=1` (fixture `local`) : il vérifie le choix
d'enseigne qui précède l'inscription, l'habillage aux couleurs et textes de l'enseigne, le
rendu inchangé quand une seule enseigne est servie, et que tout appel de tool part par
`front.routage.appeler` avec l'enseigne de session — jamais vers le pipeline.

Le parcours de production (IAP, assertion relayée, URL de chaque enseigne) est vérifié dans
`tests/test_front_app_iap.py` : ce fichier-ci n'en dit rien.

Le dépôt d'identités et la matrice sont remplacés par des doublures : la base réelle
`gouvernance/gouvernance.db` n'est ni lue ni modifiée.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit import config as config_streamlit
from streamlit.testing.v1 import AppTest

import front.depot
import front.routage
from front.routage import SUJET_LOCAL

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = RACINE / "front" / "app_client.py"

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

    def __init__(self, profils: dict[str, str] | None = None):
        self.profils = dict(profils or {})

    def profil_de(self, sujet: str) -> str | None:
        return self.profils.get(sujet)

    def attribuer(self, sujet: str, profil: str, source: str) -> None:
        self.profils[sujet] = profil


@pytest.fixture
def appels(monkeypatch):
    """Doublure de `front.routage.appeler` : enregistre l'appel, ne joint aucun serveur."""
    enregistres = []

    def appeler(enseigne, tool, arguments, *, assertion, profil):
        enregistres.append(
            {"enseigne": enseigne, "tool": tool, "assertion": assertion, "profil": profil}
        )
        return {"statut": "erreur", "message": "doublure de test"}

    monkeypatch.setattr(front.routage, "appeler", appeler)
    return enregistres


@pytest.fixture
def depot(monkeypatch):
    memoire = DepotMemoire()
    monkeypatch.setattr(front.depot, "depot_identites", lambda: memoire)
    monkeypatch.setattr(front.depot, "tools_accordes", lambda profil: TOUS_LES_TOOLS)
    return memoire


@pytest.fixture
def adresse_boucle_locale():
    """`make front` lance Streamlit avec `--server.address=127.0.0.1` ; AppTest n'a pas de
    ligne de commande, on pose donc l'option elle-même — et on la restaure."""
    avant = config_streamlit.get_option("server.address")
    config_streamlit.set_option("server.address", "127.0.0.1")
    yield
    config_streamlit.set_option("server.address", avant)


@pytest.fixture
def local(monkeypatch, depot, appels, adresse_boucle_locale):
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    monkeypatch.delenv("K_SERVICE", raising=False)
    return depot


@pytest.fixture
def iap(monkeypatch, depot, appels):
    monkeypatch.delenv("SORABEL_FRONT_LOCAL", raising=False)
    monkeypatch.delenv("SORABEL_URL_MCP_KIABI", raising=False)
    return depot


def lancer() -> AppTest:
    application = AppTest.from_file(str(SCRIPT), default_timeout=30)
    application.run()
    assert not application.exception, [e.value for e in application.exception]
    return application


def textes(application: AppTest) -> str:
    """Tout le texte rendu, barre latérale comprise : on cherche une chaîne, pas un widget."""
    morceaux = []
    for famille in ("markdown", "caption", "info", "warning", "error", "subheader"):
        morceaux.extend(str(element.value) for element in getattr(application, famille))
    return "\n".join(morceaux)


def boutons(application: AppTest) -> set[str]:
    return {bouton.key for bouton in application.button if bouton.key}


# --- une seule enseigne servie ----------------------------------------------------------
# Les tests de ce paragraphe tournent en mode local (fixture `local`) : ils prouvent que le
# rendu Sorabel ne change pas quand une seule enseigne est servie, pas le parcours IAP, qui
# est dans `tests/test_front_app_iap.py`. Sans en-tête IAP, seule la garde ci-dessous se
# vérifie sans doublure d'identité.


def test_iap_sans_entete_affiche_session_non_authentifiee(iap):
    application = lancer()
    assert any("Session non authentifiée" in info.value for info in application.info)
    assert "Choisir une enseigne" not in textes(application)


def test_une_seule_enseigne_servie_ne_montre_aucune_page_de_choix(local, monkeypatch):
    monkeypatch.setattr(front.routage, "enseignes_servies", lambda: ["sorabel"])
    application = lancer()
    rendu = textes(application)
    assert "Choisir une enseigne" not in rendu
    # Directement l'inscription, aux textes Sorabel d'origine.
    assert "Bienvenue sur la Sorabel Data Gateway" in rendu
    assert application.session_state["enseigne"] == "sorabel"


def test_une_seule_enseigne_garde_le_rendu_sorabel(local, monkeypatch):
    monkeypatch.setattr(front.routage, "enseignes_servies", lambda: ["sorabel"])
    local.attribuer(SUJET_LOCAL, "commercial", source="test")
    application = lancer()
    rendu = textes(application)
    assert "### Sorabel Data Gateway" in rendu
    assert "--accent:       #2563EB;" in rendu
    assert "linear-gradient(185deg, #0D1526 0%" in rendu
    # Teintes dérivées de l'accent : celles de la feuille Sorabel d'origine.
    assert "--accent-fonce: #1D4ED8;" in rendu
    assert "rgba(37,99,235,.16)" in rendu
    assert "<span class='valeur'>400 documents indexés</span>" in rendu
    # Ni bascule d'enseigne ni bandeau d'avertissement : rien à changer, rien à signaler.
    assert "btn_enseigne" not in boutons(application)
    assert not application.warning
    assert application.text_input(key="ref_produit").placeholder == "REF-8842"
    assert {"ex_REF-8842", "ex_REF-1024", "ex_REF-5719", "ex_REF-3764"} <= boutons(application)


# --- mode local, deux enseignes ---------------------------------------------------------


def test_mode_local_deux_enseignes_affiche_la_page_de_choix(local):
    application = lancer()
    rendu = textes(application)
    assert "Choisir une enseigne" in rendu
    assert "Sorabel" in rendu and "Kiabi" in rendu
    assert {"enseigne_sorabel", "enseigne_kiabi"} <= boutons(application)
    # Le choix précède l'inscription : aucun profil ne se choisit avant l'enseigne.
    assert "Bienvenue sur la" not in rendu


def test_choisir_kiabi_habille_l_inscription_aux_textes_kiabi(local):
    application = lancer()
    application.button(key="enseigne_kiabi").click().run()
    assert not application.exception
    rendu = textes(application)
    assert application.session_state["enseigne"] == "kiabi"
    assert "Bienvenue sur la Kiabi Data Gateway" in rendu
    assert any("données entièrement fictives" in w.value for w in application.warning)
    assert "Choisir une enseigne" not in rendu


def test_poste_kiabi_porte_nom_couleurs_mention_et_exemples(local):
    local.attribuer(SUJET_LOCAL, "commercial", source="test")
    application = AppTest.from_file(str(SCRIPT), default_timeout=30)
    application.session_state["enseigne"] = "kiabi"
    application.run()
    assert not application.exception
    rendu = textes(application)
    assert "### Kiabi Data Gateway" in rendu
    assert "--accent:       #1E5BC6;" in rendu
    assert "linear-gradient(185deg, #0B2E6B 0%" in rendu
    # L'habillage va jusqu'aux ombres et au focus : plus aucun bleu Sorabel.
    assert "rgba(30,91,198,.16)" in rendu
    assert "#1D4ED8" not in rendu and "37,99,235" not in rendu
    assert "<span class='valeur'>175 documents indexés</span>" in rendu
    assert "400 documents" not in rendu
    assert any("données entièrement fictives" in w.value for w in application.warning)
    assert application.text_input(key="ref_produit").placeholder == "REF-1024"
    assert "ex_REF-1141" in boutons(application)
    assert "btn_enseigne" in boutons(application)


def test_changer_d_enseigne_ramene_a_la_page_de_choix(local):
    local.attribuer(SUJET_LOCAL, "commercial", source="test")
    application = AppTest.from_file(str(SCRIPT), default_timeout=30)
    application.session_state["enseigne"] = "kiabi"
    application.run()
    application.button(key="btn_enseigne").click().run()
    assert not application.exception
    assert "Choisir une enseigne" in textes(application)
    # Le profil, commun à toutes les enseignes, n'est pas perdu : en re-choisissant une
    # enseigne, on retombe directement sur le poste, sans repasser par l'inscription.
    assert local.profil_de(SUJET_LOCAL) == "commercial"
    application.button(key="enseigne_sorabel").click().run()
    assert not application.exception
    rendu = textes(application)
    assert application.session_state["enseigne"] == "sorabel"
    assert "btn_produit" in boutons(application)
    assert "Bienvenue sur la" not in rendu
    assert "### Sorabel Data Gateway" in rendu


def test_les_appels_partent_par_le_routage_avec_l_enseigne_de_session(local, appels):
    local.attribuer(SUJET_LOCAL, "support", source="test")
    application = AppTest.from_file(str(SCRIPT), default_timeout=30)
    application.session_state["enseigne"] = "kiabi"
    application.run()
    assert appels == []  # aucun tool appelé tant que l'utilisateur n'a rien demandé
    application.text_input(key="ref_produit").input("REF-1024")
    application.button(key="btn_produit").click().run()
    assert not application.exception
    assert [a["tool"] for a in appels] == ["check_stock", "ask_database", "answer_question"]
    assert all(a["enseigne"] == "kiabi" for a in appels)
    # Sans IAP, pas d'assertion à relayer : c'est le profil qui fixe la matrice du serveur.
    assert all(a["assertion"] is None and a["profil"] == "support" for a in appels)
    # La doublure renvoie une panne : elle s'affiche comme telle, jamais comme un refus.
    assert any("Incident technique" in e.value or "doublure" in e.value for e in application.error)


def test_k_service_interdit_le_mode_local(local, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "sorabel-front")
    application = AppTest.from_file(str(SCRIPT), default_timeout=30)
    application.run()
    assert application.exception
    assert "Cloud Run" in application.exception[0].value


@pytest.mark.parametrize("adresse", [None, "", "0.0.0.0", "::", "192.168.1.20"])
def test_mode_local_refuse_d_ecouter_hors_de_la_boucle_locale(local, adresse):
    """Sans IAP, le profil se choisit à l'écran : un poste joignable du réseau le donnerait
    à n'importe qui. `server.address` non posée = toutes les interfaces."""
    config_streamlit.set_option("server.address", adresse)
    application = AppTest.from_file(str(SCRIPT), default_timeout=30)
    application.run()
    assert not application.exception
    assert any("--server.address=127.0.0.1" in e.value for e in application.error)
    rendu = textes(application)
    assert "Choisir une enseigne" not in rendu
    assert "Bienvenue sur la" not in rendu
    assert not application.button


@pytest.mark.parametrize("adresse", ["127.0.0.1", "localhost", "::1"])
def test_mode_local_accepte_les_adresses_de_boucle_locale(local, adresse):
    config_streamlit.set_option("server.address", adresse)
    application = lancer()
    assert not application.error
    assert "Choisir une enseigne" in textes(application)


def test_hors_mode_local_l_adresse_d_ecoute_n_est_pas_controlee(iap):
    """En production, Cloud Run écoute sur 0.0.0.0 derrière IAP : le garde-fou ne vaut que
    pour le mode local, qui contourne IAP."""
    config_streamlit.set_option("server.address", "0.0.0.0")
    try:
        application = lancer()
    finally:
        config_streamlit.set_option("server.address", None)
    assert not any("--server.address" in e.value for e in application.error)


# --- garde-fous statiques ---------------------------------------------------------------


def test_le_poste_n_a_aucun_chemin_direct_vers_le_pipeline():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "sorabel_rag" not in source and "sorabel_sql" not in source
    # Les vues passent par `appeler` du module, donc par `front.routage` : un import de
    # `passerelle.appeler` contournerait le choix d'enseigne.
    assert "import appeler" not in source
    assert "passerelle.appeler(" not in source
