"""Commentaires de schéma par enseigne : la structure SQL est commune, le vocabulaire
métier (catégories, entrepôts, segments) vient de enseigne.toml."""

import pytest

from sorabel_sql.schema import _table_commentee, valider_commentaires


def test_un_commentaire_d_enseigne_remplace_celui_du_moteur():
    table = _table_commentee("stocks", frozenset(), {"stocks.entrepot": "LAUWIN | MONTLUEL"})
    assert "  entrepot TEXT,  -- LAUWIN | MONTLUEL" in table


def test_sans_commentaire_d_enseigne_une_colonne_metier_reste_sans_vocabulaire():
    """Une enseigne qui oublie ses entrepôts ne doit pas hériter de ceux de Sorabel."""
    table = _table_commentee("stocks", frozenset(), {})
    assert "  entrepot TEXT," in table
    assert "LILLE" not in table


def test_une_cle_de_commentaire_inconnue_est_refusee():
    with pytest.raises(ValueError, match="produit.categorie"):
        valider_commentaires({"produit.categorie": "Femme | Homme"})
