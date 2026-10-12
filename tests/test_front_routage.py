"""Routage du front vers le serveur MCP de chaque enseigne.

Le routeur ne décide d'aucun droit : il choisit seulement *quel* serveur MCP interroger. La
matrice d'accès reste appliquée par ce serveur, en stdio (mode local) comme en HTTP. Aucun
test ne joint le réseau ni ne lance de sous-processus : les deux ponts sont remplacés par
des doublures qui enregistrent leurs arguments.
"""

import asyncio
import contextlib

import pytest

from front import mcp_client, passerelle, routage

VARIABLES = (
    "SORABEL_FRONT_LOCAL",
    "K_SERVICE",
    "SORABEL_URL_MCP_SORABEL",
    "SORABEL_URL_MCP_KIABI",
)


@pytest.fixture(autouse=True)
def environnement_neutre(monkeypatch):
    """Un shell de développement peut avoir exporté l'une de ces variables : chaque test
    part d'un environnement de production Sorabel, puis pose ce qu'il vérifie."""
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(routage, "enseignes_disponibles", lambda: ["kiabi", "sorabel"])


@pytest.fixture
def ponts(monkeypatch):
    """Remplace les deux ponts par des doublures ; renvoie les appels reçus par chacun."""
    appels = {"local": [], "http": []}

    def faux_local(profil, tool, arguments, enseigne=None):
        appels["local"].append(
            {"profil": profil, "tool": tool, "arguments": arguments, "enseigne": enseigne}
        )
        return {"statut": "ok", "pont": "local"}

    def faux_http(assertion, tool, arguments, url=None):
        appels["http"].append(
            {"assertion": assertion, "tool": tool, "arguments": arguments, "url": url}
        )
        return {"statut": "ok", "pont": "http"}

    monkeypatch.setattr(mcp_client, "appeler", faux_local)
    monkeypatch.setattr(passerelle, "appeler", faux_http)
    return appels


# --- mode_local ---------------------------------------------------------------------------


def test_mode_local_faux_par_defaut():
    assert routage.mode_local() is False


def test_mode_local_vrai_si_la_variable_vaut_1(monkeypatch):
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    assert routage.mode_local() is True


def test_mode_local_faux_pour_toute_autre_valeur(monkeypatch):
    # Seul "1" active le contournement d'IAP : "true" ou "oui" ne doivent pas l'ouvrir par
    # accident.
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "true")
    assert routage.mode_local() is False


def test_mode_local_interdit_sur_cloud_run(monkeypatch):
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    monkeypatch.setenv("K_SERVICE", "sorabel-front")
    with pytest.raises(RuntimeError):
        routage.mode_local()


def test_k_service_seul_ne_change_rien(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "sorabel-front")
    assert routage.mode_local() is False


# --- enseignes_servies --------------------------------------------------------------------


def test_en_local_toutes_les_enseignes_disponibles_sont_servies(monkeypatch):
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    assert routage.enseignes_servies() == ["sorabel", "kiabi"]


def test_en_http_sans_url_kiabi_seule_sorabel_est_servie():
    assert routage.enseignes_servies() == ["sorabel"]


def test_en_http_avec_url_kiabi_les_deux_sont_servies(monkeypatch):
    monkeypatch.setenv("SORABEL_URL_MCP_KIABI", "https://kiabi.exemple/mcp")
    assert routage.enseignes_servies() == ["sorabel", "kiabi"]


def test_image_de_production_ne_sert_que_sorabel(monkeypatch):
    """L'image de prod ne contient que enseignes/sorabel : une variable Kiabi égarée dans
    la configuration Cloud Run ne fait pas apparaître d'enseigne qui n'existe pas."""
    monkeypatch.setattr(routage, "enseignes_disponibles", lambda: ["sorabel"])
    monkeypatch.setenv("SORABEL_URL_MCP_KIABI", "https://kiabi.exemple/mcp")
    assert routage.enseignes_servies() == ["sorabel"]


def test_tri_alphabetique_apres_sorabel(monkeypatch):
    monkeypatch.setattr(
        routage, "enseignes_disponibles", lambda: ["zeta", "alpha", "sorabel", "kiabi"]
    )
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    assert routage.enseignes_servies() == ["sorabel", "alpha", "kiabi", "zeta"]


def test_sans_sorabel_disponible_le_tri_reste_alphabetique(monkeypatch):
    monkeypatch.setattr(routage, "enseignes_disponibles", lambda: ["kiabi", "alpha"])
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    assert routage.enseignes_servies() == ["alpha", "kiabi"]


