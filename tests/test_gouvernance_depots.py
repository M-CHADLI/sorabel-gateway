"""choisir_depot() est le point de passage unique du dispatch SORABEL_DEPOT, partagé par
front/depot.py et mcp_server/serveur.py — voir gouvernance/depots.py.

Comme pour tests/test_gouvernance_identites_firestore.py, aucun appel réseau ni émulateur :
le client Firestore est toujours une doublure en mémoire.
"""

import pytest

from gouvernance.depots import choisir_depot
from gouvernance.identites import DepotIdentitesSqlite
from gouvernance.identites_firestore import DepotIdentitesFirestore
from gouvernance.seed import peupler


class _Document:
    def __init__(self, magasin, identifiant):
        self._magasin, self._id = magasin, identifiant

    def get(self):
        return _Instantane(self._magasin.get(self._id))

    def set(self, donnees):
        self._magasin[self._id] = dict(donnees)


class _Instantane:
    def __init__(self, donnees):
        self._donnees = donnees

    @property
    def exists(self):
        return self._donnees is not None

    def to_dict(self):
        return self._donnees


class _Collection:
    def __init__(self, magasin):
        self._magasin = magasin

    def document(self, identifiant):
        return _Document(self._magasin, identifiant)


class _ClientFactice:
    def __init__(self):
        self.magasin = {}

    def collection(self, _nom):
        return _Collection(self.magasin)


def test_sans_sorabel_depot_firestore_choisit_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("SORABEL_DEPOT", raising=False)
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)

    depot = choisir_depot(chemin, profils_valides=frozenset({"support"}))

    assert isinstance(depot, DepotIdentitesSqlite)


def test_avec_sorabel_depot_firestore_choisit_firestore(monkeypatch, tmp_path):
    monkeypatch.setenv("SORABEL_DEPOT", "firestore")
    client = _ClientFactice()
    monkeypatch.setattr("google.cloud.firestore.Client", lambda: client)
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)

    depot = choisir_depot(chemin, profils_valides=frozenset({"support"}))

    assert isinstance(depot, DepotIdentitesFirestore)
    # Preuve que c'est bien le client injecté qui est consulté, pas un vrai firestore.Client().
    depot.attribuer("sub-123", "support", source="demo")
    assert client.magasin["sub-123"]["profil"] == "support"


def test_profils_valides_vide_reste_fail_closed_via_choisir_depot(monkeypatch, tmp_path):
    """profils_valides est reçu tel quel, pas recalculé : un ensemble vide passé par
    l'appelant continue de fermer le dépôt Firestore à tout profil (délégué à
    DepotIdentitesFirestore, pas réimplémenté ici)."""
    monkeypatch.setenv("SORABEL_DEPOT", "firestore")
    monkeypatch.setattr("google.cloud.firestore.Client", lambda: _ClientFactice())
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)

    depot = choisir_depot(chemin, profils_valides=frozenset())

    with pytest.raises(ValueError, match="profil inconnu"):
        depot.attribuer("sub-123", "support", source="demo")
