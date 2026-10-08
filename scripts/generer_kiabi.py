"""Génère les données FICTIVES de l'enseigne de démonstration Kiabi : base SQLite et corpus.

Rien ici ne provient de Kiabi : catalogue, prix, magasins, ateliers et notes sont inventés pour
une démonstration. Mêmes tables, mêmes colonnes et mêmes gabarits de documents que Sorabel —
l'ingestion ne change pas d'une ligne. Les pièges volontaires du corpus Sorabel sont reproduits :
versions multiples d'un même document, guides d'entretien au corps identique par famille de
matière (seule la référence les distingue, d'où l'intérêt de BM25), notes à diffusion restreinte,
colonnes de marge sensibles (E5).

Graine fixe et date de création des PDF figée : relancer le script réécrit des fichiers
identiques à l'octet près, donc un diff git vide.

Usage : python scripts/generer_kiabi.py
"""

from __future__ import annotations

import random
import shutil
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fpdf import FPDF

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "enseignes" / "kiabi" / "data"
CORPUS = SORTIE / "corpus"
BASE = SORTIE / "kiabi.db"

GRAINE = 2026
DATE_PDF = datetime(2026, 1, 1, tzinfo=timezone.utc)
ENTREPOTS = ["LAUWIN", "LYON", "TOULOUSE"]
PIED_DE_PAGE = "Document Kiabi - diffusion interne et magasins du réseau (données fictives)."

