"""Construction du serveur MCP : résolution du profil (SEUL point dépendant du transport),
chargement et validation de la matrice au démarrage. Depuis la Task 4, l'enregistrement des
tools n'est plus filtré par profil (cf. mcp_server.tools) : ce fichier ne teste donc plus le
filtrage de tools/list, seulement la résolution du profil et la validation de la matrice."""

import asyncio
import json

import pytest

from gouvernance.perimetre import ProfilInconnu
from gouvernance.seed import peupler
from mcp_server.serveur import construire_serveur, resoudre_profil_stdio


def test_resoudre_profil_leve_si_variable_absente(monkeypatch):
    monkeypatch.delenv("SORABEL_PROFIL", raising=False)
    with pytest.raises(RuntimeError, match="SORABEL_PROFIL"):
        resoudre_profil_stdio()


def test_resoudre_profil_lit_la_variable_denvironnement(monkeypatch):
    monkeypatch.setenv("SORABEL_PROFIL", "commercial")
    assert resoudre_profil_stdio() == "commercial"


def test_construire_serveur_enregistre_toujours_les_huit_tools(tmp_path, monkeypatch):
    """Depuis la Task 4, l'enregistrement n'est plus filtré par profil : les 8 tools sont
    toujours enregistrés, et c'est le décorateur de mcp_server.tools qui refuse à l'appel
    (ask_database reste hors de portée du profil dev, mais le tool existe désormais)."""
    chemin_gouvernance = tmp_path / "gouvernance.db"
    peupler(chemin_gouvernance)
    monkeypatch.setenv("SORABEL_PROFIL", "dev")

    mcp = construire_serveur(chemin_gouvernance_db=chemin_gouvernance)

    noms = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "ask_database" in noms
    assert "search_docs" in noms
    assert len(noms) == 8


def test_construire_serveur_profil_inconnu_leve(tmp_path, monkeypatch):
    chemin_gouvernance = tmp_path / "gouvernance.db"
    peupler(chemin_gouvernance)
    monkeypatch.setenv("SORABEL_PROFIL", "stagiaire")

    with pytest.raises(ProfilInconnu):
        construire_serveur(chemin_gouvernance_db=chemin_gouvernance)


def test_en_stdio_le_profil_vient_de_la_variable_d_environnement(monkeypatch, tmp_path):
    from gouvernance.seed import peupler
    from mcp_server.serveur import construire_serveur

    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    monkeypatch.setenv("SORABEL_TRANSPORT", "stdio")
    monkeypatch.setenv("SORABEL_PROFIL", "support")
    serveur = construire_serveur(chemin)
    assert serveur is not None


def test_en_http_la_variable_de_profil_est_ignoree(monkeypatch, tmp_path):
    """Accepter SORABEL_PROFIL en HTTP rouvrirait exactement la faille qu'on ferme :
    l'appelant qui déclare son identité."""
    from gouvernance.seed import peupler
    from mcp_server.serveur import resoudre_profil_http

    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    monkeypatch.setenv("SORABEL_TRANSPORT", "http")
    monkeypatch.setenv("SORABEL_PROFIL", "admin")

    from gouvernance.identites import DepotIdentitesSqlite
    depot = DepotIdentitesSqlite(chemin)

    with pytest.raises(PermissionError, match="aucun profil"):
        resoudre_profil_http(depot, sujet="sub-inconnu")


def test_en_http_le_profil_vient_du_depot(monkeypatch, tmp_path):
    from gouvernance.identites import DepotIdentitesSqlite
    from gouvernance.seed import peupler
    from mcp_server.serveur import resoudre_profil_http

    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    depot = DepotIdentitesSqlite(chemin)
    depot.attribuer("sub-123", "support", source="demo")
    assert resoudre_profil_http(depot, sujet="sub-123") == "support"


# --- Choix du dépôt d'identités en HTTP selon SORABEL_DEPOT (§5 de la conception GCP) ------
#
# Firestore est lu par le serveur MCP et lu/écrit par le front — jamais l'inverse. Le bug
# corrigé ici : construire_serveur() instanciait toujours DepotIdentitesSqlite, quelle que
# soit SORABEL_DEPOT, si bien qu'en production le serveur ne voyait jamais les attributions
# de profil écrites par le front dans Firestore (chaque appel de tool échouait en
# `non_autorise`, indéfiniment).
#
# Ces tests passent par construire_serveur() puis un vrai appel de tool (comme
# tests/test_mcp_tools.py), plutôt que par une inspection de `depot` — FastMCP n'expose pas
# cet objet, et il n'a pas sa place dans l'API publique. Le sujet appelant n'existe QUE dans
# l'implémentation attendue (Firestore factice ou SQLite selon le test) : un appel autorisé
# prouve donc, par le comportement, laquelle a été réellement consultée par le résolveur —
# sans jamais construire de vrai firestore.Client() ni toucher le réseau.


class _DocumentFirestoreFactice:
    def __init__(self, magasin, identifiant):
        self._magasin, self._id = magasin, identifiant

    def get(self):
        return _InstantaneFirestoreFactice(self._magasin.get(self._id))


