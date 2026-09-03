"""Détection lexicale d'intention sensible (E5) — asymétrie assumée : faux positif
récupérable, faux négatif inacceptable, donc le lexique est volontairement large."""

from sorabel_sql.lexique_sensible import question_sensible


def test_detecte_la_marge():
    assert question_sensible("quelle est la marge sur REF-1024 ?")


def test_detecte_le_prix_dachat():
    assert question_sensible("quel est le prix d'achat du REF-1024 ?")


def test_detecte_independamment_de_la_casse():
    assert question_sensible("Quelle MARGE fait-on sur ce produit ?")


def test_ne_detecte_pas_une_question_neutre():
    assert not question_sensible("combien de commandes en avril ?")


def test_ne_detecte_pas_le_prix_de_vente():
    assert not question_sensible("quel est le prix de vente du REF-1024 ?")