# (catégorie, libellé, famille de matière, composition, unité)
CATALOGUE = [
    ("Homme", "Jean slim brut", "denim", "98 % coton, 2 % élasthanne", "pièce"),
    ("Homme", "T-shirt col rond coton bio", "coton", "100 % coton biologique", "pièce"),
    ("Homme", "Polo piqué manches courtes", "coton", "100 % coton", "pièce"),
    ("Homme", "Chemise oxford", "coton", "100 % coton", "pièce"),
    ("Homme", "Sweat à capuche molleton", "coton", "80 % coton, 20 % polyester", "pièce"),
    ("Homme", "Pull col camionneur", "maille", "70 % acrylique, 30 % laine", "pièce"),
    ("Homme", "Pantalon chino", "coton", "97 % coton, 3 % élasthanne", "pièce"),
    ("Homme", "Veste softshell", "synthetique", "94 % polyester, 6 % élasthanne", "pièce"),
    ("Homme", "Bermuda cargo", "coton", "100 % coton", "pièce"),
    ("Homme", "Boxers coton lot de 3", "coton", "95 % coton, 5 % élasthanne", "lot"),
    ("Homme", "Veste en jean", "denim", "100 % coton", "pièce"),
    ("Femme", "Jean mom taille haute", "denim", "99 % coton, 1 % élasthanne", "pièce"),
    ("Femme", "Robe fluide imprimée", "synthetique", "100 % viscose", "pièce"),
    ("Femme", "Pull col roulé maille côtelée", "maille", "60 % acrylique, 40 % coton", "pièce"),
    ("Femme", "T-shirt col V coton bio", "coton", "100 % coton biologique", "pièce"),
    ("Femme", "Chemise en lin manches longues", "coton", "100 % lin", "pièce"),
    ("Femme", "Doudoune légère sans manches", "synthetique", "100 % polyamide", "pièce"),
    ("Femme", "Legging côtelé", "maille", "95 % coton, 5 % élasthanne", "pièce"),
    ("Femme", "Blazer droit", "synthetique", "65 % polyester, 35 % viscose", "pièce"),
    ("Femme", "Jupe plissée mi-longue", "synthetique", "100 % polyester recyclé", "pièce"),
    ("Femme", "Gilet long maille", "maille", "70 % acrylique, 30 % laine", "pièce"),
    ("Femme", "Short en lin", "coton", "55 % lin, 45 % viscose", "pièce"),
    ("Femme", "Top en dentelle", "synthetique", "100 % polyamide", "pièce"),
    ("Fille", "Robe à volants", "coton", "100 % coton", "pièce"),
    ("Fille", "Legging imprimé", "maille", "92 % coton, 8 % élasthanne", "pièce"),
    ("Fille", "Sweat licorne", "coton", "80 % coton, 20 % polyester", "pièce"),
    ("Fille", "Jean flare", "denim", "98 % coton, 2 % élasthanne", "pièce"),
    ("Fille", "Pyjama 2 pièces", "coton", "100 % coton", "lot"),
    ("Fille", "Doudoune à capuche", "synthetique", "100 % polyester", "pièce"),
    ("Fille", "Jupe en tulle", "synthetique", "100 % polyamide", "pièce"),
    ("Garçon", "T-shirt imprimé dinosaure", "coton", "100 % coton", "pièce"),
    ("Garçon", "Jogging molleton", "coton", "80 % coton, 20 % polyester", "pièce"),
    ("Garçon", "Jean regular", "denim", "100 % coton", "pièce"),
    ("Garçon", "Parka doublée", "synthetique", "100 % polyester", "pièce"),
    ("Garçon", "Pyjama court", "coton", "100 % coton", "lot"),
    ("Garçon", "Chemise à carreaux", "coton", "100 % coton", "pièce"),
    ("Garçon", "Bermuda en jean", "denim", "99 % coton, 1 % élasthanne", "pièce"),
    ("Bébé", "Bodies manches courtes lot de 5", "coton", "100 % coton biologique", "lot"),
    ("Bébé", "Pyjama velours", "coton", "80 % coton, 20 % polyester", "pièce"),
    ("Bébé", "Gigoteuse 6-18 mois", "coton", "100 % coton", "pièce"),
    ("Bébé", "Ensemble naissance 3 pièces", "coton", "100 % coton", "lot"),
    ("Bébé", "Bonnet et moufles", "maille", "100 % acrylique", "lot"),
    ("Bébé", "Salopette en jean", "denim", "100 % coton", "pièce"),
    ("Bébé", "Cardigan tricot", "maille", "50 % coton, 50 % acrylique", "pièce"),
    ("Chaussures", "Baskets en toile", "chaussure", "dessus textile, semelle caoutchouc", "pièce"),
    ("Chaussures", "Bottines à talon carré", "chaussure", "dessus synthétique, semelle TPR", "pièce"),
    ("Chaussures", "Chaussons fourrés", "chaussure", "dessus textile, doublure polyester", "pièce"),
    ("Chaussures", "Sandales à scratch enfant", "chaussure", "dessus synthétique, semelle EVA", "pièce"),
    ("Chaussures", "Baskets running légères", "chaussure", "dessus mesh, semelle EVA", "pièce"),
    ("Chaussures", "Bottes de pluie", "chaussure", "100 % caoutchouc naturel", "pièce"),
    ("Accessoires", "Écharpe maille douce", "maille", "100 % acrylique", "pièce"),
    ("Accessoires", "Casquette en coton", "accessoire", "100 % coton", "pièce"),
    ("Accessoires", "Sac cabas en toile", "accessoire", "100 % coton recyclé", "pièce"),
    ("Accessoires", "Ceinture tressée", "accessoire", "100 % polyester", "pièce"),
    ("Accessoires", "Chaussettes lot de 7", "coton", "75 % coton, 23 % polyamide, 2 % élasthanne", "lot"),
    ("Accessoires", "Bonnet côtelé", "maille", "100 % acrylique", "pièce"),
    ("Accessoires", "Lunettes de soleil enfant", "accessoire", "monture polycarbonate, filtre catégorie 3", "pièce"),
    ("Accessoires", "Gants tactiles", "maille", "100 % acrylique", "lot"),
    ("Accessoires", "Parapluie pliable", "accessoire", "toile polyester, armature acier", "pièce"),
    ("Accessoires", "Tote bag imprimé", "accessoire", "100 % coton", "pièce"),
]