# --- url_mcp ------------------------------------------------------------------------------


def test_url_sorabel_par_defaut_est_celle_de_la_passerelle(monkeypatch):
    monkeypatch.setattr(passerelle, "URL_MCP", "https://sorabel.exemple/mcp")
    assert routage.url_mcp("sorabel") == "https://sorabel.exemple/mcp"


def test_url_sorabel_surchargeable_par_variable(monkeypatch):
    monkeypatch.setenv("SORABEL_URL_MCP_SORABEL", "https://autre.exemple/mcp")
    assert routage.url_mcp("sorabel") == "https://autre.exemple/mcp"


def test_url_kiabi_lue_dans_sa_variable(monkeypatch):
    monkeypatch.setenv("SORABEL_URL_MCP_KIABI", "https://kiabi.exemple/mcp")
    assert routage.url_mcp("kiabi") == "https://kiabi.exemple/mcp"


def test_url_kiabi_sans_variable_ne_retombe_pas_sur_sorabel():
    # Un repli sur l'URL Sorabel enverrait une question Kiabi aux données Sorabel.
    with pytest.raises(ValueError):
        routage.url_mcp("kiabi")


def test_url_d_une_enseigne_inconnue_leve_value_error():
    with pytest.raises(ValueError):
        routage.url_mcp("inconnue")


# --- appeler ------------------------------------------------------------------------------


def test_en_local_l_appel_passe_par_le_serveur_mcp_stdio(monkeypatch, ponts):
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    resultat = routage.appeler(
        "kiabi", "check_stock", {"ref": "K-001"}, assertion=None, profil="commercial"
    )
    assert resultat["pont"] == "local"
    assert ponts["local"] == [
        {
            "profil": "commercial",
            "tool": "check_stock",
            "arguments": {"ref": "K-001"},
            "enseigne": "kiabi",
        }
    ]
    assert ponts["http"] == []


def test_en_http_l_appel_vise_l_url_de_l_enseigne(monkeypatch, ponts):
    monkeypatch.setenv("SORABEL_URL_MCP_KIABI", "https://kiabi.exemple/mcp")
    resultat = routage.appeler(
        "kiabi", "check_stock", {"ref": "K-001"}, assertion="jeton-abc", profil=None
    )
    assert resultat["pont"] == "http"
    assert ponts["http"] == [
        {
            "assertion": "jeton-abc",
            "tool": "check_stock",
            "arguments": {"ref": "K-001"},
            "url": "https://kiabi.exemple/mcp",
        }
    ]
    assert ponts["local"] == []


def test_en_http_sorabel_garde_l_url_de_production(monkeypatch, ponts):
    monkeypatch.setattr(passerelle, "URL_MCP", "https://sorabel.exemple/mcp")
    routage.appeler("sorabel", "get_schema", {}, assertion="jeton-abc", profil=None)
    assert ponts["http"][0]["url"] == "https://sorabel.exemple/mcp"


def test_enseigne_non_servie_renvoie_une_erreur_sans_contacter_personne(ponts):
    # Kiabi est disponible mais sans URL : en HTTP, elle n'est pas servie.
    resultat = routage.appeler(
        "kiabi", "check_stock", {"ref": "K-001"}, assertion="jeton-abc", profil=None
    )
    assert resultat["statut"] == "erreur"
    assert "kiabi" in resultat["message"]
    assert ponts == {"local": [], "http": []}


def test_enseigne_inconnue_renvoie_une_erreur_meme_en_local(monkeypatch, ponts):
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    resultat = routage.appeler("inconnue", "get_schema", {}, assertion=None, profil="dev")
    assert resultat["statut"] == "erreur"
    assert ponts == {"local": [], "http": []}


def test_en_local_sans_profil_l_appel_est_refuse_sans_lancer_de_serveur(monkeypatch, ponts):
    monkeypatch.setenv("SORABEL_FRONT_LOCAL", "1")
    resultat = routage.appeler("sorabel", "get_schema", {}, assertion=None, profil=None)
    assert resultat["statut"] == "non_autorise"
    assert ponts["local"] == []


def test_sujet_local_identifie_le_developpeur():
    assert routage.SUJET_LOCAL == "local:developpeur"


