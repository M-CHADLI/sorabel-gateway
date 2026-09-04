"""Génération de la requête SQL candidate — traduction de la question en langage naturel.

La détection d'intention sensible se fait AVANT tout appel LLM (E5) : aucune raison de payer
un appel et de risquer une fuite pour une question qu'on sait devoir refuser.
"""

from __future__ import annotations

from sorabel_llm.client import completer

from .lexique_sensible import question_sensible
from .schema import schema_commente

PROMPT_SYSTEME = """Tu traduis une question en langage naturel en une requête SQLite en LECTURE \
SEULE sur la base Sorabel. Règles strictes :
- Une seule requête, commençant par SELECT ou WITH.
- Pas de point-virgule multiple, pas de commentaire.
- N'utilise QUE les tables et colonnes du schéma ci-dessous — n'invente jamais de colonne.
- `date_commande` est du texte ISO ('AAAA-MM-JJ') : utilise strftime() pour les agrégations \
temporelles.
- Réponds UNIQUEMENT avec la requête SQL, sans habillage ni explication.
- Si la question ne peut pas être traduite en SQL sur ce schéma, réponds EXACTEMENT : \
AUCUNE_REQUETE"""

EXEMPLES = """Q : combien de commandes en avril ?
S : SELECT COUNT(*) FROM commandes WHERE strftime('%m', date_commande) = '04';

Q : quel est le stock de REF-1024 ?
S : SELECT entrepot, quantite FROM stocks WHERE ref = 'REF-1024';"""


class QuestionSensible(Exception):
    """Levée avant tout appel LLM : la question porte sur une colonne interdite au profil."""


TABLES_A_COLONNES_SENSIBLES = ("produits", "ventes")


def _profil_restreint_sur_le_sensible(perimetre) -> bool:
    """Vrai si le profil se voit interdire au moins une colonne sensible.

    Le lexique (marge, prix d'achat…) ne vaut refus que pour ces profils-là : `commercial`
    et `admin` ont légitimement accès aux marges, leur opposer le garde-fou lexical les
    priverait d'une donnée que la matrice leur accorde.
    """
    return any(perimetre.colonnes_interdites(table) for table in TABLES_A_COLONNES_SENSIBLES)


def generer(question: str, perimetre) -> str | None:
    """`None` si la question ne se traduit pas en SQL sur ce schéma (hors_schema)."""
    if _profil_restreint_sur_le_sensible(perimetre) and question_sensible(question):
        raise QuestionSensible(question)

    schema = schema_commente(perimetre)
    prompt_systeme = f"{PROMPT_SYSTEME}\n\nSchéma disponible :\n{schema}\n\nExemples :\n{EXEMPLES}"
    reponse = completer([
        {"role": "system", "content": prompt_systeme},
        {"role": "user", "content": f"Q : {question}\nS :"},
    ])
    sql = reponse.strip().strip(";").strip()
    return None if sql == "AUCUNE_REQUETE" else sql
