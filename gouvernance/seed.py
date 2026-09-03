"""Peuplement de la matrice de gouvernance pour les 4 profils."""

import sqlite3
from pathlib import Path


def peupler(chemin_db: str | Path) -> None:
    """Crée et peuple une base de gouvernance avec 4 profils et leurs permissions.

    Structure minimale pour Phase 6 Task 1.
    """
    chemin = Path(chemin_db)
    chemin.parent.mkdir(parents=True, exist_ok=True)

    # Supprimer la DB existante pour garantir un état frais
    if chemin.exists():
        chemin.unlink()

    conn = sqlite3.connect(str(chemin))
    c = conn.cursor()

    # Table des profils
    c.execute("""
        CREATE TABLE profils (
            nom TEXT PRIMARY KEY,
            description TEXT
        )
    """)

    # Table des autorisations par profil et tool
    c.execute("""
        CREATE TABLE autorisations_tools (
            profil TEXT,
            tool TEXT,
            PRIMARY KEY (profil, tool)
        )
    """)

    # Table des colonnes interdites par profil et table
    c.execute("""
        CREATE TABLE colonnes_interdites (
            profil TEXT,
            table_name TEXT,
            colonne TEXT,
            PRIMARY KEY (profil, table_name, colonne)
        )
    """)

    # Insérer les 4 profils
    profils = [
        ("support", "Support client - accès public"),
        ("commercial", "Équipe commerciale - accès complet sauf coûts"),
        ("dev", "Développeur - accès en lecture seule, pas de SQL"),
        ("admin", "Admin - accès complet"),
    ]
    c.executemany("INSERT INTO profils VALUES (?, ?)", profils)

    # 8 tools totaux (d'après test_lister_tools_support_a_les_huit_tools):
    # answer_question, search_docs, get_document, list_sources (RAG)
    # ask_database, get_schema, check_stock, order_status (données)

    # Profil support : accès à tous les 8 tools
    tools_support = [
        ("support", "answer_question"),
        ("support", "search_docs"),
        ("support", "get_document"),
        ("support", "list_sources"),
        ("support", "ask_database"),
        ("support", "get_schema"),
        ("support", "check_stock"),
        ("support", "order_status"),
    ]

    # Profil commercial : accès à tous sauf les tools de coûts/marges
    tools_commercial = [
        ("commercial", "answer_question"),
        ("commercial", "search_docs"),
        ("commercial", "get_document"),
        ("commercial", "list_sources"),
        ("commercial", "ask_database"),
        ("commercial", "get_schema"),
        ("commercial", "check_stock"),
        ("commercial", "order_status"),
    ]

    # Profil dev : accès RAG uniquement (pas ask_database, check_stock, order_status)
    tools_dev = [
        ("dev", "search_docs"),
        ("dev", "get_document"),
        ("dev", "list_sources"),
        ("dev", "get_schema"),
    ]

    # Profil admin : accès à tous les 8 tools
    tools_admin = [
        ("admin", "answer_question"),
        ("admin", "search_docs"),
        ("admin", "get_document"),
        ("admin", "list_sources"),
        ("admin", "ask_database"),
        ("admin", "get_schema"),
        ("admin", "check_stock"),
        ("admin", "order_status"),
    ]

    c.executemany(
        "INSERT INTO autorisations_tools VALUES (?, ?)",
        tools_support + tools_commercial + tools_dev + tools_admin
    )

    # Colonnes interdites pour support (E5) : prix d'achat, marge
    colonnes_interdites = [
        ("support", "produits", "prix_achat_ht"),
        ("support", "produits", "marge_pct"),
        ("support", "ventes", "marge_ht"),
    ]
    c.executemany(
        "INSERT INTO colonnes_interdites VALUES (?, ?, ?)",
        colonnes_interdites
    )

    conn.commit()
    conn.close()