def test_le_routeur_n_importe_pas_le_pipeline():
    """Le front n'a aucun chemin direct vers le RAG ou le SQL : tout passe par un serveur
    MCP, qui applique la matrice et journalise."""
    import ast
    from pathlib import Path

    arbre = ast.parse(Path(routage.__file__).read_text(encoding="utf-8"))
    modules = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(alias.name for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            modules.add(noeud.module)
    assert not any(m.split(".")[0] in {"sorabel_rag", "sorabel_sql"} for m in modules)


# --- passerelle : l'URL descend jusqu'à la session HTTP -----------------------------------


def test_passerelle_transmet_l_url_au_distant(monkeypatch):
    vus = []

    async def faux_distant(assertion, tool, arguments, url=None):
        vus.append(url)
        return {"statut": "ok"}

    monkeypatch.setattr(passerelle, "_appeler_distant", faux_distant)
    passerelle.appeler("jeton-abc", "get_schema", {}, url="https://kiabi.exemple/mcp")
    passerelle.appeler("jeton-abc", "get_schema", {})
    assert vus == ["https://kiabi.exemple/mcp", None]


def test_session_http_vise_l_url_donnee_sinon_celle_de_production(monkeypatch):
    import mcp.client.streamable_http as streamable_http

    class _Arret(Exception):
        pass

    vues = []

    @contextlib.asynccontextmanager
    async def faux_client(url, headers=None):
        vues.append(url)
        raise _Arret
        yield  # pragma: no cover — fait de la fonction un générateur

    monkeypatch.setattr(streamable_http, "streamablehttp_client", faux_client)
    monkeypatch.setattr(passerelle, "URL_MCP", "https://sorabel.exemple/mcp")

    async def consommer(url):
        with pytest.raises(_Arret):
            async for _ in passerelle._session("jeton-abc", url):
                pass

    asyncio.run(consommer("https://kiabi.exemple/mcp"))
    asyncio.run(consommer(None))
    assert vues == ["https://kiabi.exemple/mcp", "https://sorabel.exemple/mcp"]


# --- mcp_client : l'enseigne descend jusqu'au sous-processus ------------------------------


def test_parametres_posent_l_enseigne_et_heritent_de_l_environnement(monkeypatch):
    monkeypatch.setenv("SORABEL_TEST_HERITAGE", "present")
    parametres = mcp_client._parametres("commercial", "kiabi")
    assert parametres.env["SORABEL_ENSEIGNE"] == "kiabi"
    assert parametres.env["SORABEL_PROFIL"] == "commercial"
    # Piège Windows (WinError 10106) : sans héritage, SYSTEMROOT et PATH manquent.
    assert parametres.env["SORABEL_TEST_HERITAGE"] == "present"


def test_parametres_sans_enseigne_restent_ceux_d_avant(monkeypatch):
    monkeypatch.setenv("SORABEL_TEST_HERITAGE", "present")
    parametres = mcp_client._parametres("support")
    import os

    assert parametres.env == {**os.environ, "SORABEL_PROFIL": "support"}


def test_politique_proactor_conservee_sous_windows():
    """Vérifié dans le source plutôt qu'à l'exécution : la politique courante dépend de ce
    que les autres tests ont importé, et ce piège doit rester gardé même hors Windows."""
    from pathlib import Path

    source = Path(mcp_client.__file__).read_text(encoding="utf-8")
    assert 'if sys.platform == "win32":' in source
    assert "asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())" in source


def test_sessions_indexees_par_profil_et_enseigne(monkeypatch):
    creees = []

    class FausseSession:
        def __init__(self, profil, enseigne=None):
            creees.append((profil, enseigne))
            self.profil, self.enseigne = profil, enseigne

        def appeler(self, tool, arguments):
            return {"statut": "ok", "profil": self.profil, "enseigne": self.enseigne}

        def outils(self):
            return ["get_schema"]

    monkeypatch.setattr(mcp_client, "_SessionPersistante", FausseSession)
    monkeypatch.setattr(mcp_client, "_sessions", {})

    assert mcp_client.appeler("commercial", "get_schema", {}, enseigne="kiabi")["enseigne"] == "kiabi"
    assert mcp_client.appeler("commercial", "get_schema", {})["enseigne"] is None
    mcp_client.appeler("commercial", "get_schema", {}, enseigne="kiabi")
    assert mcp_client.lister_tools("commercial", enseigne="kiabi") == ["get_schema"]
    # Une session Kiabi et une session sans enseigne, chacune ouverte une seule fois.
    assert creees == [("commercial", "kiabi"), ("commercial", None)]
