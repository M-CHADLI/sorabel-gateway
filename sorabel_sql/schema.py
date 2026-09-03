"""Schéma SQL commenté envoyé au LLM, filtré par le périmètre du profil (E5).

Pas un CREATE TABLE brut : chaque colonne porte un commentaire qui dit ce qu'elle signifie,
pas seulement son type. Le schéma est construit à partir du périmètre, pas tronqué après
coup — on ne peut pas générer du SQL sur une colonne qu'on ignore.
"""

from __future__ import annotations

# (nom, type SQLite, commentaire — vide si le nom de colonne se suffit à lui-même)
COLONNES: dict[str, list[tuple[str, str, str]]] = {
    "produits": [
        ("ref", "TEXT PRIMARY KEY", "référence commerciale REF-XXXX, clé vers le corpus documentaire"),
        ("nom", "TEXT", "libellé commercial"),
        ("categorie", "TEXT", "Protection électrique | EPI | Câblage | Outillage électroportatif | "
                              "Visserie | Outillage à main | Distribution | Éclairage | Mesure"),
        ("fabricant", "TEXT", ""),
        ("unite", "TEXT", "pièce | conditionnement"),
        ("prix_vente_ht", "REAL", "prix public HT"),
        ("prix_achat_ht", "REAL", "prix d'achat fournisseur"),
        ("marge_pct", "REAL", "taux de marge"),
        ("actif", "INTEGER", "1 = au catalogue"),
    ],
    "stocks": [
        ("id", "INTEGER PRIMARY KEY", ""),
        ("ref", "TEXT", "clé vers produits.ref"),
        ("entrepot", "TEXT", "LILLE | LYON | NANTES"),
        ("quantite", "INTEGER", ""),
        ("seuil_reappro", "INTEGER", "en dessous, réapprovisionnement nécessaire"),
    ],
    "clients": [
        ("id", "TEXT PRIMARY KEY", "ex. 'CLI-1000'"),
        ("raison_sociale", "TEXT", ""),
        ("segment", "TEXT", "PME | artisan | collectivité | grand compte"),
        ("ville", "TEXT", ""),
        ("email", "TEXT", ""),
    ],
    "commandes": [
        ("id", "TEXT PRIMARY KEY", "ex. 'CMD-2025-0004'"),
        ("client_id", "TEXT", "clé vers clients.id"),
        ("date_commande", "TEXT", "ISO 'AAAA-MM-JJ' — utiliser strftime() pour les agrégations temporelles"),
        ("statut", "TEXT", "annulee | en_attente | expediee | livree | preparee"),
        ("montant_ht", "REAL", ""),
    ],
    "ventes": [
        ("id", "INTEGER PRIMARY KEY", ""),
        ("commande_id", "TEXT", "clé vers commandes.id"),
        ("ref", "TEXT", "clé vers produits.ref"),
        ("quantite", "INTEGER", ""),
        ("prix_unitaire_ht", "REAL", ""),
        ("remise_pct", "REAL", ""),
        ("marge_ht", "REAL", "marge en valeur"),
    ],
}

ORDRE_TABLES = ["produits", "stocks", "clients", "commandes", "ventes"]


def _table_commentee(table: str, colonnes_interdites: frozenset[str]) -> str:
    lignes = [f"CREATE TABLE {table} ("]
    colonnes_visibles = [c for c in COLONNES[table] if c[0] not in colonnes_interdites]
    for index, (nom, type_sql, commentaire) in enumerate(colonnes_visibles):
        virgule = "," if index < len(colonnes_visibles) - 1 else ""
        suffixe = f"  -- {commentaire}" if commentaire else ""
        lignes.append(f"  {nom} {type_sql}{virgule}{suffixe}")
    lignes.append(");")
    return "\n".join(lignes)


def schema_commente(perimetre) -> str:
    """Le schéma tel que le profil de `perimetre` le voit — mêmes tables, mêmes colonnes,
    mêmes valeurs types que ce qui est envoyé au modèle de génération SQL."""
    tables_autorisees = perimetre.tables_autorisees()
    morceaux = [
        _table_commentee(table, perimetre.colonnes_interdites(table))
        for table in ORDRE_TABLES
        if table in tables_autorisees
    ]
    return "\n\n".join(morceaux)