class _InstantaneFirestoreFactice:
    def __init__(self, donnees):
        self._donnees = donnees

    @property
    def exists(self):
        return self._donnees is not None

    def to_dict(self):
        return self._donnees


class _ClientFirestoreFactice:
    """Même patron que tests/test_gouvernance_identites_firestore.py : un magasin en
    mémoire, aucun réseau. `magasin` est pré-rempli par le test, jamais écrit ici."""

    def __init__(self, magasin):
        self._magasin = magasin

    def collection(self, _nom):
        return self  # un seul magasin suffit, la collection ne sert qu'à documenter l'appel

    def document(self, identifiant):
        return _DocumentFirestoreFactice(self._magasin, identifiant)


def _definir_environnement_http_minimal(monkeypatch):
    """Variables requises par construire_serveur() en HTTP, hors SORABEL_DEPOT : émetteur,
    audience et URL publique factices — aucune n'est appelée (le jeton est simulé via le
    contexte d'authentification, jamais vérifié)."""
    monkeypatch.setenv("SORABEL_TRANSPORT", "http")
    monkeypatch.setenv("SORABEL_OIDC_ISSUER", "https://issuer.exemple.test")
    monkeypatch.setenv("SORABEL_OIDC_AUDIENCE", "sorabel-test")
    monkeypatch.setenv("SORABEL_OIDC_JWKS", "https://issuer.exemple.test/jwks")
    monkeypatch.setenv("SORABEL_URL_PUBLIQUE", "https://mcp.exemple.test")
    monkeypatch.delenv("SORABEL_PROFIL", raising=False)


def _appeler_en_tant_que(mcp, sujet: str, nom_tool: str, arguments: dict) -> dict:
    """Simule un appel de tool authentifié : pose le sujet dans le contexte d'authentification
    que `resoudre_profil_http` consulte via get_access_token(), comme le ferait le middleware
    HTTP réel à réception d'un jeton vérifié."""
    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    utilisateur = AuthenticatedUser(AccessToken(token="t", client_id="c", scopes=[], subject=sujet))
    jeton_ctx = auth_context_var.set(utilisateur)
    try:
        blocs = asyncio.run(mcp.call_tool(nom_tool, arguments))
    finally:
        auth_context_var.reset(jeton_ctx)
    return json.loads(blocs[0].text)


def test_en_http_avec_sorabel_depot_firestore_le_serveur_consulte_firestore(monkeypatch, tmp_path):
    """SORABEL_DEPOT=firestore (celle que cloudbuild.yaml fixe sur deploy-mcp) doit faire
    consulter Firestore par le résolveur — pas la copie SQLite figée dans l'image. Le
    sujet n'existe QUE dans le magasin Firestore factice, jamais dans gouvernance.db : si le
    tool réussit, c'est nécessairement Firestore qui a été consulté."""
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)  # gouvernance.db reste vierge de toute identité : voir le commentaire ci-dessus

    _definir_environnement_http_minimal(monkeypatch)
    monkeypatch.setenv("SORABEL_DEPOT", "firestore")

    magasin = {"sub-firestore": {"profil": "support", "source": "demo"}}
    monkeypatch.setattr(
        "google.cloud.firestore.Client", lambda: _ClientFirestoreFactice(magasin)
    )

    mcp = construire_serveur(chemin_gouvernance_db=chemin)

    resultat = _appeler_en_tant_que(mcp, "sub-firestore", "get_schema", {})
    assert resultat["statut"] == "ok"

    # Une identité absente du magasin Firestore reste refusée : la bascule ne désactive pas
    # la gouvernance, elle change seulement où le profil est lu.
    refus = _appeler_en_tant_que(mcp, "sub-jamais-vu", "get_schema", {})
    assert refus["statut"] == "non_autorise"


@pytest.mark.parametrize("valeur_depot", [None, "sqlite", "autre-chose"])
def test_en_http_sans_sorabel_depot_firestore_le_serveur_reste_sur_sqlite(
    monkeypatch, tmp_path, valeur_depot
):
    """Comportement actuel inchangé : sans SORABEL_DEPOT=firestore (absente, ou toute autre
    valeur), le résolveur continue de lire gouvernance.db — jamais Firestore. Si le code
    tentait malgré tout de construire un firestore.Client(), ce test échouerait au premier
    appel réseau réel (aucun monkeypatch n'est posé ici)."""
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    from gouvernance.identites import DepotIdentitesSqlite

    DepotIdentitesSqlite(chemin).attribuer("sub-sqlite", "support", source="demo")

    _definir_environnement_http_minimal(monkeypatch)
    if valeur_depot is None:
        monkeypatch.delenv("SORABEL_DEPOT", raising=False)
    else:
        monkeypatch.setenv("SORABEL_DEPOT", valeur_depot)

    mcp = construire_serveur(chemin_gouvernance_db=chemin)

    resultat = _appeler_en_tant_que(mcp, "sub-sqlite", "get_schema", {})
    assert resultat["statut"] == "ok"
