"""Le Perimetre : les droits d'un profil, sous la forme que les tools consomment.

Les tools ne lisent ni gouvernance.db ni le modèle Pydantic : ils reçoivent un Perimetre
construit une fois par appel et lui posent des questions. Duck-typé pour satisfaire le
contrat déjà attendu par sorabel_sql (Phase 3) sans qu'aucune ligne de ce package ne
dépende de `gouvernance`.
"""

from __future__ import annotations

from .modeles import MatriceAcces


class ProfilInconnu(Exception):
    pass


class Perimetre:
    def __init__(self, profil: str, matrice: MatriceAcces):
        if profil not in matrice.profils:
            raise ProfilInconnu(f"profil inconnu : {profil!r}")
        self.profil = profil
        self._droits = matrice.profils[profil]

    def peut_appeler(self, tool: str) -> bool:
        return tool in self._droits.tools

    def collections_autorisees(self) -> frozenset[str]:
        return self._droits.collections

    def tables_autorisees(self) -> frozenset[str]:
        return self._droits.tables

    def colonnes_interdites(self, table: str) -> frozenset[str]:
        return self._droits.colonnes_interdites.get(table, frozenset())