ATELIERS = {
    "denim": [("Atelier Porto", "Portugal"), ("Marrakech Denim", "Maroc")],
    "coton": [("Tirupur Cotton", "Inde"), ("Dhaka Knit", "Bangladesh")],
    "maille": [("Izmir Tricot", "Turquie"), ("Atelier Roubaix", "France")],
    "synthetique": [("Ningbo Apparel", "Chine"), ("Hanoi Garment", "Vietnam")],
    "chaussure": [("Calzados Elche", "Espagne"), ("Dongguan Shoes", "Chine")],
    "accessoire": [("Atelier Lyonnais", "France"), ("Ningbo Apparel", "Chine")],
}

PRIX_HT = {
    "Homme": (9, 35), "Femme": (9, 35), "Fille": (6, 20), "Garçon": (6, 20),
    "Bébé": (5, 18), "Chaussures": (12, 30), "Accessoires": (3, 15),
}

TAILLES = {
    "Homme": "S au XXL", "Femme": "34 au 48", "Fille": "3 au 14 ans", "Garçon": "3 au 14 ans",
    "Bébé": "naissance au 36 mois", "Chaussures": "24 au 45 selon modèle",
    "Accessoires": "taille unique",
}

# Une consigne par famille : les guides d'une même famille ont un corps identique, seule la
# référence les distingue — le piège des notices Sorabel, reproduit à dessein.
ENTRETIEN = {
    "denim": ("Laver à l'envers avant la première utilisation, séparément.",
              "Lavage en machine à 30 °C, programme couleurs.",
              "Pas de sèche-linge. Repassage à l'envers, température moyenne.",
              "Ranger plié, à l'abri de la lumière directe pour préserver la teinte."),
    "coton": ("Laver avant la première utilisation avec des couleurs proches.",
              "Lavage en machine à 40 °C.",
              "Sèche-linge à basse température possible. Repassage à température moyenne.",
              "Ranger sec et plié."),
    "maille": ("Ne pas laisser tremper.",
               "Lavage en machine à 30 °C, programme laine, ou lavage à la main.",
               "Séchage à plat, jamais de sèche-linge. Pas de repassage direct.",
               "Ranger plié, jamais sur cintre, pour éviter la déformation."),
    "synthetique": ("Laver avant la première utilisation.",
                    "Lavage en machine à 30 °C, programme délicat.",
                    "Séchage sur cintre. Repassage doux, température basse.",
                    "Ranger sur cintre."),
    "chaussure": ("Imperméabiliser avant la première utilisation.",
                  "Ne pas laver en machine. Nettoyer à l'éponge humide et au savon doux.",
                  "Sécher à l'air libre, loin d'une source de chaleur.",
                  "Ranger au sec, garnies de papier pour garder la forme."),
    "accessoire": ("Aucune préparation nécessaire.",
                   "Nettoyage à la main à l'eau tiède savonneuse.",
                   "Sécher à l'air libre.",
                   "Ranger au sec."),
}

VILLES = [
    "Lille", "Roubaix", "Lens", "Arras", "Amiens", "Rouen", "Caen", "Rennes", "Nantes", "Angers",
    "Tours", "Orléans", "Paris Nation", "Créteil", "Cergy", "Reims", "Metz", "Nancy", "Strasbourg",
    "Mulhouse", "Dijon", "Besançon", "Lyon Part-Dieu", "Villeurbanne", "Grenoble", "Saint-Étienne",
    "Clermont-Ferrand", "Limoges", "Poitiers", "La Rochelle", "Bordeaux", "Mérignac", "Toulouse",
    "Montpellier", "Nîmes", "Marseille", "Toulon", "Nice", "Perpignan", "Pau",
]
SEGMENTS = ["franchise", "franchise", "succursale", "succursale", "succursale", "outlet"]
STATUTS = ["livree"] * 9 + ["expediee"] * 3 + ["annulee"] * 3 + ["en_attente"] * 3 + ["preparee"] * 2
AUTEURS = ["C. Lefebvre", "M. Dubois", "S. Martin", "A. Benali", "J. Moreau", "L. Nguyen"]
SAISONS = ["printemps-été 2025", "automne-hiver 2025", "printemps-été 2026", "automne-hiver 2026"]
DEFAUTS = [
    "décoloration au premier lavage", "couture d'entrejambe qui lâche",
    "fermeture éclair défectueuse", "boutons mal fixés", "rétrécissement supérieur à 5 %",
]


