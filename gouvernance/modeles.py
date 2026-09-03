"""Validation Pydantic de la matrice d'accès — chargée une fois au démarrage du serveur MCP.

Deux garanties : un code inconnu (faute de frappe dans gouvernance.db) fait échouer le
chargement, pas silencieusement à l'appel ; E5 est vérifiée par un validateur, pas seulement
espérée dans les données — si l'exclusion d'une colonne sensible manque, le chargement lève.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationInfo, field_validator

CodeTool = Literal[
    "answer_question", "search_docs", "get_document", "list_sources",
    "ask_database", "get_schema", "check_stock", "order_status",
]
CodeCollection = Literal[
    "fiches", "notices", "sav", "notes_operationnelles", "notes_confidentielles",
]
TableSql = Literal["produits", "stocks", "clients", "commandes", "ventes"]

COLONNES_SENSIBLES_OBLIGATOIRES: dict[str, frozenset[str]] = {
    "produits": frozenset({"prix_achat_ht", "marge_pct"}),
    "ventes": frozenset({"marge_ht"}),
}


class DroitsProfil(BaseModel):
    code: str
    tools: frozenset[CodeTool]
    collections: frozenset[CodeCollection]
    tables: frozenset[TableSql]
    colonnes_interdites: dict[TableSql, frozenset[str]]

    @field_validator("colonnes_interdites")
    @classmethod
    def colonnes_sensibles_couvertes(cls, valeur, info: ValidationInfo):
        if info.data.get("code") in ("commercial", "admin"):
            return valeur
        for table, colonnes_obligatoires in COLONNES_SENSIBLES_OBLIGATOIRES.items():
            if table in info.data.get("tables", frozenset()):
                manquantes = colonnes_obligatoires - valeur.get(table, frozenset())
                if manquantes:
                    raise ValueError(
                        f"E5 violée pour le profil {info.data.get('code')!r} : "
                        f"{table}.{sorted(manquantes)} non exclue(s)"
                    )
        return valeur


class MatriceAcces(BaseModel):
    profils: dict[str, DroitsProfil]


def charger_matrice(chemin_db: Path) -> MatriceAcces:
    """Lecture seule de gouvernance.db. Un code inconnu en base fait échouer Pydantic ici,
    au démarrage — jamais à l'appel d'un tool."""
    connexion = sqlite3.connect(f"file:{Path(chemin_db).as_posix()}?mode=ro", uri=True)
    try:
        codes_profils = [
            row[0] for row in connexion.execute("SELECT code FROM profils WHERE actif = 1")
        ]
        profils: dict[str, DroitsProfil] = {}
        for code in codes_profils:
            tools = {
                r[0] for r in connexion.execute(
                    "SELECT tool FROM profil_tool WHERE profil = ?", (code,)
                )
            }
            collections = {
                r[0] for r in connexion.execute(
                    "SELECT collection FROM profil_collection WHERE profil = ?", (code,)
                )
            }
            tables = {
                r[0] for r in connexion.execute(
                    "SELECT table_sql FROM profil_table WHERE profil = ?", (code,)
                )
            }
            colonnes_interdites: dict[str, set[str]] = {}
            for table, colonne in connexion.execute(
                "SELECT table_sql, colonne FROM colonne_interdite WHERE profil = ?", (code,)
            ):
                colonnes_interdites.setdefault(table, set()).add(colonne)

            profils[code] = DroitsProfil(
                code=code,
                tools=tools,
                collections=collections,
                tables=tables,
                colonnes_interdites={t: frozenset(c) for t, c in colonnes_interdites.items()},
            )
        return MatriceAcces(profils=profils)
    finally:
        connexion.close()
