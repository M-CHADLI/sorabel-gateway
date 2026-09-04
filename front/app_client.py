"""Poste commercial Sorabel — interface métier de la Data Gateway.

Organisée autour du travail réel d'un commercial (préparer une visite, répondre à un client
sur une référence, suivre une commande) et non autour du catalogue de tools : une fiche
produit rassemble ici documentation, stock et conditions tarifaires, là où le serveur expose
trois tools distincts.

Direction visuelle : registre SaaS contemporain — profondeur par ombres douces plutôt que
par traits, coins largement arrondis, fond légèrement teinté sur lequel les surfaces
blanches se détachent. Plus Jakarta Sans porte l'interface, JetBrains Mono les données à
lire au caractère près (références, identifiants, SQL). Le verre dépoli est réservé au
bandeau : l'appliquer derrière un tableau de chiffres coûterait en lisibilité ce qu'il
rapporte en style.

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
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

  :root {
    --encre:        #101828;
    --encre-douce:  #5B6478;
    --bord:         #E6EAF2;
    --bord-net:     #D4DBE8;
    --fond-doux:    #F4F7FC;
    --accent:       #2563EB;
    --accent-fonce: #1D4ED8;
    --accent-voile: #EFF4FF;
    --succes:       #0F7A4A;
    --succes-fond:  #E3F7EC;
    --alerte:       #C0322B;
    --alerte-fond:  #FDECEB;
    --transition:   180ms cubic-bezier(.4, 0, .2, 1);
    /* Élévation par ombres douces plutôt que par traits : deux ombres superposées — une
       courte et dense pour le contact, une longue et diffuse pour la hauteur — donnent la
       profondeur qu'un bord 1px ne rend pas. */
    --ombre-1:  0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.05);
    --ombre-2:  0 2px 4px rgba(16,24,40,.05), 0 6px 16px -4px rgba(16,24,40,.09);
    --rayon:    14px;
  }

  html, body, [class*="css"], .stMarkdown, button, input, select, textarea {
    font-family: 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
  }
  /* Fond légèrement teinté : les surfaces blanches s'y détachent, ce qu'un blanc sur blanc
     ne permet pas — c'est ce qui fait exister les cartes sans les cercler de traits. */
  [data-testid="stAppViewContainer"] {
    background:
      radial-gradient(1100px 460px at 12% -8%, #EAF1FE 0%, rgba(234,241,254,0) 62%),
      radial-gradient(900px 420px at 96% 0%, #F1EDFD 0%, rgba(241,237,253,0) 58%),
      #F7F9FD;
  }
  .block-container { padding-top: 2.6rem; max-width: 1180px; }

  /* Contraste : 4.5:1 minimum sur tout le texte courant. */
  .stMarkdown, .stMarkdown p, label, .stCaption { color: var(--encre); }
  .stCaption, [data-testid="stCaptionContainer"] { color: var(--encre-douce) !important; }
  h1, h2, h3, h4, h5 { letter-spacing: -.021em; font-weight: 700; color: var(--encre); }

  /* Verre dépoli sur le bandeau seulement : flouter un fond derrière un tableau de chiffres
     coûterait en lisibilité ce qu'il rapporte en style. Ici il n'y a que du titre. */
  .bandeau {
    display: flex; align-items: center; gap: .7rem;
    background: rgba(255,255,255,.72);
    -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px);
    border: 1px solid rgba(255,255,255,.7); box-shadow: var(--ombre-1);
    border-radius: var(--rayon); padding: .85rem 1.15rem; margin-bottom: .8rem;
    color: var(--encre);
  }
  .bandeau .marque {
    display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px;
    background: linear-gradient(140deg, var(--accent) 0%, #4F46E5 100%);
    color: #fff; box-shadow: 0 3px 8px -2px rgba(37,99,235,.5);
  }
  /* `line-height` explicite : à 1.42rem, les jambages de « p » et « j » et les accents
     capitaux débordent de la boîte par défaut et se font rogner par le flex. */
  .bandeau .titre {
    font-size: 1.42rem; font-weight: 800; letter-spacing: -.03em;
    line-height: 1.45; padding: .1rem 0;
  }
  .bandeau .profil {
    margin-left: auto; font-size: .76rem; font-weight: 600; color: var(--accent-fonce);
    background: var(--accent-voile); border: 1px solid #DBE6FF;
    border-radius: 999px; padding: .3rem .75rem;
  }

  /* La zone de saisie est le point d'entrée de chaque écran : elle doit se lire comme un
     bloc, pas comme un champ perdu au milieu du blanc. */
  .panneau {
    border: 1px solid var(--bord); border-radius: var(--rayon); background: #fff;
    box-shadow: var(--ombre-1);
    padding: 1.15rem 1.3rem .5rem; margin-bottom: 1.15rem;
  }
  .panneau .intitule {
    font-size: 1.06rem; font-weight: 700; color: var(--encre); letter-spacing: -.015em;
  }
  .panneau .aide { font-size: .855rem; color: var(--encre-douce); margin-top: .25rem; line-height: 1.5; }

  .rappel {
    display: flex; gap: 2rem; flex-wrap: wrap;
    border: 1px solid var(--bord); border-radius: var(--rayon); background: #fff;
    box-shadow: var(--ombre-1); padding: .85rem 1.15rem; margin-bottom: 1.3rem;
  }
  .rappel .item { display: flex; flex-direction: column; gap: .15rem; }
  .rappel .valeur { font-weight: 600; color: var(--encre); font-size: .92rem; }

  .carte {
    border: 1px solid var(--bord); border-radius: var(--rayon); padding: 1rem 1.15rem;
    background: #fff; margin-bottom: .8rem; box-shadow: var(--ombre-1);
    transition: box-shadow var(--transition), transform var(--transition), border-color var(--transition);
  }
  .carte:hover {
    box-shadow: var(--ombre-2); border-color: var(--bord-net); transform: translateY(-1px);
  }
  .carte .entete { font-weight: 700; color: var(--encre); margin-bottom: .3rem; letter-spacing: -.01em; }
  .carte .meta   { font-size: .8rem; color: var(--encre-douce); font-family: 'JetBrains Mono', monospace; }

  .source {
    border: 1px solid var(--bord); border-left: 3px solid var(--accent);
    background: linear-gradient(90deg, var(--accent-voile) 0%, #fff 55%);
    padding: .6rem .9rem; border-radius: 0 10px 10px 0; margin-bottom: .5rem;
  }
  .source .titre { font-weight: 600; font-size: .9rem; color: var(--encre); }
  .source .meta  { font-size: .77rem; color: var(--encre-douce); font-family: 'JetBrains Mono', monospace; }

  .etiquette {
    display: inline-block; padding: .2rem .6rem; border-radius: 999px;
    font-size: .73rem; font-weight: 600; font-family: 'JetBrains Mono', monospace;
    border: 1px solid transparent; margin: 0 .12rem .28rem 0;
  }
  .vert  { background: var(--succes-fond); color: var(--succes); border-color: #C6EEDA; }
  .rouge { background: var(--alerte-fond); color: var(--alerte); border-color: #F9D2CF; }
  .gris  { background: var(--fond-doux); color: #3B455C; border-color: var(--bord); }

  .chiffre {
    font-size: 1.75rem; font-weight: 700; color: var(--encre);
    line-height: 1.2; letter-spacing: -.03em; font-variant-numeric: tabular-nums;
  }
  .legende {
    font-size: .71rem; color: var(--encre-douce); text-transform: uppercase;
    letter-spacing: .07em; font-weight: 600; margin-bottom: .2rem;
  }

  /* Les réponses rédigées sont de la prose : au-delà de ~75 caractères par ligne, l'œil
     perd le début de la ligne suivante. */
  .prose { max-width: 68ch; line-height: 1.65; color: var(--encre); }

  .etapes {
    font-size: .8rem; color: var(--encre-douce); margin-bottom: .7rem;
    background: #fff; border: 1px solid var(--bord); border-radius: 999px;
    padding: .35rem .9rem; display: inline-block; box-shadow: var(--ombre-1);
  }
  .etapes .fait   { color: var(--succes); }
  .etapes .encours{ color: var(--accent); font-weight: 700; }

  .vide {
    border: 1px dashed var(--bord-net); border-radius: var(--rayon); padding: 1.7rem;
    text-align: center; color: var(--encre-douce); background: rgba(255,255,255,.6);
  }

  /* Le focus clavier doit rester visible : c'est le seul repère de position pour qui
     n'utilise pas la souris. */
  button:focus-visible, input:focus-visible, select:focus-visible, [role="tab"]:focus-visible {
    outline: 2px solid var(--accent) !important; outline-offset: 2px !important;
  }
  .stButton > button {
    cursor: pointer; border-radius: 10px; font-weight: 600; letter-spacing: -.01em;
    transition: background var(--transition), border-color var(--transition),
                box-shadow var(--transition), transform var(--transition);
  }
  .stButton > button[kind="primary"] {
    background: linear-gradient(180deg, #2F6BEE 0%, var(--accent-fonce) 100%);
    border: 1px solid var(--accent-fonce); box-shadow: 0 2px 6px -1px rgba(37,99,235,.45);
  }
  .stButton > button[kind="primary"]:hover { transform: translateY(-1px); box-shadow: 0 5px 12px -2px rgba(37,99,235,.5); }
  .stButton > button[kind="primary"]:active { transform: translateY(0); }

  /* Champs : le halo au focus vaut confirmation que la frappe ira bien là. */
  .stTextInput input, .stSelectbox [data-baseweb="select"] > div, .stNumberInput input {
    border-radius: 10px !important; border-color: var(--bord-net) !important;
    background: #fff !important;
  }
  .stTextInput input:focus {
    border-color: var(--accent) !important; box-shadow: 0 0 0 3px rgba(37,99,235,.16) !important;
  }
  [data-testid="stExpander"] details {
    border: 1px solid var(--bord) !important; border-radius: var(--rayon) !important;
    background: #fff; box-shadow: var(--ombre-1);
  }
  [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; box-shadow: var(--ombre-1); }

  /* Barre latérale sombre : elle cesse d'être une colonne de page pour devenir un châssis
     d'application. L'inversion suffit à séparer « où je suis » de « ce que je consulte »,
     sans le trait de séparation qu'il fallait sinon. */
  [data-testid="stSidebar"] {
    background: linear-gradient(185deg, #0D1526 0%, #16223C 55%, #1A2745 100%);
    border-right: none;
  }
  [data-testid="stSidebar"] * { color: #E9EEF9; }
  [data-testid="stSidebar"] h3 { color: #fff; font-size: 1.02rem; letter-spacing: -.01em; }
  /* #A9B6D3 sur #16223C : 6.4:1, au-delà des 4.5:1 exigés pour du texte secondaire. */
  [data-testid="stSidebar"] .stCaption,
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #A9B6D3 !important; }
  [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.13); }
  /* Le profil connecté conditionne tout l'écran : il doit se lire en pleine encre, et non
     dans le gris de placeholder que baseweb applique par défaut sur fond sombre. */
  [data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: rgba(255,255,255,.07) !important;
    border-color: rgba(255,255,255,.16) !important;
  }
  [data-testid="stSidebar"] [data-baseweb="select"] div { color: #FFFFFF !important; }
  [data-testid="stSidebar"] [data-baseweb="select"] svg { fill: #A9B6D3 !important; }
  [data-testid="stSidebar"] [data-testid="stExpander"] details {
    background: rgba(255,255,255,.05); border-color: rgba(255,255,255,.13) !important;
    box-shadow: none;
  }
  [data-testid="stSidebar"] .etiquette.gris {
    background: rgba(255,255,255,.09); color: #D8E1F5; border-color: rgba(255,255,255,.14);
  }

  /* Navigation verticale : des entrées de menu, pas des boutons d'action. Chaque thème
     porte sa couleur — en pastille quand il dort, en liseré quand il est ouvert. La
     sélection ne repose donc jamais sur la seule couleur. */
  [data-testid="stSidebar"] .stButton > button {
    display: flex; align-items: center; justify-content: flex-start; text-align: left;
    border: 1px solid transparent; background: transparent; color: #C9D4EA;
    font-weight: 600; padding: .45rem .7rem; min-height: 2.5rem;
    border-radius: 10px; box-shadow: none;
  }
  [data-testid="stSidebar"] .stButton > button::before {
    content: ""; width: 8px; height: 8px; border-radius: 50%; flex: none;
    margin-right: .6rem; background: rgba(255,255,255,.3);
    transition: transform var(--transition);
  }
  /* Le libellé est centré par défaut dans un bouton Streamlit : dans un menu, l'œil
     descend une colonne de débuts de mots, pas une colonne de milieux. */
  [data-testid="stSidebar"] .stButton > button > div,
  [data-testid="stSidebar"] .stButton > button p {
    text-align: left !important; width: 100%;
  }
  [data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,.07); color: #fff; transform: none;
  }
  [data-testid="stSidebar"] .stButton > button[kind="primary"] {
    color: #fff; font-weight: 700; border-color: transparent;
  }
  [data-testid="stSidebar"] .stButton > button[kind="primary"]::before { transform: scale(1.25); }

  /* Les sous-entrées vivent dans une colonne indentée : plus discrètes que leur thème, et
     marquées d'un trait plutôt que d'une pastille pour qu'on ne les confonde pas. */
  [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] .stButton > button {
    font-size: .86rem; font-weight: 500; min-height: 2.15rem; padding: .32rem .6rem;
    color: #A9B6D3;
  }
  [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] .stButton > button::before {
    width: 3px; height: 14px; border-radius: 2px; background: rgba(255,255,255,.18);
    margin-right: .55rem;
  }
  [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] .stButton > button[kind="primary"] {
    background: rgba(255,255,255,.08); color: #fff; font-weight: 600;
  }
  [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] .stButton > button[kind="primary"]::before {
    transform: none;
  }

  .groupe-acces {
    font-size: .8rem; line-height: 1.5;
    display: flex; align-items: center; gap: .55rem;
    padding: .32rem 0; border-bottom: 1px solid rgba(255,255,255,.09);
  }
  .groupe-acces .pastille { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .groupe-acces .nom { color: #C9D4EA; }
  .groupe-acces .compte {
    margin-left: auto; font-family: 'JetBrains Mono', monospace;
    color: #fff; font-weight: 600;
  }
  code, pre, .stCode { font-family: 'JetBrains Mono', monospace !important; }
  [data-testid="stCode"] { border-radius: 10px; overflow: hidden; }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition-duration: .01ms !important; animation-duration: .01ms !important; }
    .carte:hover, .stButton > button:hover { transform: none !important; }
  }
</style>
"""
# Une couleur par thème de la navigation, tenue d'un bout à l'autre : pastille du menu,
# liseré de l'entrée ouverte, point du panneau d'accès. Elles vivent ici, avant la feuille
# de style, parce que les règles qui les portent en sont dérivées — la table `NAVIGATION`
# plus bas les reprend, sans jamais redéfinir une teinte de son côté.
COULEURS_THEME = {
    "produit": "#F59E0B",
    "documentation": "#3B82F6",
    "donnees": "#8B5CF6",
    "commandes": "#10B981",
}


