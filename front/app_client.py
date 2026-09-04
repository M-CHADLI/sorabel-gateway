"""Poste commercial Sorabel — interface métier de la Data Gateway.

Organisée autour du travail réel d'un commercial (préparer une visite, répondre à un client
sur une référence, suivre une commande) et non autour du catalogue de tools : une fiche
produit rassemble ici documentation, stock et conditions tarifaires, là où le serveur expose
trois tools distincts.

Direction visuelle : Minimalism & Swiss Style (grille, contraste élevé, typographie
fonctionnelle) — registre adapté aux outils métier denses. Fira Sans porte l'interface,
Fira Code les données à lire au caractère près (références, identifiants, SQL).

Tout passe par le serveur MCP (`front.mcp_client`) : la page n'applique aucune règle d'accès
elle-même, elle reflète ce que la matrice autorise pour le profil connecté. Les garanties du
brief s'y retrouvent — sources citées (E1), SQL exécuté ou rejeté toujours visible (E3),
tools masqués hors périmètre (E4), refus traduits en message clair et jamais confondus avec
une panne (E5).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import re

import streamlit as st

from front.mcp_client import appeler, lister_tools

st.set_page_config(page_title="Sorabel — Poste commercial", layout="wide")

# Le titre suit le profil : afficher « Poste commercial » à un technicien du support
# donnerait à croire qu'il travaille dans le mauvais outil.
PROFILS = {
    "commercial": ("Commercial", "Poste commercial"),
    "support": ("Support client", "Poste support"),
    "admin": ("Exploitation", "Console d'exploitation"),
    "dev": ("Développeur", "Console d'intégration"),
}

# Références réelles du catalogue, proposées en exemple : un champ vide n'apprend rien du
# format attendu, et le premier essai d'un nouvel utilisateur échoue le plus souvent dessus.
REFERENCES_EXEMPLE = ["REF-8842", "REF-1024", "REF-5719", "REF-3764"]


def appliquer_exemple(cle_champ: str) -> None:
    """Reporte dans le champ la valeur choisie au run précédent.

    Streamlit interdit d'écrire dans `session_state[clé]` une fois le widget de même clé
    créé : un bouton d'exemple, rendu après le champ, ne peut donc pas le remplir
    directement. Il dépose sa valeur dans une clé tampon, transférée ici avant que le
    widget n'existe.
    """
    tampon = f"_attente_{cle_champ}"
    if tampon in st.session_state:
        st.session_state[cle_champ] = st.session_state.pop(tampon)


def proposer_exemple(cle_champ: str, valeur: str, cle_bouton: str, colonne=None) -> None:
    cible = colonne if colonne is not None else st
    if cible.button(valeur, key=cle_bouton, use_container_width=True):
        st.session_state[f"_attente_{cle_champ}"] = valeur
        st.rerun()

MOTIF_REFERENCE = re.compile(r"REF-\d{4}", re.IGNORECASE)

# Un refus n'est pas une panne : chaque statut a son registre et son conseil de reprise,
# pour que l'utilisateur sache s'il doit reformuler, demander un droit ou signaler un
# incident. Une erreur sans issue est un cul-de-sac.
REFUS = {
    "hors_corpus": (
        "info",
        "Aucun document du corpus ne traite ce sujet.",
        "Reformulez avec les termes du catalogue, ou cherchez par référence (REF-XXXX).",
    ),
    "hors_schema": (
        "warning",
        "Cette question ne correspond à aucune donnée disponible.",
        "Consultez « Données consultables par votre profil » pour voir ce qui est interrogeable.",
    ),
    "non_autorise": (
        "warning",
        "Votre profil n'a pas accès à cette information.",
        "Demandez l'accès à l'exploitation si votre mission le justifie.",
    ),
    "refuse_ecriture": (
        "error",
        "Refusé : seule la consultation des données est autorisée.",
        "Aucune modification n'est possible depuis cet outil, par conception.",
    ),
    "erreur": (
        "error",
        "Incident technique — l'information n'a pas pu être récupérée.",
        "Relancez la recherche ; si l'incident persiste, signalez-le à l'exploitation.",
    ),
}

# SVG plutôt qu'emoji : un emoji change de dessin selon la plateforme, n'est pas
# redimensionnable proprement et se fait lire à voix haute par les lecteurs d'écran.
LOGO = """<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>"""

STYLE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@400;500;600;700&display=swap');

  :root {
    --encre:        #0F172A;
    --encre-douce:  #475569;
    --bord:         #E2E8F0;
    --fond-doux:    #F8FAFC;
    --accent:       #1D4ED8;
    --succes:       #15803D;
    --succes-fond:  #DCFCE7;
    --alerte:       #B91C1C;
    --alerte-fond:  #FEE2E2;
    --transition:   180ms ease;
  }

  html, body, [class*="css"], .stMarkdown, button, input, select, textarea {
    font-family: 'Fira Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
  }
  .block-container { padding-top: 2rem; max-width: 1200px; }

  /* Contraste : 4.5:1 minimum sur tout le texte courant. */
  .stMarkdown, .stMarkdown p, label, .stCaption { color: var(--encre); }
  .stCaption, [data-testid="stCaptionContainer"] { color: var(--encre-douce) !important; }

  .bandeau {
    display: flex; align-items: center; gap: .6rem;
    border-bottom: 1px solid var(--bord); padding-bottom: .8rem; margin-bottom: 1.1rem;
    color: var(--encre);
  }
  .bandeau .titre { font-size: 1.4rem; font-weight: 650; letter-spacing: -.02em; }
  .bandeau .profil {
    margin-left: auto; font-size: .78rem; color: var(--encre-douce);
    font-family: 'Fira Code', monospace; background: var(--fond-doux);
    border: 1px solid var(--bord); border-radius: 4px; padding: .2rem .55rem;
  }

  /* La zone de saisie est le point d'entrée de chaque onglet : elle doit se lire comme un
     bloc, pas comme un champ perdu au milieu du blanc. */
  .panneau {
    border: 1px solid var(--bord); border-radius: 10px;
    background: linear-gradient(180deg, #fff 0%, var(--fond-doux) 100%);
    padding: 1.1rem 1.25rem .4rem; margin-bottom: 1.1rem;
  }
  .panneau .intitule { font-size: 1.02rem; font-weight: 650; color: var(--encre); }
  .panneau .aide { font-size: .85rem; color: var(--encre-douce); margin-top: .15rem; }

  .rappel {
    display: flex; gap: 1.4rem; flex-wrap: wrap;
    border: 1px solid var(--bord); border-radius: 8px; background: #fff;
    padding: .7rem 1rem; margin-bottom: 1.1rem;
  }
  .rappel .item { display: flex; flex-direction: column; gap: .1rem; }
  .rappel .valeur {
    font-family: 'Fira Code', monospace; font-weight: 600; color: var(--encre); font-size: .95rem;
  }

  .carte {
    border: 1px solid var(--bord); border-radius: 8px; padding: .9rem 1.05rem;
    background: #fff; margin-bottom: .8rem; transition: border-color var(--transition);
  }
  .carte:hover { border-color: #CBD5E1; }
  .carte .entete { font-weight: 600; color: var(--encre); margin-bottom: .3rem; }
  .carte .meta   { font-size: .82rem; color: var(--encre-douce); font-family: 'Fira Code', monospace; }

  .source {
    border-left: 3px solid var(--accent); background: var(--fond-doux);
    padding: .55rem .8rem; border-radius: 0 6px 6px 0; margin-bottom: .45rem;
  }
  .source .titre { font-weight: 600; font-size: .9rem; color: var(--encre); }
  .source .meta  { font-size: .78rem; color: var(--encre-douce); font-family: 'Fira Code', monospace; }

  .etiquette {
    display: inline-block; padding: .16rem .55rem; border-radius: 4px;
    font-size: .74rem; font-weight: 600; font-family: 'Fira Code', monospace;
  }
  .vert  { background: var(--succes-fond); color: var(--succes); }
  .rouge { background: var(--alerte-fond); color: var(--alerte); }
  .gris  { background: #F1F5F9; color: #334155; }

  .chiffre {
    font-family: 'Fira Code', monospace; font-size: 1.55rem; font-weight: 600;
    color: var(--encre); line-height: 1.2;
  }
  .legende {
    font-size: .74rem; color: var(--encre-douce); text-transform: uppercase;
    letter-spacing: .05em; font-weight: 500; margin-bottom: .15rem;
  }

  /* Les réponses rédigées sont de la prose : au-delà de ~75 caractères par ligne, l'œil
     perd le début de la ligne suivante. */
  .prose { max-width: 68ch; line-height: 1.6; color: var(--encre); }

  .etapes {
    font-family: 'Fira Code', monospace; font-size: .8rem; color: var(--encre-douce);
    margin-bottom: .6rem;
  }
  .etapes .fait   { color: var(--succes); }
  .etapes .encours{ color: var(--accent); font-weight: 600; }

  .vide {
    border: 1px dashed var(--bord); border-radius: 8px; padding: 1.4rem;
    text-align: center; color: var(--encre-douce); background: var(--fond-doux);
  }

  /* Le focus clavier doit rester visible : c'est le seul repère de position pour qui
     n'utilise pas la souris. */
  button:focus-visible, input:focus-visible, select:focus-visible, [role="tab"]:focus-visible {
    outline: 2px solid var(--accent) !important; outline-offset: 2px !important;
  }
  .stButton > button { cursor: pointer; transition: background var(--transition), border-color var(--transition); }
  .stTabs [data-baseweb="tab"] { cursor: pointer; }
  code, pre, .stCode { font-family: 'Fira Code', monospace !important; }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition-duration: .01ms !important; animation-duration: .01ms !important; }
  }
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)


# --- présentation ----------------------------------------------------------------------


def afficher_refus(resultat: dict, cle_reprise: str | None = None) -> None:
    """Message + issue de sortie. `role=alert` fait annoncer l'incident aux lecteurs
    d'écran, qui ne voient pas la couleur du bandeau."""
    statut = resultat.get("statut", "erreur")
    niveau, defaut, conseil = REFUS.get(statut, REFUS["erreur"])
    getattr(st, niveau)(resultat.get("message") or defaut)
    st.markdown(
        f"<div role='alert' style='font-size:.85rem;color:var(--encre-douce);"
        f"margin:-.4rem 0 .6rem'>{conseil}</div>",
        unsafe_allow_html=True,
    )
    if statut == "erreur" and cle_reprise:
        st.button("Réessayer", key=cle_reprise)