def _references(rng: random.Random) -> list[str]:
    """`REF-1024` est forcée sur le premier article : le client de démonstration
    (scripts/mcp_client.py) interroge sa marge, pour Sorabel comme pour Kiabi."""
    tirees = {"REF-1024"}
    while len(tirees) < len(CATALOGUE):
        tirees.add(f"REF-{rng.randint(1100, 9899)}")
    reste = sorted(tirees - {"REF-1024"})
    rng.shuffle(reste)
    return ["REF-1024", *reste]


def construire_catalogue(rng: random.Random) -> list[dict]:
    produits = []
    for reference, (categorie, nom, famille, composition, unite) in zip(_references(rng), CATALOGUE):
        atelier, origine = rng.choice(ATELIERS[famille])
        bas, haut = PRIX_HT[categorie]
        prix_vente = round(rng.uniform(bas, haut), 2)
        marge = round(rng.uniform(48, 68), 1)
        produits.append({
            "ref": reference, "nom": nom, "categorie": categorie, "famille": famille,
            "composition": composition, "unite": unite, "fabricant": atelier, "origine": origine,
            "prix_vente_ht": prix_vente, "marge_pct": marge,
            "prix_achat_ht": round(prix_vente * (1 - marge / 100), 2),
        })
    return produits


# --------------------------------------------------------------------------------------
# Base SQLite — même DDL que data/sorabel.db
# --------------------------------------------------------------------------------------
DDL = """
CREATE TABLE produits (
  ref TEXT PRIMARY KEY, nom TEXT NOT NULL, categorie TEXT NOT NULL,
  fabricant TEXT NOT NULL, unite TEXT NOT NULL,
  prix_vente_ht REAL NOT NULL, prix_achat_ht REAL NOT NULL, marge_pct REAL NOT NULL,
  actif INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE stocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT NOT NULL REFERENCES produits(ref),
  entrepot TEXT NOT NULL, quantite INTEGER NOT NULL, seuil_reappro INTEGER NOT NULL
);
CREATE TABLE clients (
  id TEXT PRIMARY KEY, raison_sociale TEXT NOT NULL, segment TEXT NOT NULL,
  ville TEXT NOT NULL, email TEXT NOT NULL
);
CREATE TABLE commandes (
  id TEXT PRIMARY KEY, client_id TEXT NOT NULL REFERENCES clients(id),
  date_commande TEXT NOT NULL, statut TEXT NOT NULL, montant_ht REAL NOT NULL
);
CREATE TABLE ventes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, commande_id TEXT NOT NULL REFERENCES commandes(id),
  ref TEXT NOT NULL REFERENCES produits(ref), quantite INTEGER NOT NULL,
  prix_unitaire_ht REAL NOT NULL, remise_pct REAL NOT NULL, marge_ht REAL NOT NULL
);
"""


