"""Firestore avec un client factice : le contrat est testé, pas le SDK de Google.

Aucun appel réseau ni émulateur — la suite doit rester exécutable dans Cloud Build sans
aucun secret.
"""

import pytest

from gouvernance.identites_firestore import DepotIdentitesFirestore


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


@pytest.fixture
def depot():
    return DepotIdentitesFirestore(
        _ClientFactice(), profils_valides=frozenset({"support", "commercial", "dev", "admin"})
    )


def test_sujet_inconnu_ne_donne_aucun_profil(depot):
    assert depot.profil_de("sub-jamais-vu") is None


def test_attribuer_puis_relire(depot):
    depot.attribuer("sub-123", "commercial", source="demo")
    assert depot.profil_de("sub-123") == "commercial"


def test_attribuer_deux_fois_remplace_le_profil(depot):
    depot.attribuer("sub-123", "commercial", source="demo")
    depot.attribuer("sub-123", "support", source="demo")
    assert depot.profil_de("sub-123") == "support"


def test_profil_inexistant_est_refuse(depot):
    with pytest.raises(ValueError, match="profil inconnu"):
        depot.attribuer("sub-123", "directeur", source="demo")


def test_profils_valides_vide_refuse_tout_profil_fail_closed():
    """profils_valides est obligatoire : un ensemble vide ne désactive pas la validation,
    elle doit au contraire refuser tous les profils — y compris ceux qui seraient valides
    ailleurs — plutôt que de tous les accepter (l'ancien défaut fail-open)."""
    depot_ferme = DepotIdentitesFirestore(_ClientFactice(), profils_valides=frozenset())
    with pytest.raises(ValueError, match="profil inconnu"):
        depot_ferme.attribuer("sub-123", "support", source="demo")
    with pytest.raises(ValueError, match="profil inconnu"):
        depot_ferme.attribuer("sub-123", "commercial", source="demo")
