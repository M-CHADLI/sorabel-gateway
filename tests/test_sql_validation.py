"""Barrières 2 et 3 (sur 4, E3) : une instruction, SELECT/WITH, mots-clés interdits,
tables et colonnes dans le périmètre du profil."""

import pytest

from sorabel_sql.validation import ValidationEchouee, valider


class _PerimetreFactice:
    def __init__(self, tables, colonnes_interdites=None):
        self._tables = frozenset(tables)
        self._colonnes_interdites = colonnes_interdites or {}

    def tables_autorisees(self):
        return self._tables

    def colonnes_interdites(self, table):
        return frozenset(self._colonnes_interdites.get(table, ()))


PERIMETRE_COMPLET = _PerimetreFactice(["produits", "stocks", "clients", "commandes", "ventes"])
PERIMETRE_SUPPORT = _PerimetreFactice(
    ["produits", "stocks", "clients", "commandes", "ventes"],
    colonnes_interdites={"produits": {"prix_achat_ht", "marge_pct"}, "ventes": {"marge_ht"}},
)


def test_requete_select_simple_passe():
    resultat = valider("SELECT COUNT(*) FROM commandes", PERIMETRE_COMPLET)
    assert resultat == "SELECT COUNT(*) FROM commandes"


def test_requete_with_passe():
    sql = "WITH t AS (SELECT * FROM produits) SELECT * FROM t"
    assert valider(sql, PERIMETRE_COMPLET) == sql


def test_refuse_plusieurs_instructions():
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT * FROM produits; DROP TABLE produits;", PERIMETRE_COMPLET)
    assert exc.value.statut == "refuse_ecriture"


def test_refuse_une_ecriture():
    with pytest.raises(ValidationEchouee) as exc:
        valider("DELETE FROM produits WHERE ref = 'REF-1024'", PERIMETRE_COMPLET)
    assert exc.value.statut == "refuse_ecriture"


def test_refuse_pragma_deguise_en_select():
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT * FROM pragma_table_info('produits')", PERIMETRE_COMPLET)
    # pragma_table_info n'est pas une table connue du schéma Sorabel : hors_schema.
    assert exc.value.statut == "hors_schema"

    with pytest.raises(ValidationEchouee) as exc:
        valider("PRAGMA table_info(produits)", PERIMETRE_COMPLET)
    assert exc.value.statut == "refuse_ecriture"


def test_refuse_une_table_inconnue():
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT * FROM avis", PERIMETRE_COMPLET)
    assert exc.value.statut == "hors_schema"


def test_refuse_une_table_hors_perimetre_du_profil():
    perimetre = _PerimetreFactice(["produits"])  # pas "ventes"
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT * FROM ventes", perimetre)
    assert exc.value.statut == "non_autorise"


def test_refuse_une_colonne_interdite_au_profil_support():
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT marge_pct FROM produits", PERIMETRE_SUPPORT)
    assert exc.value.statut == "non_autorise"
    assert "marge_pct" in exc.value.message


def test_autorise_prix_vente_ht_pour_le_profil_support():
    # Non sensible : ne doit jamais être bloqué.
    resultat = valider("SELECT prix_vente_ht FROM produits", PERIMETRE_SUPPORT)
    assert resultat == "SELECT prix_vente_ht FROM produits"


def test_supprime_les_commentaires_avant_validation():
    sql = "SELECT * FROM produits -- commentaire piégeux ; DROP TABLE produits\n"
    resultat = valider(sql, PERIMETRE_COMPLET)
    assert "DROP" not in resultat
    assert "--" not in resultat


def test_refuse_selection_generique_sur_table_avec_colonnes_sensibles():
    # SELECT * ne mentionne littéralement aucune colonne interdite, mais SQLite les
    # renverrait quand même : c'est le contournement E5 à bloquer.
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT * FROM produits", PERIMETRE_SUPPORT)
    assert exc.value.statut == "non_autorise"


def test_autorise_selection_generique_sur_table_sans_colonnes_sensibles():
    # "stocks" n'a aucune colonne interdite pour le profil support : SELECT * reste permis.
    resultat = valider("SELECT * FROM stocks", PERIMETRE_SUPPORT)
    assert resultat == "SELECT * FROM stocks"


def test_autorise_count_etoile_reste_permis():
    # COUNT(*) est un agrégat légitime, pas une sélection générique de colonnes : non-régression.
    resultat = valider("SELECT COUNT(*) FROM commandes", PERIMETRE_COMPLET)
    assert resultat == "SELECT COUNT(*) FROM commandes"


def test_refuse_selection_generique_avec_alias_sur_table_sensible():
    # Cas limite : "t.*" est aussi une sélection générique de colonnes (via un alias),
    # pas un argument de fonction d'agrégat — doit être refusé au même titre que "SELECT *".
    with pytest.raises(ValidationEchouee) as exc:
        valider("SELECT t.* FROM produits t", PERIMETRE_SUPPORT)
    assert exc.value.statut == "non_autorise"


def test_autorise_multiplication_sur_table_avec_colonnes_sensibles():
    # Non-régression : une multiplication arithmétique (quantite * prix_unitaire_ht)
    # ne doit pas être confondue avec un wildcard générique (SELECT *).
    # La requête est valide : ni quantite ni prix_unitaire_ht ne sont dans les colonnes
    # interdites (seule marge_ht l'est pour ventes).
    resultat = valider(
        "SELECT quantite * prix_unitaire_ht AS total FROM ventes", PERIMETRE_SUPPORT
    )
    assert resultat == "SELECT quantite * prix_unitaire_ht AS total FROM ventes"
