"""Les quatre tools SQL du chantier 2. Compose schema/generation/validation/execution sans
dupliquer leur logique — chaque tool ne fait que router vers le bon statut."""

from __future__ import annotations

import re

from .execution import executer
from .generation import QuestionSensible, generer
from .schema import schema_commente
from .validation import ValidationEchouee, valider

MOTIF_REF = re.compile(r"^REF-\d{4}$")
MOTIF_COMMANDE = re.compile(r"^CMD-\d{4}-\d{4}$")


def get_schema(perimetre) -> dict:
    return {"statut": "ok", "schema": schema_commente(perimetre)}


def ask_database(question: str, perimetre) -> dict:
    try:
        sql_candidat = generer(question, perimetre)
    except QuestionSensible:
        return {
            "statut": "non_autorise",
            "message": "Ce profil n'a pas accès aux marges ni aux prix d'achat.",
            "sql": None,
        }

    if sql_candidat is None:
        return {
            "statut": "hors_schema",
            "message": "Cette question ne correspond à aucune table de la base Sorabel.",
            "sql": None,
        }

    try:
        sql_valide = valider(sql_candidat, perimetre)
    except ValidationEchouee as erreur:
        return {"statut": erreur.statut, "message": erreur.message, "sql": sql_candidat}

    resultat = executer(sql_valide)
    return {"statut": "ok", **resultat}


def check_stock(ref: str) -> dict:
    if not MOTIF_REF.match(ref):
        return {"statut": "hors_schema", "message": f"référence invalide : {ref!r} (attendu REF-XXXX)"}

    resultat = executer(
        "SELECT entrepot, quantite, seuil_reappro FROM stocks WHERE ref = ?", (ref,)
    )
    index_quantite = resultat["colonnes"].index("quantite")
    index_seuil = resultat["colonnes"].index("seuil_reappro")
    sous_seuil = any(ligne[index_quantite] < ligne[index_seuil] for ligne in resultat["lignes"])
    return {"statut": "ok", **resultat, "sous_seuil_reappro": sous_seuil}


def order_status(order_id: str) -> dict:
    if not MOTIF_COMMANDE.match(order_id):
        return {
            "statut": "hors_schema",
            "message": f"identifiant de commande invalide : {order_id!r} (attendu CMD-AAAA-NNNN)",
        }

    resultat = executer(
        "SELECT statut, date_commande, montant_ht FROM commandes WHERE id = ?", (order_id,)
    )
    return {"statut": "ok", **resultat}
