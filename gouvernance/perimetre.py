"""Matrice d'accès : profil × tools × tables × colonnes."""

import sqlite3
from pathlib import Path


class Perimetre:
    """Encapsule la matrice d'accès pour un profil donné."""

    def __init__(self, profil: str, chemin_db: str | Path):
        """Initialise le périmètre pour un profil.

        Args:
            profil: "support", "commercial", "dev", ou "admin"
            chemin_db: chemin de la base gouvernance/gouvernance.db
        """
        self.profil = profil
        self.chemin_db = Path(chemin_db)
        self._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        """Retourne une connexion à la base (lazy initialization)."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.chemin_db))
        return self._conn

    def tools_autorises(self) -> list[str]:
        """Retourne la liste des tools autorisés pour ce profil."""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT tool FROM profil_tool WHERE profil = ? ORDER BY tool",
            (self.profil,)
        )
        return [row[0] for row in c.fetchall()]

    def colonnes_interdites(self, table: str) -> set[str]:
        """Retourne l'ensemble des colonnes interdites pour une table.

        Args:
            table: nom de la table (ex. "produits", "ventes")

        Returns:
            Ensemble des colonnes interdites (ex. {"marge_pct", "prix_achat_ht"})
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT colonne FROM colonne_interdite WHERE profil = ? AND table_sql = ?",
            (self.profil, table)
        )
        return {row[0] for row in c.fetchall()}

    def tables_autorisees(self) -> set[str]:
        """Retourne l'ensemble des tables autorisées pour ce profil."""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT table_sql FROM profil_table WHERE profil = ? ORDER BY table_sql",
            (self.profil,)
        )
        return {row[0] for row in c.fetchall()}

    def fermer(self):
        """Ferme la connexion à la base."""
        if self._conn:
            self._conn.close()
            self._conn = None
