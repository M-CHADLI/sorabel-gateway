"""Un extracteur par format, tous avec le même contrat de sortie : `DocumentCanonique`.

C'est la seule couche du pipeline qui connaît l'existence du PDF, du HTML et du YAML.
Tout ce qui suit ne manipule que des canoniques.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .modeles import (
    TYPE_FICHE,
    TYPE_NOTE,
    TYPE_NOTICE,
    TYPE_SAV,
    DocumentCanonique,
    Qualite,
    Section,
    extraire_references,
    hacher_fichier,
    hacher_texte,
)

# --------------------------------------------------------------------------------------
# Motifs de nom de fichier — réf et version sont dans le nom pour les 230 PDF et le SAV.
# --------------------------------------------------------------------------------------
MOTIF_NOM_FICHE = re.compile(r"^(?P<reference>REF-\d{4})-v(?P<version>\d+\.\d+)$")
MOTIF_NOM_NOTICE = re.compile(r"^notice-(?P<reference>REF-\d{4})-v(?P<version>\d+\.\d+)$")
MOTIF_NOM_SAV = re.compile(r"^(?P<famille>proc-.+?)-v(?P<version>\d+\.\d+)$")

# `$` sans MULTILINE vaut fin de chaîne : sans le drapeau, le dernier champ d'une ligne
# (« Catégorie : … ») n'était jamais capturé.
MOTIF_CHAMP = re.compile(
    r"(Référence produit|Version|Date|Fabricant|Catégorie)\s*:\s*(\S[^:\n]*?)(?=\s{2,}\w+\s*:|$)",
    re.MULTILINE,
)
MOTIF_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
MOTIF_TITRE_NUMEROTE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")

# Seuils du contrôle qualité, par type de document (caractères).
SEUILS_LONGUEUR = {TYPE_FICHE: 200, TYPE_NOTICE: 200, TYPE_NOTE: 100, TYPE_SAV: 200}


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _lire_pdf(chemin: Path) -> str:
    lecteur = PdfReader(str(chemin))
    return "\n".join(page.extract_text() or "" for page in lecteur.pages)


def _controler(doc: DocumentCanonique, reference_attendue: bool) -> None:
    """Alimente `doc.qualite`. Sans ce contrôle, un document mal extrait disparaît
    silencieusement de l'index et personne ne s'en aperçoit avant la démonstration."""
    alertes = doc.qualite.alertes
    texte = doc.texte
    if not texte.strip():
        alertes.append("texte_vide")
    elif len(texte) < SEUILS_LONGUEUR.get(doc.type_document, 100):
        alertes.append("texte_court")
    if not doc.sections:
        alertes.append("aucune_section")
    if reference_attendue and not doc.reference:
        alertes.append("reference_absente")
    if not doc.date:
        alertes.append("date_absente")
    if not doc.titre:
        alertes.append("titre_absent")


# --------------------------------------------------------------------------------------
# Fiches techniques — 1 page, champs étiquetés, liste de caractéristiques à tirets.
# --------------------------------------------------------------------------------------
def extraire_fiche(chemin: Path) -> DocumentCanonique:
    correspondance = MOTIF_NOM_FICHE.match(chemin.stem)
    reference = correspondance["reference"] if correspondance else None
    version = correspondance["version"] if correspondance else "1.0"

    texte = _lire_pdf(chemin)
    lignes = [ligne.rstrip() for ligne in texte.splitlines()]

    titre = ""
    if lignes and " - " in lignes[0]:
        titre = lignes[0].split(" - ", 1)[1].strip()

    attributs = {
        cle.lower().replace(" ", "_"): valeur.strip()
        for cle, valeur in MOTIF_CHAMP.findall(texte)
        if cle not in ("Référence produit", "Version", "Date")
    }
    date = MOTIF_DATE.search(texte)

    identification = [
        ligne for ligne in lignes[1:]
        if ligne.strip() and not ligne.strip().startswith("-")
        and not ligne.startswith("Caractéristiques")
        and not ligne.startswith("Document Sorabel")
        and not ligne.startswith("Accessoires")
    ]
    caracteristiques = [ligne.strip().lstrip("- ").strip() for ligne in lignes if ligne.strip().startswith("-")]
    accessoires = [ligne.strip() for ligne in lignes if ligne.strip().startswith("Accessoires")]

    sections = [Section("Identification", "\n".join(identification).strip())]
    if caracteristiques:
        sections.append(Section("Caractéristiques", "\n".join(f"- {c}" for c in caracteristiques)))
    if accessoires:
        sections.append(Section("Accessoires et produits associés", "\n".join(accessoires)))

    doc = DocumentCanonique(
        doc_id=f"{TYPE_FICHE}:{reference}:v{version}",
        titre=titre,
        type_document=TYPE_FICHE,
        version=version,
        reference=reference,
        references_citees=extraire_references(texte, sauf=reference),
        date=date.group(1) if date else None,
        cle_groupe=f"{TYPE_FICHE}:{reference}",
        source_path=str(chemin).replace("\\", "/"),
        hash_source=hacher_fichier(chemin),
        hash_texte=hacher_texte(texte, titre, reference, date.group(1) if date else None),
        extrait_le=_maintenant(),
        attributs=attributs,
        sections=sections,
        qualite=Qualite(),
    )
    _controler(doc, reference_attendue=True)
    return doc


# --------------------------------------------------------------------------------------
# Notices — 1 page, sections numérotées « 1. Consignes de sécurité », « 2. Installation »…
# --------------------------------------------------------------------------------------
def extraire_notice(chemin: Path) -> DocumentCanonique:
    correspondance = MOTIF_NOM_NOTICE.match(chemin.stem)
    reference = correspondance["reference"] if correspondance else None
    version = correspondance["version"] if correspondance else "1.0"

    texte = _lire_pdf(chemin)
    lignes = [ligne.rstrip() for ligne in texte.splitlines()]

    titre = ""
    if lignes and " - " in lignes[0]:
        titre = lignes[0].split(" - ", 1)[1].strip()
    date = MOTIF_DATE.search(texte)

    sections: list[Section] = []
    entete: list[str] = []
    titre_courant, contenu_courant = None, []
    for ligne in lignes[1:]:
        numerote = MOTIF_TITRE_NUMEROTE.match(ligne)
        if numerote:
            if titre_courant:
                sections.append(Section(titre_courant, "\n".join(contenu_courant).strip()))
            titre_courant, contenu_courant = numerote.group(2), []
        elif titre_courant:
            contenu_courant.append(ligne.strip())
        elif ligne.strip():
            entete.append(ligne.strip())
    if titre_courant:
        sections.append(Section(titre_courant, "\n".join(contenu_courant).strip()))
    if entete:
        sections.insert(0, Section("Identification", "\n".join(entete)))

    doc = DocumentCanonique(
        doc_id=f"{TYPE_NOTICE}:{reference}:v{version}",
        titre=titre,
        type_document=TYPE_NOTICE,
        version=version,
        reference=reference,
        references_citees=extraire_references(texte, sauf=reference),
        date=date.group(1) if date else None,
        cle_groupe=f"{TYPE_NOTICE}:{reference}",
        source_path=str(chemin).replace("\\", "/"),
        hash_source=hacher_fichier(chemin),
        hash_texte=hacher_texte(texte, titre, reference, date.group(1) if date else None),
        extrait_le=_maintenant(),
        sections=sections,
        qualite=Qualite(),
    )
    _controler(doc, reference_attendue=True)
    return doc


# --------------------------------------------------------------------------------------
# Notes internes — front-matter YAML ; la référence n'est que dans le corps, si elle y est.
# --------------------------------------------------------------------------------------
def extraire_note(chemin: Path) -> DocumentCanonique:
    brut = chemin.read_text(encoding="utf-8")
    entete: dict = {}
    corps = brut
    if brut.startswith("---"):
        _, bloc, corps = brut.split("---", 2)
        entete = yaml.safe_load(bloc) or {}

    corps = corps.strip()
    # Le titre H1 répète le front-matter : on ne le garde pas dans le contenu.
    lignes = [ligne for ligne in corps.splitlines() if not ligne.startswith("# ")]
    corps_propre = "\n".join(lignes).strip()

    references = extraire_references(corps)
    reference = references[0] if references else None
    version = str(entete.get("version", "1.0"))
    date = entete.get("date")

    doc = DocumentCanonique(
        doc_id=f"{TYPE_NOTE}:{chemin.stem}:v{version}",
        titre=str(entete.get("titre", "")).strip(),
        type_document=TYPE_NOTE,
        version=version,
        reference=reference,
        references_citees=references[1:],
        date=str(date) if date else None,
        cle_groupe=f"{TYPE_NOTE}:{chemin.stem}",
        source_path=str(chemin).replace("\\", "/"),
        hash_source=hacher_fichier(chemin),
        hash_texte=hacher_texte(corps_propre, str(entete.get('titre', '')), reference, str(date) if date else None),
        extrait_le=_maintenant(),
        attributs={
            cle: str(valeur)
            for cle, valeur in entete.items()
            if cle in ("auteur", "type") and valeur
        },
        sections=[Section("", corps_propre)] if corps_propre else [],
        qualite=Qualite(),
    )
    # 16 notes sur 80 ne citent aucune référence : c'est normal, pas une anomalie.
    _controler(doc, reference_attendue=False)
    return doc


# --------------------------------------------------------------------------------------
# Procédures SAV — HTML, exactement 3 <h2>. Le groupement se fait sur la FAMILLE.
# --------------------------------------------------------------------------------------
def extraire_procedure_sav(chemin: Path) -> DocumentCanonique:
    correspondance = MOTIF_NOM_SAV.match(chemin.stem)
    famille = correspondance["famille"] if correspondance else chemin.stem
    version_nom = correspondance["version"] if correspondance else None

    soupe = BeautifulSoup(chemin.read_text(encoding="utf-8"), "html.parser")

    def meta(nom: str) -> str | None:
        balise = soupe.find("meta", attrs={"name": nom})
        return balise.get("content") if balise else None

    titre = soupe.title.get_text(strip=True) if soupe.title else ""
    version = meta("version") or version_nom or "1.0"

    sections: list[Section] = []
    intro = soupe.find("h1")
    if intro:
        paragraphes = []
        for element in intro.find_next_siblings():
            if element.name == "h2":
                break
            paragraphes.append(element.get_text(" ", strip=True))
        if any(paragraphes):
            sections.append(Section("Objet", "\n".join(p for p in paragraphes if p)))

    for titre_h2 in soupe.find_all("h2"):
        contenu = []
        for element in titre_h2.find_next_siblings():
            if element.name == "h2":
                break
            contenu.append(element.get_text("\n", strip=True))
        sections.append(Section(titre_h2.get_text(strip=True), "\n".join(contenu).strip()))

    texte_complet = soupe.get_text(" ", strip=True)
    # Vérifié sur les 90 procédures : la référence citée est toujours un EXEMPLE
    # (« Applicable à tout le catalogue, exemple traité sur la référence REF-9196 »).
    # La mettre dans `reference` ferait remonter une procédure générique de casse transport
    # sur une recherche « REF-9196 », comme si elle portait sur ce produit. Une procédure
    # SAV n'a pas de référence sujet : tout part dans `references_citees`.
    references = extraire_references(texte_complet)

    doc = DocumentCanonique(
        doc_id=f"{TYPE_SAV}:{famille}:v{version}",
        titre=titre,
        type_document=TYPE_SAV,
        version=version,
        reference=None,
        references_citees=references,
        date=meta("date"),
        # La famille, pas le nom de fichier : `proc-casse-transport-01` regroupe v1.0 et v2.0.
        cle_groupe=f"{TYPE_SAV}:{famille}",
        source_path=str(chemin).replace("\\", "/"),
        hash_source=hacher_fichier(chemin),
        hash_texte=hacher_texte(texte_complet, titre, None, meta('date')),
        extrait_le=_maintenant(),
        attributs={"famille": famille, "type_declare": meta("type") or ""},
        sections=sections,
        qualite=Qualite(),
    )
    # Une procédure est générique : elle peut ne citer aucune référence en exemple.
    _controler(doc, reference_attendue=False)
    return doc


EXTRACTEURS = {
    "fiches": (extraire_fiche, "*.pdf"),
    "notices": (extraire_notice, "*.pdf"),
    "notes": (extraire_note, "*.md"),
    "sav": (extraire_procedure_sav, "*.html"),
}