def ecrire_base(rng: random.Random, produits: list[dict]) -> None:
    BASE.unlink(missing_ok=True)
    connexion = sqlite3.connect(BASE)
    try:
        connexion.executescript(DDL)
        connexion.executemany(
            "INSERT INTO produits VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            [(p["ref"], p["nom"], p["categorie"], p["fabricant"], p["unite"],
              p["prix_vente_ht"], p["prix_achat_ht"], p["marge_pct"]) for p in produits],
        )
        for p in produits:
            for entrepot in sorted(rng.sample(ENTREPOTS, rng.randint(2, 3))):
                connexion.execute(
                    "INSERT INTO stocks (ref, entrepot, quantite, seuil_reappro) VALUES (?, ?, ?, ?)",
                    (p["ref"], entrepot, rng.randint(0, 2500), rng.choice([100, 200, 300, 400])),
                )
        magasins = [
            (f"MAG-{1000 + i}", f"Kiabi {ville}", rng.choice(SEGMENTS), ville,
             f"magasin{i}@kiabi.example")
            for i, ville in enumerate(VILLES)
        ]
        connexion.executemany("INSERT INTO clients VALUES (?, ?, ?, ?, ?)", magasins)

        debut = date(2025, 9, 1)
        dates = sorted(debut + timedelta(days=rng.randint(0, 364)) for _ in range(300))
        compteurs: dict[int, int] = {}
        for jour in dates:
            compteurs[jour.year] = compteurs.get(jour.year, 0) + 1
            commande = f"CMD-{jour.year}-{compteurs[jour.year]:04d}"
            montant = 0.0
            for p in rng.sample(produits, rng.randint(1, 6)):
                quantite = rng.randint(20, 300)
                remise = rng.choice([0.0, 0.0, 0.0, 5.0, 10.0])
                prix = round(p["prix_vente_ht"] * (1 - remise / 100), 2)
                montant += prix * quantite
                connexion.execute(
                    "INSERT INTO ventes (commande_id, ref, quantite, prix_unitaire_ht, remise_pct,"
                    " marge_ht) VALUES (?, ?, ?, ?, ?, ?)",
                    (commande, p["ref"], quantite, prix, remise,
                     round((prix - p["prix_achat_ht"]) * quantite, 2)),
                )
            connexion.execute(
                "INSERT INTO commandes VALUES (?, ?, ?, ?, ?)",
                (commande, rng.choice(magasins)[0], jour.isoformat(), rng.choice(STATUTS),
                 round(montant, 2)),
            )
        connexion.commit()
    finally:
        connexion.close()


# --------------------------------------------------------------------------------------
# Corpus — mêmes gabarits que data/corpus/ (voir sorabel_rag/extraction.py)
# --------------------------------------------------------------------------------------
def _ecrire_pdf(chemin: Path, lignes: list[str]) -> None:
    pdf = FPDF()
    # Date figée : sans elle, chaque génération changerait l'empreinte des PDF, donc le cache
    # d'ingestion et le diff git, sans qu'un seul mot n'ait changé.
    pdf.set_creation_date(DATE_PDF)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for ligne in lignes:
        pdf.cell(0, 6, ligne, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(chemin))


def _ecrire_texte(chemin: Path, texte: str) -> None:
    chemin.write_text(texte, encoding="utf-8", newline="\n")


def _date(rng: random.Random, annee: int) -> str:
    return (date(annee, 1, 1) + timedelta(days=rng.randint(0, 360))).isoformat()


def ecrire_fiches(rng: random.Random, produits: list[dict]) -> None:
    dossier = CORPUS / "fiches"
    # Une fiche sur cinq a une v2.1 : changement de composition ou de prix, que la recherche
    # doit servir à la place de la v1.0 (filtre sur la version courante).
    revisees = {p["ref"] for p in produits[::5]}
    for p in produits:
        associes = rng.sample([q["ref"] for q in produits if q["categorie"] == p["categorie"]
                               and q["ref"] != p["ref"]], 2)
        versions = [("1.0", _date(rng, 2024), p["composition"], p["prix_vente_ht"])]
        if p["ref"] in revisees:
            nouvelle = (p["composition"].replace("100 % coton", "100 % coton biologique")
                        if "coton" in p["composition"] else p["composition"] + ", fibres recyclées")
            versions.append(("2.1", _date(rng, 2025), nouvelle, p["prix_vente_ht"]))
        for version, jour, composition, prix in versions:
            # Renvoi au guide plutôt que la consigne : le guide a ses propres versions (v2.0 à
            # 20 °C), et une fiche qui recopierait la consigne finirait par la contredire.
            entretien = f"voir le guide d'entretien {p['ref']}"
            _ecrire_pdf(dossier / f"{p['ref']}-v{version}.pdf", [
                f"FICHE PRODUIT - {p['nom']}",
                f"Référence produit : {p['ref']}",
                f"Version : {version}    Date : {jour}",
                f"Fabricant : {p['fabricant']}    Catégorie : {p['categorie']}",
                "Caractéristiques :",
                f"  - Composition : {composition}",
                f"  - Tailles : {TAILLES[p['categorie']]}",
                f"  - Entretien : {entretien}",
                f"  - Origine : {p['origine']}",
                f"Accessoires et produits associés : {', '.join(associes)}",
                f"Prix public HT : {prix:.2f} EUR / {p['unite']}",
                PIED_DE_PAGE,
            ])


