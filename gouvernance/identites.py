"""Le dépôt d'identités : quel profil est attribué à quel sujet authentifié.

C'est la seule donnée qui s'écrit en production — la matrice, elle, est figée dans l'image.
Le contrat est duck-typé comme `Perimetre` : les appelants ne connaissent que deux méthodes,
ce qui permet de servir SQLite en développement et Firestore en production sans qu'aucun
d'eux n'importe l'autre.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class DepotIdentitesSqlite:
    """Implémentation locale, utilisée en développement et par les tests."""

    def __init__(self, chemin_db: Path | str):
        self._chemin = Path(chemin_db)

    def _connexion(self, lecture_seule: bool = True) -> sqlite3.Connection:
        if lecture_seule:
            return sqlite3.connect(f"file:{self._chemin.as_posix()}?mode=ro", uri=True)
        return sqlite3.connect(self._chemin)

    def profil_de(self, sujet: str) -> str | None:
        connexion = self._connexion()
        try:
            ligne = connexion.execute(
                "SELECT profil FROM identites WHERE sujet = ?", (sujet,)
            ).fetchone()
        finally:
            connexion.close()
        return ligne[0] if ligne else None

    def attribuer(self, sujet: str, profil: str, source: str) -> None:
        connexion = self._connexion(lecture_seule=False)
        try:
            connu = connexion.execute(
                "SELECT 1 FROM profils WHERE code = ? AND actif = 1", (profil,)
            ).fetchone()
            if not connu:
                raise ValueError(f"profil inconnu : {profil!r}")
            # REPLACE plutôt qu'INSERT : changer de profil réécrit la ligne du sujet,
            # sinon `profil_de` deviendrait ambigu.
            connexion.execute(
                "INSERT OR REPLACE INTO identites (sujet, profil, source) VALUES (?, ?, ?)",
                (sujet, profil, source),
            )
            connexion.commit()
        finally:
            connexion.close()
