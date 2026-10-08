"""Schéma SQL commenté envoyé au LLM, filtré par le périmètre du profil (E5).

Pas un CREATE TABLE brut : chaque colonne porte un commentaire qui dit ce qu'elle signifie,
pas seulement son type. Le schéma est construit à partir du périmètre, pas tronqué après
coup — on ne peut pas générer du SQL sur une colonne qu'on ignore.

Tables, colonnes et types sont communs à toutes les enseignes ; le vocabulaire métier
(catégories, entrepôts, segments…) vient de `[sql.commentaires]` dans enseigne.toml.
"""

from __future__ import annotations

from collections.abc import Mapping

from sorabel_enseigne import enseigne_active

# (nom, type SQLite, commentaire — vide si le nom de colonne se suffit à lui-même, ou si le
# commentaire est propre à l'enseigne)
COLONNES: dict[str, list[tuple[str, str, str]]] = {
    "produits": [
        ("ref", "TEXT PRIMARY KEY", "référence commerciale REF-XXXX, clé vers le corpus documentaire"),
        ("nom", "TEXT", "libellé commercial"),
        ("categorie", "TEXT", ""),
        ("fabricant", "TEXT", ""),
        ("unite", "TEXT", ""),
        ("prix_vente_ht", "REAL", "prix public HT"),
        ("prix_achat_ht", "REAL", "prix d'achat fournisseur"),
        ("marge_pct", "REAL", "taux de marge"),
        ("actif", "INTEGER", "1 = au catalogue"),
    ],
    "stocks": [
        ("id", "INTEGER PRIMARY KEY", ""),
        ("ref", "TEXT", "clé vers produits.ref"),
        ("entrepot", "TEXT", ""),
        ("quantite", "INTEGER", ""),
        ("seuil_reappro", "INTEGER", "en dessous, réapprovisionnement nécessaire"),
    ],
    "clients": [
        ("id", "TEXT PRIMARY KEY", ""),
        ("raison_sociale", "TEXT", ""),
        ("segment", "TEXT", ""),
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


def valider_commentaires(commentaires: Mapping[str, str]) -> None:
    """Une clé mal orthographiée dans enseigne.toml (`produit.categorie`) serait sinon
    ignorée en silence : le LLM perdrait la liste des valeurs sans que rien ne casse."""
    connues = {f"{table}.{nom}" for table, colonnes in COLONNES.items() for nom, _, _ in colonnes}
    inconnues = sorted(set(commentaires) - connues)
    if inconnues:
        raise ValueError(f"commentaires SQL sur des colonnes inconnues : {', '.join(inconnues)}")


COMMENTAIRES_ENSEIGNE = enseigne_active().commentaires_sql
valider_commentaires(COMMENTAIRES_ENSEIGNE)


def _table_commentee(
    table: str,
    colonnes_interdites: frozenset[str],
    commentaires: Mapping[str, str] | None = None,
) -> str:
    commentaires = COMMENTAIRES_ENSEIGNE if commentaires is None else commentaires
    lignes = [f"CREATE TABLE {table} ("]
    colonnes_visibles = [c for c in COLONNES[table] if c[0] not in colonnes_interdites]
    for index, (nom, type_sql, commentaire_moteur) in enumerate(colonnes_visibles):
        commentaire = commentaires.get(f"{table}.{nom}", commentaire_moteur)
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