def afficher_vide(message: str, suggestion: str) -> None:
    st.markdown(
        f"<div class='vide'><div style='font-weight:600;color:var(--encre)'>{message}</div>"
        f"<div style='font-size:.85rem;margin-top:.3rem'>{suggestion}</div></div>",
        unsafe_allow_html=True,
    )


def afficher_etapes(etapes: list[str], courante: int) -> None:
    """Une attente de plusieurs secondes sans repère passe pour un blocage."""
    rendu = []
    for i, nom in enumerate(etapes):
        classe = "fait" if i < courante else ("encours" if i == courante else "")
        marque = "✓" if i < courante else ("▸" if i == courante else "·")
        rendu.append(f"<span class='{classe}'>{marque} {nom}</span>")
    st.markdown(
        f"<div class='etapes'>Étape {min(courante + 1, len(etapes))} sur {len(etapes)} &nbsp;&nbsp;"
        + " &nbsp; ".join(rendu)
        + "</div>",
        unsafe_allow_html=True,
    )


def afficher_sources(citations: list[dict]) -> None:
    if not citations:
        return
    st.markdown("**Sources**")
    for c in citations:
        meta = " · ".join(p for p in (c.get("reference"), c.get("date")) if p)
        st.markdown(
            f"<div class='source'><div class='titre'>{c.get('titre', 'Document')}</div>"
            f"<div class='meta'>{meta}</div></div>",
            unsafe_allow_html=True,
        )


