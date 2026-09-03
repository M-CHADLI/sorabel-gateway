"""Détection d'intention sensible AVANT génération (E5) — pas de barrière post-génération.

Volontairement large : un faux positif produit un refus clair et récupérable, un faux négatif
laisse fuiter une donnée sensible. L'asymétrie des conséquences dicte le réglage.
"""

LEXIQUE_SENSIBLE = [
    "marge", "marges",
    "prix d'achat", "prix achat", "coût d'achat", "cout d'achat",
    "rentabilité", "rentabilite",
]


def question_sensible(question: str) -> bool:
    q = question.lower()
    return any(mot in q for mot in LEXIQUE_SENSIBLE)