def ecrire_guides(rng: random.Random, produits: list[dict]) -> None:
    dossier = CORPUS / "notices"
    # Deux versions pour un guide sur six : la v2.0 change la température de lavage, un fait
    # qui n'a de bonne réponse que sur la version courante.
    for index, p in enumerate(produits[:40]):
        avant, lavage, sechage, conservation = ENTRETIEN[p["famille"]]
        versions = [("1.0", _date(rng, 2024), lavage)]
        if index % 6 == 0 and "30 °C" in lavage:
            versions.append(("2.0", _date(rng, 2025), lavage.replace("30 °C", "20 °C")))
        for version, jour, consigne in versions:
            _ecrire_pdf(dossier / f"notice-{p['ref']}-v{version}.pdf", [
                f"GUIDE D'ENTRETIEN - {p['nom']}",
                f"Référence produit : {p['ref']}    Version : {version}    Date : {jour}",
                "1. Avant le premier lavage",
                f"   {avant}",
                "2. Lavage",
                f"   {consigne}",
                "3. Séchage et repassage",
                f"   {sechage}",
                "4. Conservation",
                f"   {conservation}",
                f"Service client Kiabi : service.client@kiabi.example - rappeler la référence {p['ref']}.",
            ])


def _corps_note(rng: random.Random, sous_type: str, p: dict) -> tuple[str, str]:
    saison = rng.choice(SAISONS)
    entrepot = rng.choice(ENTREPOTS).capitalize()
    if sous_type == "alerte-qualite":
        return "Alerte qualité", (
            f"Alerte qualité sur la référence {p['ref']} ({p['nom']}) : {rng.choice(DEFAUTS)} "
            f"signalé par {rng.randint(3, 25)} magasins. Retrait préventif des rayons et blocage "
            f"du réassort à l'entrepôt de {entrepot} jusqu'au retour du laboratoire.")
    if sous_type == "logistique":
        return "Point logistique réassort", (
            f"Réassort {saison} : l'entrepôt de {entrepot} expédie les commandes des magasins sous "
            f"{rng.randint(2, 6)} jours ouvrés. La référence {p['ref']} ({p['nom']}) est en "
            "tension ; priorité aux magasins en succursale.")
    if sous_type == "politique-tarifaire":
        return "Point politique tarifaire", (
            f"Revue des prix de la catégorie {p['categorie']}. La marge cible reste fixée à "
            f"{rng.randint(52, 62)} % par la direction commerciale ; démarque de "
            f"{rng.choice([20, 30, 40, 50])} % prévue sur la référence {p['ref']} pour les soldes "
            f"{saison}. Diffusion restreinte.")
    if sous_type == "retour-terrain":
        retour = rng.choice(["taille petit, prendre une taille au-dessus", "très bon retour client "
                             "sur la matière", "coloris plus foncé que sur le site",
                             "demandes fréquentes de la taille intermédiaire"])
        return "Retour terrain magasins", (
            f"Retour des magasins sur {p['nom']} ({p['ref']}) : {retour}. Les conseillers de "
            "vente relaient l'information en cabine.")
    return "Compte rendu réunion achats", (
        f"Réunion achats {saison} : renégociation avec {p['fabricant']} sur la référence "
        f"{p['ref']} ; objectif de prix d'achat en baisse de {rng.randint(3, 9)} %. Prochain "
        "point au comité de collection.")