def _regles_couleurs() -> str:
    """Les règles de couleur, dérivées de `COULEURS_THEME` plutôt que recopiées à la main.

    Streamlit appose sur chaque widget une classe `st-key-<clé>` : c'est ce qui permet de
    colorer une entrée de menu précise sans y toucher depuis Python. Le préfixe
    `[data-testid="stSidebar"]` n'est pas décoratif — sans lui, ces règles perdent en
    spécificité contre les règles génériques du menu, qui reprennent la main et rendent
    toutes les pastilles grises.

    Si la classe `st-key-` disparaissait d'une version de Streamlit, le menu resterait
    fonctionnel, en gris — pas cassé.
    """
    regles = []
    for slug, couleur in COULEURS_THEME.items():
        regles.append(
            f'[data-testid="stSidebar"] .st-key-nav_{slug} button::before '
            f"{{ background: {couleur}; }}\n"
            f'[data-testid="stSidebar"] .st-key-nav_{slug} button[kind="primary"] {{\n'
            f"  background: linear-gradient(90deg, {couleur}2E 0%, rgba(255,255,255,.03) 100%);\n"
            f"  box-shadow: inset 3px 0 0 {couleur};\n"
            f"}}\n"
            # Les clés d'écran sont suffixées par leur rang : sélecteur sur le préfixe.
            f'[data-testid="stSidebar"] [class*="st-key-ecran_{slug}_"] '
            f'button[kind="primary"]::before {{ background: {couleur}; }}'
        )
    return "<style>\n" + "\n".join(regles) + "\n</style>"


