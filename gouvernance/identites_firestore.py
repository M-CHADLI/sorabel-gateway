"""Dépôt d'identités sur Firestore — la seule donnée en écriture de la production.

Le client est injecté plutôt que construit ici : c'est ce qui permet de tester le contrat
avec une doublure, sans réseau ni émulateur, et de garder la suite exécutable dans Cloud
Build sans le moindre secret.

La liste des profils valides est passée à la construction, extraite de la matrice figée
dans l'image : Firestore ne connaît pas la matrice, et on n'écrit pas une identité qui
pointerait vers un profil inexistant.
"""

from __future__ import annotations


class DepotIdentitesFirestore:
    def __init__(self, client, collection: str = "identites", profils_valides=frozenset()):
        self._collection = client.collection(collection)
        self._profils_valides = frozenset(profils_valides)

    def profil_de(self, sujet: str) -> str | None:
        instantane = self._collection.document(sujet).get()
        if not instantane.exists:
            return None
        return (instantane.to_dict() or {}).get("profil")

    def attribuer(self, sujet: str, profil: str, source: str) -> None:
        if self._profils_valides and profil not in self._profils_valides:
            raise ValueError(f"profil inconnu : {profil!r}")
        # `set` sans merge : changer de profil réécrit le document entier, comme le
        # INSERT OR REPLACE de l'implémentation SQLite.
        self._collection.document(sujet).set({"profil": profil, "source": source})