def ecrire_notes(rng: random.Random, produits: list[dict]) -> None:
    dossier = CORPUS / "notes"
    sous_types = ["alerte-qualite", "logistique", "politique-tarifaire", "retour-terrain",
                  "reunion-achat"]
    for numero in range(1, 41):
        sous_type = sous_types[(numero - 1) % 5]
        jour = _date(rng, rng.choice([2025, 2026]))
        titre, corps = _corps_note(rng, sous_type, rng.choice(produits))
        _ecrire_texte(dossier / f"note-{jour}-{sous_type}-{numero:02d}.md", (
            f"---\ntitre: {titre}\ndate: {jour}\nauteur: {rng.choice(AUTEURS)}\n"
            f"type: note_interne\nversion: '1.0'\n---\n\n# {titre}\n\n{corps}\n"))


PROCEDURES = [
    ("retour-article-defectueux", "Article défectueux : retour en magasin et remboursement"),
    ("echange-taille", "Échange de taille ou de coloris"),
    ("colis-endommage", "Colis web reçu endommagé : constat et prise en charge"),
    ("erreur-reassort", "Erreur de préparation d'un réassort magasin"),
    ("remboursement-carte-cadeau", "Remboursement sur carte cadeau"),
    ("article-decolore", "Article décoloré ou rétréci au lavage"),
]


def ecrire_procedures(rng: random.Random, produits: list[dict]) -> None:
    dossier = CORPUS / "sav"
    for slug, libelle in PROCEDURES:
        for variante in ("01", "02"):
            versions = [("1.0", 30, _date(rng, 2024))]
            # La v2.0 allonge le délai de retour : seule la version courante fait foi.
            if variante == "01":
                versions.append(("2.0", 60, _date(rng, 2025)))
            exemple = rng.choice(produits)["ref"]
            for version, delai, jour in versions:
                titre = f"Procédure SAV — {libelle} ({variante})"
                _ecrire_texte(dossier / f"proc-{slug}-{variante}-v{version}.html", f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><title>{titre}</title>
<meta name="version" content="{version}"><meta name="date" content="{jour}">
<meta name="type" content="procedure_sav"></head>
<body>
<h1>{titre}</h1>
<p>Version {version} — mise à jour du {jour}. Applicable à tout le catalogue,
exemple traité sur la référence {exemple}. Données fictives de démonstration.</p>
<h2>Conditions</h2>
<ul><li>Article acheté dans un magasin du réseau ou sur le site, ticket ou commande retrouvable.</li>
<li>Demande formulée dans les {delai} jours suivant l'achat.</li></ul>
<h2>Étapes</h2>
<ol><li>Identifier l'article : demander la référence exacte (ex. {exemple}) et la date d'achat.</li>
<li>Ouvrir un dossier dans l'outil de caisse, joindre une photo si l'article est abîmé.</li>
<li>Selon le cas : échange immédiat, avoir sur carte cadeau ou remboursement.</li>
<li>Informer le client du délai : remboursement sous 5 jours ouvrés.</li></ol>
<h2>Cas hors périmètre</h2>
<p>Article porté et lavé hors consignes du guide d'entretien, ou acheté hors réseau :
transférer au responsable de magasin.</p>
</body></html>""")


def generer() -> None:
    rng = random.Random(GRAINE)
    if SORTIE.exists():
        shutil.rmtree(CORPUS, ignore_errors=True)
    for sous_dossier in ("fiches", "notices", "notes", "sav"):
        (CORPUS / sous_dossier).mkdir(parents=True, exist_ok=True)
    produits = construire_catalogue(rng)
    ecrire_base(rng, produits)
    ecrire_fiches(rng, produits)
    ecrire_guides(rng, produits)
    ecrire_notes(rng, produits)
    ecrire_procedures(rng, produits)


if __name__ == "__main__":
    generer()
    nombres = {d.name: len(list(d.iterdir())) for d in sorted(CORPUS.iterdir())}
    print(f"-> {BASE.relative_to(RACINE).as_posix()}")
    print(f"-> {CORPUS.relative_to(RACINE).as_posix()} : {nombres}")