st.markdown(STYLE + _regles_couleurs(), unsafe_allow_html=True)


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
    st.markdown(
        "<div class='panneau'><div class='intitule'>Interroger les données</div>"
        "<div class='aide'>Produits, stocks, clients, commandes et ventes, en langage "
        "naturel. Consultation seule : la requête produite reste toujours consultable."
        "</div></div>",
        unsafe_allow_html=True,
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


def vue_schema(profil: str, tools: list[str]) -> None:
    """`get_schema` : le schéma déjà filtré par la matrice, donc lisible comme un périmètre.

    Ce que ce profil n'a pas le droit de lire n'y figure pas — c'est la démonstration la plus
    directe d'E5 côté utilisateur : il constate son périmètre au lieu de le deviner aux refus.
    """
    st.markdown(
        "<div class='panneau'><div class='intitule'>Données consultables</div>"
        "<div class='aide'>Tables et colonnes que votre profil peut interroger. Les colonnes "
        "hors périmètre sont absentes du schéma, pas seulement refusées à l'exécution."
        "</div></div>",
        unsafe_allow_html=True,
    )
    schema = appeler(profil, "get_schema", {})
    if schema.get("statut") == "ok":
        st.code(schema["schema"], language="sql")
    else:
        afficher_refus(schema, "reprise_schema")


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

# Navigation à deux niveaux : quatre thèmes métier, chacun ouvrant ses écrans. Le catalogue
# de tools n'est pas une organisation utilisable — « search_docs » ne dit rien à un
# commercial, « Rechercher sans générer » si. Les huit tools restent tous atteignables, mais
# rangés derrière le geste qui les motive, et non listés à plat.
#
# Un écran apparaît dès qu'un seul de ses tools est accordé, et un thème dès qu'un seul de
# ses écrans apparaît : la barre reflète le profil sans jamais offrir une entrée morte.
# Le `slug` sert de clé de widget et de sélecteur CSS : un identifiant sans accent ni
# espace, qui relie l'entrée à sa couleur dans `COULEURS_THEME` sans dépendre du libellé.
# Le repère devient spatial autant que textuel — on retrouve « Données » à sa teinte avant
# d'avoir lu le mot.
NAVIGATION = [
    (
        "Produit",
        "produit",
        [("Fiche produit", ["check_stock", "ask_database"], vue_produit)],
    ),
    (
        "Documentation",
        "documentation",
        [
            ("Poser une question", ["answer_question"], vue_question),
            ("Rechercher un extrait", ["search_docs"], vue_recherche),
            ("Ouvrir un document", ["get_document"], vue_document),
            ("Inventaire du corpus", ["list_sources"], vue_inventaire),
        ],
    ),
    (
        "Données",
        "donnees",
        [
            ("Interroger la base", ["ask_database"], vue_donnees),
            ("Périmètre accessible", ["get_schema"], vue_schema),
        ],
    ),
    ("Commandes", "commandes", [("Suivi de commande", ["order_status"], vue_commande)]),
]


def navigation_disponible(tools: list[str]) -> list[tuple[str, str, list[tuple]]]:
    themes = []
    for theme, slug, ecrans in NAVIGATION:
        accessibles = [
            (nom, vue) for nom, requis, vue in ecrans if any(t in tools for t in requis)
        ]
        if accessibles:
            themes.append((theme, slug, accessibles))
    return themes


def _selection(cle: str, valeurs: list[str]) -> str:
    """Maintient la sélection valide : un changement de profil peut la faire disparaître."""
    if st.session_state.get(cle) not in valeurs:
        st.session_state[cle] = valeurs[0]
    return st.session_state[cle]


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

    themes = navigation_disponible(tools)
    vue_courante = None
    if themes:
        st.divider()
        theme_actif = _selection("_theme", [nom for nom, _, _ in themes])
        for nom_theme, slug, ecrans in themes:
            if st.button(
                nom_theme,
                key=f"nav_{slug}",
                use_container_width=True,
                type="primary" if nom_theme == theme_actif else "secondary",
            ):
                # Les sous-entrées d'un thème situé plus haut sont déjà rendues à ce
                # stade : sans relance, la barre afficherait deux thèmes ouverts.
                st.session_state["_theme"] = nom_theme
                st.session_state["_ecran"] = ecrans[0][0]
                st.rerun()

            # Un thème à écran unique n'a rien à déplier : afficher une sous-entrée qui
            # répète son thème n'ajoute qu'un clic.
            if nom_theme == theme_actif and len(ecrans) > 1:
                _, colonne = st.columns([1, 11])
                with colonne:
                    ecran_actif = _selection("_ecran", [nom for nom, _ in ecrans])
                    for rang, (nom_ecran, vue) in enumerate(ecrans):
                        if st.button(
                            nom_ecran,
                            key=f"ecran_{slug}_{rang}",
                            use_container_width=True,
                            type="primary" if nom_ecran == ecran_actif else "secondary",
                        ):
                            st.session_state["_ecran"] = nom_ecran
                            ecran_actif = nom_ecran
                    vue_courante = dict(ecrans)[ecran_actif]
            elif nom_theme == theme_actif:
                vue_courante = ecrans[0][1]

    st.divider()
    # On compte des écrans, pas des tools : `ask_database` sert deux écrans (les conditions
    # d'une fiche produit et l'interrogation libre), et le compter dans les deux thèmes
    # faisait un total de 9 pour 8 tools accordés. Les deux unités sont justes mais ne
    # s'additionnent pas — les mélanger dans un même panneau donnait un décompte faux.
    st.markdown("**Écrans accessibles**")
    for theme, slug, ecrans in NAVIGATION:
        ouverts = sum(1 for _, requis, _ in ecrans if any(t in tools for t in requis))
        st.markdown(
            f"<div class='groupe-acces'>"
            f"<span class='pastille' style='background:{COULEURS_THEME[slug]}'></span>"
            f"<span class='nom'>{theme}</span>"
            f"<span class='compte'>{ouverts}/{len(ecrans)}</span></div>",
            unsafe_allow_html=True,
        )
    with st.expander(f"Tools accordés par le serveur ({len(tools)}/8)"):
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
    f"<div class='bandeau'><span class='marque'>{LOGO}</span>"
    f"<span class='titre'>{titre_poste}</span>"
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

if vue_courante is None:
    afficher_vide(
        "Aucune fonctionnalité accessible",
        "Ce profil n'a de droit sur aucun tool. Contactez l'exploitation.",
    )
else:
    vue_courante(profil, tools)