def afficher_reponse(texte: str) -> None:
    st.markdown(f"<div class='prose'>{texte}</div>", unsafe_allow_html=True)


def afficher_sql(resultat: dict) -> None:
    """E3 : la requête est montrée qu'elle ait été exécutée ou rejetée."""
    if resultat.get("sql"):
        with st.expander("Requête SQL"):
            st.code(resultat["sql"], language="sql")


def afficher_tableau(resultat: dict, suggestion: str) -> None:
    colonnes, lignes = resultat.get("colonnes", []), resultat.get("lignes", [])
    if not lignes:
        afficher_vide("Aucune donnée ne correspond", suggestion)
        return
    st.dataframe(
        [dict(zip(colonnes, ligne)) for ligne in lignes], use_container_width=True
    )
    if resultat.get("tronque"):
        st.caption(f"Affichage limité aux {len(lignes)} premières lignes.")


# --- vues métier -----------------------------------------------------------------------


def vue_produit(profil: str, tools: list[str]) -> None:
    st.markdown(
        "<div class='panneau'><div class='intitule'>Consulter une référence</div>"
        "<div class='aide'>Stock par entrepôt, conditions tarifaires et documentation "
        "technique, rassemblés en une vue.</div></div>",
        unsafe_allow_html=True,
    )

    appliquer_exemple("ref_produit")
    champ, action = st.columns([4, 1])
    with champ:
        saisie = st.text_input(
            "Référence produit", placeholder="REF-8842", key="ref_produit"
        )
    with action:
        st.markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
        lancer = st.button("Consulter", key="btn_produit", type="primary", use_container_width=True)

    st.caption("Références du catalogue, pour essayer :")
    for exemple, colonne in zip(REFERENCES_EXEMPLE, st.columns(len(REFERENCES_EXEMPLE) + 3)):
        proposer_exemple("ref_produit", exemple, f"ex_{exemple}", colonne)

    reference = saisie.strip().upper()
    if not lancer or not reference:
        return
    if not MOTIF_REFERENCE.fullmatch(reference):
        st.warning("Format attendu : REF-XXXX (quatre chiffres). Exemple : REF-8842.")
        return

    st.divider()

    etapes = [e for e, t in [("Stock", "check_stock"), ("Conditions", "ask_database"),
                             ("Documentation", "answer_question")] if t in tools]
    suivi = st.empty()

    if "check_stock" in tools:
        with suivi.container():
            afficher_etapes(etapes, 0)
        st.markdown("#### Disponibilité")
        stock = appeler(profil, "check_stock", {"ref": reference})
        if stock.get("statut") == "ok":
            colonnes, lignes = stock.get("colonnes", []), stock.get("lignes", [])
            if not lignes:
                afficher_vide(
                    "Aucun stock enregistré",
                    "La référence existe peut-être au catalogue sans être stockée.",
                )
            else:
                for entrepot, colonne in zip(lignes, st.columns(len(lignes))):
                    donnees = dict(zip(colonnes, entrepot))
                    quantite = donnees.get("quantite", 0)
                    sous_seuil = quantite < donnees.get("seuil_reappro", 0)
                    with colonne:
                        st.markdown(
                            f"<div class='carte'>"
                            f"<div class='legende'>{donnees.get('entrepot', '')}</div>"
                            f"<div class='chiffre'>{quantite}</div>"
                            f"<span class='etiquette {'rouge' if sous_seuil else 'vert'}'>"
                            f"{'sous le seuil' if sous_seuil else 'disponible'}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
        else:
            afficher_refus(stock, "reprise_stock")

    if "ask_database" in tools:
        with suivi.container():
            afficher_etapes(etapes, etapes.index("Conditions"))
        st.markdown("#### Conditions commerciales")
        conditions = appeler(
            profil,
            "ask_database",
            {"question": f"donne le nom, la catégorie et le prix de vente du produit {reference}"},
        )
        if conditions.get("statut") == "ok":
            afficher_tableau(conditions, f"{reference} n'est peut-être plus au catalogue.")
        else:
            afficher_refus(conditions, "reprise_conditions")
        afficher_sql(conditions)

    if "answer_question" in tools:
        with suivi.container():
            afficher_etapes(etapes, etapes.index("Documentation"))
        st.markdown("#### Ce que dit la documentation")
        doc = appeler(
            profil,
            "answer_question",
            {"question": f"quelles sont les caractéristiques techniques du {reference} ?"},
        )
        if doc.get("statut") == "ok":
            afficher_reponse(doc["reponse"])
            afficher_sources(doc.get("citations", []))
        else:
            afficher_refus(doc, "reprise_doc")

    suivi.empty()


QUESTIONS_EXEMPLE = [
    "Quel disjoncteur pour un départ moteur en triphasé ?",
    "Quelle est la procédure de retour d'un produit défectueux ?",
    "Que faire quand un disjoncteur déclenche de façon répétée ?",
]


def vue_question(profil: str, tools: list[str]) -> None:
    st.markdown(
        "<div class='panneau'><div class='intitule'>Interroger la documentation</div>"
        "<div class='aide'>Fiches techniques, notices et procédures SAV. Chaque réponse "
        "cite ses sources ; hors du corpus, l'assistant le dit plutôt que d'inventer."
        "</div></div>",
        unsafe_allow_html=True,
    )
    appliquer_exemple("question_doc")
    question = st.text_input(
        "Votre question",
        placeholder="Quel disjoncteur pour un départ moteur en triphasé ?",
        key="question_doc",
    )
    st.caption("Exemples couverts par le corpus :")
    for indice, exemple in enumerate(QUESTIONS_EXEMPLE):
        proposer_exemple("question_doc", exemple, f"q_{indice}")

    if st.button("Rechercher", key="btn_question", type="primary") and question:
        with st.spinner("Analyse du corpus documentaire — une dizaine de secondes…"):
            resultat = appeler(profil, "answer_question", {"question": question})
        if resultat.get("statut") == "ok":
            afficher_reponse(resultat["reponse"])
            afficher_sources(resultat.get("citations", []))
        else:
            afficher_refus(resultat, "reprise_question")


def vue_donnees(profil: str, tools: list[str]) -> None:
    st.subheader("Interroger les données")
    st.caption(
        "Produits, stocks, clients, commandes et ventes, en langage naturel. "
        "Consultation seule : la requête produite reste toujours consultable."
    )
    question = st.text_input(
        "Votre question", placeholder="Combien de commandes en avril ?", key="question_sql"
    )
    if st.button("Interroger", key="btn_donnees", type="primary") and question:
        with st.spinner("Interrogation de la base…"):
            resultat = appeler(profil, "ask_database", {"question": question})
        if resultat.get("statut") == "ok":
            afficher_tableau(
                resultat, "Essayez en nommant explicitement la table ou la période."
            )
        else:
            afficher_refus(resultat, "reprise_donnees")
        afficher_sql(resultat)

    if "get_schema" in tools:
        with st.expander("Données consultables par votre profil"):
            schema = appeler(profil, "get_schema", {})
            if schema.get("statut") == "ok":
                st.code(schema["schema"], language="sql")
            else:
                afficher_refus(schema)


def vue_commande(profil: str, tools: list[str]) -> None:
    st.subheader("Suivre une commande")
    identifiant = (
        st.text_input("Identifiant de commande", placeholder="CMD-2025-0004", key="id_commande")
        .strip()
        .upper()
    )
    if st.button("Rechercher", key="btn_commande", type="primary") and identifiant:
        resultat = appeler(profil, "order_status", {"order_id": identifiant})
        if resultat.get("statut") != "ok":
            afficher_refus(resultat, "reprise_commande")
            return
        colonnes, lignes = resultat.get("colonnes", []), resultat.get("lignes", [])
        if not lignes:
            afficher_vide(
                "Aucune commande à cet identifiant",
                "Vérifiez le format : CMD-AAAA-NNNN, par exemple CMD-2025-0004.",
            )
            return
        donnees = dict(zip(colonnes, lignes[0]))
        for (libelle, valeur), colonne in zip(
            [
                ("Statut", donnees.get("statut", "—")),
                ("Date", donnees.get("date_commande", "—")),
                ("Montant HT", f"{donnees.get('montant_ht', 0):,.2f} €".replace(",", " ")),
            ],
            st.columns(3),
        ):
            with colonne:
                st.markdown(
                    f"<div class='carte'><div class='legende'>{libelle}</div>"
                    f"<div class='chiffre'>{valeur}</div></div>",
                    unsafe_allow_html=True,
                )


def vue_recherche(profil: str, tools: list[str]) -> None:
    """`search_docs` : les extraits bruts et leurs scores, sans passer par le LLM.

    C'est la brique du RAG utile à qui veut juger la source lui-même — un intégrateur, ou
    un technicien qui préfère lire le passage d'origine plutôt qu'une reformulation.
    """
    st.markdown(
        "<div class='panneau'><div class='intitule'>Rechercher sans générer</div>"
        "<div class='aide'>Extraits classés par pertinence, sans reformulation : vous lisez "
        "le texte d'origine. Plus rapide qu'une réponse rédigée.</div></div>",
        unsafe_allow_html=True,
    )
    requete = st.text_input("Termes recherchés", placeholder="REF-8842", key="requete_docs")
    nombre = st.slider("Nombre d'extraits", 1, 10, 5, key="k_docs")

    if st.button("Rechercher", key="btn_recherche", type="primary") and requete:
        with st.spinner("Recherche dans le corpus…"):
            resultat = appeler(
                profil, "search_docs", {"requete": requete, "k": nombre}
            )
        if resultat.get("statut") != "ok":
            afficher_refus(resultat, "reprise_recherche")
            return
        extraits = resultat.get("resultats", [])
        if not extraits:
            afficher_vide(
                "Aucun extrait ne correspond",
                "Essayez une référence (REF-XXXX) ou des termes du catalogue.",
            )
            return
        for extrait in extraits:
            st.markdown(
                f"<div class='carte'><div class='entete'>{extrait.get('titre', '')}</div>"
                f"<div class='meta'>{extrait.get('reference') or '—'} · "
                f"pertinence {extrait.get('score', 0):.3f} · "
                f"{extrait.get('chunk_id', '')}</div></div>",
                unsafe_allow_html=True,
            )
            with st.expander("Lire l'extrait"):
                st.markdown(
                    f"<div class='prose'>{extrait.get('texte', '')}</div>",
                    unsafe_allow_html=True,
                )


def vue_document(profil: str, tools: list[str]) -> None:
    """`get_document` : le document canonique complet, par identifiant ou par référence."""
    st.markdown(
        "<div class='panneau'><div class='intitule'>Ouvrir un document</div>"
        "<div class='aide'>Par référence produit, ou par identifiant exact repéré dans une "
        "recherche. Sans version précisée, la version courante est servie.</div></div>",
        unsafe_allow_html=True,
    )
    par_reference, par_identifiant = st.columns(2)
    with par_reference:
        reference = st.text_input("Référence produit", placeholder="REF-1024", key="doc_ref")
        version = st.text_input("Version (facultatif)", placeholder="2.1", key="doc_version")
    with par_identifiant:
        doc_id = st.text_input(
            "Ou identifiant du document",
            placeholder="fiche_technique:REF-1024:v2.1",
            key="doc_id",
        )

    if st.button("Ouvrir", key="btn_document", type="primary"):
        if not (reference or doc_id):
            st.warning("Renseignez une référence produit ou un identifiant de document.")
            return
        resultat = appeler(
            profil,
            "get_document",
            {
                "doc_id": doc_id or None,
                "reference": reference.strip().upper() or None,
                "version": version.strip() or None,
            },
        )
        if resultat.get("statut") != "ok":
            afficher_refus(resultat, "reprise_document")
            return
        document = resultat.get("document", {})
        st.markdown(
            f"<div class='carte'><div class='entete'>{document.get('titre', '')}</div>"
            f"<div class='meta'>{document.get('reference') or '—'} · "
            f"{document.get('type_document', '').replace('_', ' ')} · "
            f"version {document.get('version', '')} · {document.get('date', '')}</div></div>",
            unsafe_allow_html=True,
        )
        # Le canonique conserve le document découpé en sections : les restituer telles
        # quelles préserve la structure d'origine, qu'un aplatissement effacerait.
        for section in document.get("sections", []):
            st.markdown(f"##### {section.get('titre', '')}")
            st.markdown(
                f"<div class='prose'>{section.get('contenu', '').replace(chr(10), '<br>')}</div>",
                unsafe_allow_html=True,
            )
        if references := document.get("references_citees"):
            st.caption("Références citées : " + ", ".join(references))


def vue_inventaire(profil: str, tools: list[str]) -> None:
    st.markdown(
        "<div class='panneau'><div class='intitule'>Inventaire du corpus</div>"
        "<div class='aide'>Documents indexés et leurs versions, restreints au périmètre de "
        "votre profil.</div></div>",
        unsafe_allow_html=True,
    )
    type_document = st.selectbox(
        "Type de document",
        [None, "fiche_technique", "notice", "procedure_sav", "note_interne"],
        format_func=lambda t: "Tous les types" if t is None else t.replace("_", " "),
        key="type_doc",
    )
    if st.button("Afficher", key="btn_sources", type="primary"):
        resultat = appeler(profil, "list_sources", {"type_document": type_document})
        if resultat.get("statut") != "ok":
            afficher_refus(resultat, "reprise_sources")
            return
        sources = resultat.get("sources", [])
        if not sources:
            afficher_vide(
                "Aucun document de ce type",
                "Choisissez « Tous les types », ou vérifiez les droits de votre profil.",
            )
            return
        st.caption(f"{len(sources)} document(s) accessible(s).")
        for source in sources[:60]:
            versions = ", ".join(source.get("versions", []))
            st.markdown(
                f"<div class='carte'><div class='entete'>{source.get('titre', '')}</div>"
                f"<div class='meta'>{source.get('reference') or '—'} · "
                f"{source.get('type_document', '').replace('_', ' ')} · "
                f"versions {versions} (courante {source.get('version_courante', '')})</div></div>",
                unsafe_allow_html=True,
            )


# --- assemblage ------------------------------------------------------------------------

def vue_documentation(profil: str, tools: list[str]) -> None:
    """Les quatre briques documentaires derrière une sous-navigation.

    Une barre principale à sept entrées deviendrait illisible ; regrouper ce qui relève du
    même geste métier — se documenter — la ramène à quatre. Le découpage rend aussi visible
    que les briques du RAG s'utilisent séparément : répondre, chercher, ouvrir, inventorier.
    """
    modes = [
        ("Réponse rédigée", "answer_question", vue_question),
        ("Recherche brute", "search_docs", vue_recherche),
        ("Ouvrir un document", "get_document", vue_document),
        ("Inventaire", "list_sources", vue_inventaire),
    ]
    disponibles = [(libelle, vue) for libelle, tool, vue in modes if tool in tools]
    if not disponibles:
        afficher_vide(
            "Aucune fonction documentaire accordée",
            "Votre profil n'a de droit sur aucun tool du corpus.",
        )
        return

    choix = st.radio(
        "Mode de consultation",
        [libelle for libelle, _ in disponibles],
        horizontal=True,
        key="mode_doc",
        label_visibility="collapsed",
    )
    dict(disponibles)[choix](profil, tools)


# Quatre entrées principales : la navigation reste sous le seuil au-delà duquel elle cesse
# d'être lisible d'un coup d'œil, et chaque entrée correspond à un geste métier entier.
# Une entrée s'affiche dès qu'un seul de ses outils est accordé — le profil `dev`, privé
# de réponse rédigée, garde ainsi la recherche brute et la lecture de documents.
VUES = [
    ("Produit", ["check_stock"], vue_produit),
    (
        "Documentation",
        ["answer_question", "search_docs", "get_document", "list_sources"],
        vue_documentation,
    ),
    ("Données", ["ask_database", "get_schema"], vue_donnees),
    ("Commandes", ["order_status"], vue_commande),
]

with st.sidebar:
    st.markdown("### Sorabel Data Gateway")
    profil = st.selectbox(
        "Profil connecté", list(PROFILS), format_func=lambda p: PROFILS[p][0], key="profil"
    )
    if st.session_state.get("_profil_charge") != profil:
        with st.spinner("Ouverture de la session…"):
            st.session_state["_tools"] = lister_tools(profil)
        st.session_state["_profil_charge"] = profil
    tools = st.session_state.get("_tools", [])

    st.markdown("**Accès accordés**")
    st.markdown(
        " ".join(f"<span class='etiquette gris'>{t}</span>" for t in tools),
        unsafe_allow_html=True,
    )
    st.caption(
        "Ce que ce profil ne peut pas appeler n'apparaît pas : la matrice d'accès est "
        "appliquée par le serveur, cette page ne fait que la refléter."
    )

libelle_profil, titre_poste = PROFILS[profil]
st.markdown(
    f"<div class='bandeau'>{LOGO}<span class='titre'>{titre_poste}</span>"
    f"<span class='profil'>{libelle_profil}</span></div>"
    f"<div class='rappel'>"
    f"<div class='item'><span class='legende'>Corpus</span>"
    f"<span class='valeur'>400 documents indexés</span></div>"
    f"<div class='item'><span class='legende'>Données</span>"
    f"<span class='valeur'>produits · stocks · clients · commandes · ventes</span></div>"
    f"<div class='item'><span class='legende'>Fonctions accordées</span>"
    f"<span class='valeur'>{len(tools)} sur 8</span></div>"
    f"</div>",
    unsafe_allow_html=True,
)

vues_actives = [
    (nom, vue)
    for nom, tools_requis, vue in VUES
    if any(tool in tools for tool in tools_requis)
]
if not vues_actives:
    afficher_vide(
        "Aucune fonctionnalité accessible",
        "Ce profil n'a de droit sur aucun tool. Contactez l'exploitation.",
    )
else:
    for (nom, vue), onglet in zip(vues_actives, st.tabs([n for n, _ in vues_actives])):
        with onglet:
            vue(profil, tools)
