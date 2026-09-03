"""Barrières 2 et 3 (sur 4, E3) : une instruction, SELECT/WITH, mots-clés interdits, tables
et colonnes dans le périmètre du profil. Les barrières 1 (connexion lecture seule) et 4
(LIMIT, timeout) sont dans execution.py — une seule barrière ne suffit pas.

Liste blanche (SELECT/WITH) plutôt que liste noire seule : plus sûre, une liste noire ne
couvre que les formes d'écriture déjà prévues.
"""

from __future__ import annotations

import re

MOTS_CLES_INTERDITS = {
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "attach", "detach", "pragma", "vacuum", "reindex", "truncate",
}

TABLES_CONNUES = {"produits", "stocks", "clients", "commandes", "ventes"}

MOTIF_TABLE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
MOTIF_COMMENTAIRE_LIGNE = re.compile(r"--.*")
MOTIF_COMMENTAIRE_BLOC = re.compile(r"/\*.*?\*/", re.DOTALL)
MOTIF_MOT = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
MOTIF_CTE = re.compile(r"\bwith\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+as", re.IGNORECASE)


class ValidationEchouee(Exception):
    def __init__(self, statut: str, message: str):
        self.statut = statut
        self.message = message
        super().__init__(message)


def _normaliser(sql: str) -> str:
    sans_commentaires = MOTIF_COMMENTAIRE_BLOC.sub(" ", sql)
    sans_commentaires = MOTIF_COMMENTAIRE_LIGNE.sub(" ", sans_commentaires)
    return re.sub(r"\s+", " ", sans_commentaires).strip()


def _contient_selection_generique(instruction: str) -> bool:
    """Un "*" est une sélection générique de colonnes (SELECT *, SELECT t.*) sauf s'il est
    un argument de fonction d'agrégat (COUNT(*)) ou une opération arithmétique (a * b).

    COUNT(*) : le * est précédé d'une parenthèse ouvrante.
    Multiplication (a * b) : le * est suivi d'un identifiant/nombre.
    Wildcard générique : le * n'est pas précédé d'un ( et est suivi de virgule, FROM ou fin.
    """
    for position, caractere in enumerate(instruction):
        if caractere != "*":
            continue

        # Vérifier le caractère précédent (ignorer les espaces)
        curseur = position - 1
        while curseur >= 0 and instruction[curseur].isspace():
            curseur -= 1
        precedent = instruction[curseur] if curseur >= 0 else ""

        # Si précédé d'une parenthèse, c'est COUNT(*) → pas générique
        if precedent == "(":
            continue

        # Vérifier ce qui suit le * (ignorer les espaces)
        curseur = position + 1
        while curseur < len(instruction) and instruction[curseur].isspace():
            curseur += 1
        suite = instruction[curseur:] if curseur < len(instruction) else ""

        # Un vrai wildcard est suivi de virgule, FROM, ou fin de chaîne
        # Si c'est suivi d'un identifiant ou nombre, c'est une multiplication
        est_fin_de_selection = (
            suite == "" or
            suite.startswith(",") or
            re.match(r"(?i:from)\b", suite)
        )

        if est_fin_de_selection:
            # C'est un wildcard générique
            return True

    return False


def valider(sql: str, perimetre) -> str:
    """Retourne le SQL normalisé s'il passe les quatre contrôles ; lève ValidationEchouee sinon."""
    normalisee = _normaliser(sql)

    instructions = [i.strip() for i in normalisee.rstrip(";").split(";") if i.strip()]
    if len(instructions) != 1:
        raise ValidationEchouee("refuse_ecriture", "une seule instruction SQL est autorisée")
    instruction = instructions[0]

    premier_mot = instruction.split(" ", 1)[0].lower()
    if premier_mot not in ("select", "with"):
        raise ValidationEchouee(
            "refuse_ecriture", "seules les requêtes SELECT ou WITH sont autorisées"
        )

    mots = {m.lower() for m in MOTIF_MOT.findall(instruction)}
    interdits_presents = mots & MOTS_CLES_INTERDITS
    if interdits_presents:
        raise ValidationEchouee(
            "refuse_ecriture", f"mot-clé interdit détecté : {', '.join(sorted(interdits_presents))}"
        )

    # Extraire les CTEs (Common Table Expressions) pour les exclure de la vérification
    ctes = {c.lower() for c in MOTIF_CTE.findall(instruction)}

    tables_citees = {t.lower() for t in MOTIF_TABLE.findall(instruction)}
    # Exclure les CTEs de la vérification des tables inconnues
    tables_citees_reelles = tables_citees - ctes

    inconnues = tables_citees_reelles - TABLES_CONNUES
    if inconnues:
        raise ValidationEchouee(
            "hors_schema",
            f"table(s) inexistante(s) : {', '.join(sorted(inconnues))}. "
            f"Tables disponibles : {', '.join(sorted(TABLES_CONNUES))}.",
        )

    tables_autorisees = perimetre.tables_autorisees()
    hors_perimetre = tables_citees_reelles - tables_autorisees
    if hors_perimetre:
        raise ValidationEchouee(
            "non_autorise", f"table(s) hors périmètre du profil : {', '.join(sorted(hors_perimetre))}"
        )

    if _contient_selection_generique(instruction):
        tables_avec_colonnes_sensibles = {
            table for table in tables_citees_reelles if perimetre.colonnes_interdites(table)
        }
        if tables_avec_colonnes_sensibles:
            raise ValidationEchouee(
                "non_autorise",
                "sélection générique (SELECT * ou alias.*) refusée : la ou les table(s) "
                f"{', '.join(sorted(tables_avec_colonnes_sensibles))} ont des colonnes hors "
                "périmètre du profil ; nommez explicitement les colonnes autorisées.",
            )

    for table in tables_citees_reelles:
        colonnes_interdites = perimetre.colonnes_interdites(table)
        presentes = {
            colonne for colonne in colonnes_interdites
            if re.search(rf"\b{re.escape(colonne)}\b", instruction, re.IGNORECASE)
        }
        if presentes:
            raise ValidationEchouee(
                "non_autorise",
                f"colonne(s) hors périmètre du profil : {', '.join(sorted(presentes))}",
            )

    return instruction
