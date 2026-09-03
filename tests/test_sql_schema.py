"""Schéma SQL commenté, filtré par le périmètre du profil (E5)."""

from sorabel_sql.schema import schema_commente


class _PerimetreFactice:
    def __init__(self, tables, colonnes_interdites=None):
        self._tables = frozenset(tables)
        self._colonnes_interdites = colonnes_interdites or {}

    def tables_autorisees(self):
        return self._tables

    def colonnes_interdites(self, table):
        return frozenset(self._colonnes_interdites.get(table, ()))


def test_schema_ne_contient_que_les_tables_autorisees():
    perimetre = _PerimetreFactice(["produits", "stocks"])
    schema = schema_commente(perimetre)
    assert "CREATE TABLE produits" in schema
    assert "CREATE TABLE stocks" in schema
    assert "CREATE TABLE clients" not in schema
    assert "CREATE TABLE commandes" not in schema
    assert "CREATE TABLE ventes" not in schema


def test_schema_exclut_les_colonnes_interdites_du_profil_support():
    perimetre = _PerimetreFactice(
        ["produits", "ventes"],
        colonnes_interdites={
            "produits": {"prix_achat_ht", "marge_pct"},
            "ventes": {"marge_ht"},
        },
    )
    schema = schema_commente(perimetre)
    assert "prix_achat_ht" not in schema
    assert "marge_pct" not in schema
    assert "marge_ht" not in schema
    # Le prix public reste visible : il n'est pas sensible.
    assert "prix_vente_ht" in schema


def test_schema_profil_commercial_contient_les_colonnes_sensibles():
    perimetre = _PerimetreFactice(["produits", "ventes"])
    schema = schema_commente(perimetre)
    assert "prix_achat_ht" in schema
    assert "marge_pct" in schema
    assert "marge_ht" in schema


def test_schema_contient_les_valeurs_types_des_enumerations():
    perimetre = _PerimetreFactice(["commandes", "clients", "stocks", "produits"])
    schema = schema_commente(perimetre)
    for valeur in ("annulee", "en_attente", "expediee", "livree", "preparee"):
        assert valeur in schema
    for valeur in ("PME", "artisan", "collectivité", "grand compte"):
        assert valeur in schema
    for valeur in ("LILLE", "LYON", "NANTES"):
        assert valeur in schema
