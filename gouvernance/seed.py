"""Peuple gouvernance.db avec la matrice d'accès exacte de docs/conception_mcp.md §2.

Script d'administration : c'est le SEUL endroit du dépôt qui écrit la matrice (profils,
tools, collections, tables, colonnes interdites) dans gouvernance.db — elle se modifie hors
ligne, la Gateway l'ouvre toujours en lecture seule à l'exécution. Les identités (quel
profil pour quel sujet) s'écrivent à part, via `gouvernance.identites.DepotIdentitesSqlite`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = Path(__file__).resolve().parent / "schema.sql"

PROFILS = [
    ("support", "technicien du support client"),
    ("commercial", "commercial en clientèle"),
    ("dev", "développeur intégrant la Gateway"),
    ("admin", "exploitation"),
]

TOOLS = [
    ("answer_question", "Réponse rédigée avec sources, refuse hors corpus sans appel LLM."),
    ("search_docs", "Recherche hybride, extraits bruts et scores, aucune génération."),
    ("get_document", "Document complet, version courante par défaut."),
    ("list_sources", "Inventaire des documents et de leurs versions."),
    ("ask_database", "Requête SQL en langage naturel, lecture seule (E3)."),
    ("get_schema", "Schéma commenté tel que le profil le voit."),
    ("check_stock", "Stock par entrepôt pour une référence précise, zéro LLM."),
    ("order_status", "Statut, date et montant d'une commande, zéro LLM."),
]

COLLECTIONS = [
    ("fiches", "Fiches techniques"),
    ("notices", "Notices d'installation"),
    ("sav", "Procédures SAV"),
    ("notes_operationnelles", "Alerte qualité, logistique, retour terrain"),
    ("notes_confidentielles", "Politique tarifaire, réunion achats"),
]

PROFIL_TOOL: dict[str, set[str]] = {
    "answer_question": {"support", "commercial", "admin"},
    "search_docs": {"support", "commercial", "dev", "admin"},
    "get_document": {"support", "commercial", "dev", "admin"},
    "list_sources": {"support", "commercial", "dev", "admin"},
    "ask_database": {"support", "commercial", "admin"},
    "get_schema": {"support", "commercial", "dev", "admin"},
    "check_stock": {"support", "commercial", "admin"},
    "order_status": {"support", "commercial", "admin"},
}

PROFIL_COLLECTION: dict[str, set[str]] = {
    "fiches": {"support", "commercial", "dev", "admin"},
    "notices": {"support", "commercial", "dev", "admin"},
    "sav": {"support", "commercial", "dev", "admin"},
    "notes_operationnelles": {"support", "commercial", "admin"},
    "notes_confidentielles": {"commercial", "admin"},
}

TABLES_SQL = ["produits", "stocks", "clients", "commandes", "ventes"]

# Les 4 profils voient les 5 tables — `dev` en lecture de schéma seule (drapeau
# documentaire ; la barrière réelle est `peut_appeler("ask_database")`, cf. Global Constraints).
LECTURE_SEULE_SCHEMA = {("dev", table) for table in TABLES_SQL}

# Exigé par le validateur E5 (Task 2) pour tout profil hors commercial/admin ayant accès à
# la table concernée — dev y est soumis même s'il n'appelle jamais ask_database en pratique.
COLONNES_INTERDITES = [
    ("support", "produits", "prix_achat_ht", "colonne sensible E5"),
    ("support", "produits", "marge_pct", "colonne sensible E5"),
    ("support", "ventes", "marge_ht", "colonne sensible E5"),
    ("dev", "produits", "prix_achat_ht", "colonne sensible E5"),
    ("dev", "produits", "marge_pct", "colonne sensible E5"),
    ("dev", "ventes", "marge_ht", "colonne sensible E5"),
]


def peupler(chemin_db: Path) -> None:
    chemin_db = Path(chemin_db)
    chemin_db.parent.mkdir(parents=True, exist_ok=True)
    if chemin_db.exists():
        chemin_db.unlink()

    connexion = sqlite3.connect(chemin_db)
    try:
        connexion.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        connexion.executemany("INSERT INTO profils (code, libelle) VALUES (?, ?)", PROFILS)
        connexion.executemany("INSERT INTO tools (code, description) VALUES (?, ?)", TOOLS)
        connexion.executemany("INSERT INTO collections (code, libelle) VALUES (?, ?)", COLLECTIONS)

        for tool, profils in PROFIL_TOOL.items():
            connexion.executemany(
                "INSERT INTO profil_tool (profil, tool) VALUES (?, ?)",
                [(profil, tool) for profil in profils],
            )
        for collection, profils in PROFIL_COLLECTION.items():
            connexion.executemany(
                "INSERT INTO profil_collection (profil, collection) VALUES (?, ?)",
                [(profil, collection) for profil in profils],
            )
        for profil, _ in PROFILS:
            connexion.executemany(
                "INSERT INTO profil_table (profil, table_sql, lecture_seule_schema) VALUES (?, ?, ?)",
                [
                    (profil, table, int((profil, table) in LECTURE_SEULE_SCHEMA))
                    for table in TABLES_SQL
                ],
            )
        connexion.executemany(
            "INSERT INTO colonne_interdite (profil, table_sql, colonne, motif) VALUES (?, ?, ?, ?)",
            COLONNES_INTERDITES,
        )
        connexion.commit()
    finally:
        connexion.close()
