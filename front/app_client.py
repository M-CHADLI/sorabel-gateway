"""Poste commercial Sorabel — interface métier de la Data Gateway.

Organisée autour du travail réel d'un commercial (préparer une visite, répondre à un client
sur une référence, suivre une commande) et non autour du catalogue de tools : une fiche
produit rassemble ici documentation, stock et conditions tarifaires, là où le serveur expose
trois tools distincts.

Tout passe par le serveur MCP (`front.mcp_client`) : la page n'applique aucune règle d'accès
elle-même, elle reflète ce que la matrice autorise pour le profil connecté. Les garanties du
brief s'y retrouvent telles quelles — sources citées (E1), SQL exécuté ou rejeté toujours
visible (E3), tools masqués hors périmètre (E4), refus traduits en message clair et jamais
confondus avec une panne (E5).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import re

import streamlit as st

from front.mcp_client import appeler, lister_tools

st.set_page_config(
    page_title="Sorabel — Poste commercial", page_icon="⚡", layout="wide"
)

PROFILS = {
    "commercial": "Commercial",
    "support": "Support client",
    "admin": "Exploitation",
    "dev": "Développeur",
}

MOTIF_REFERENCE = re.compile(r"REF-\d{4}", re.IGNORECASE)

# Un refus n'est pas une panne : chaque statut a son registre visuel et son message, pour
# que l'utilisateur sache s'il doit reformuler, demander un droit, ou signaler un incident.
REFUS = {
    "hors_corpus": ("info", "Aucun document du corpus ne traite ce sujet."),
    "hors_schema": ("warning", "Cette question ne correspond à aucune donnée disponible."),
    "non_autorise": ("warning", "Votre profil n'a pas accès à cette information."),
    "refuse_ecriture": ("error", "Refusé : seule la consultation des données est autorisée."),
    "erreur": ("error", "Incident technique — l'information n'a pas pu être récupérée."),
}

STYLE = """
<style>
  .block-container { padding-top: 2.2rem; max-width: 1180px; }
  h1, h2, h3 { letter-spacing: -0.02em; }

  .bandeau {
    display: flex; align-items: baseline; gap: .75rem;
    border-bottom: 1px solid #E5E7EB; padding-bottom: .9rem; margin-bottom: 1.6rem;
  }
  .bandeau .titre { font-size: 1.45rem; font-weight: 650; color: #111827; }
  .bandeau .sous  { font-size: .9rem; color: #6B7280; }

  .carte {
    border: 1px solid #E5E7EB; border-radius: 10px; padding: 1rem 1.15rem;
    background: #fff; margin-bottom: .85rem;
  }
  .carte .entete { font-weight: 600; color: #111827; margin-bottom: .35rem; }
  .carte .meta   { font-size: .82rem; color: #6B7280; }

  .source {
    border-left: 3px solid #2563EB; background: #F8FAFC;
    padding: .6rem .85rem; border-radius: 0 6px 6px 0; margin-bottom: .5rem;
  }
  .source .titre { font-weight: 600; font-size: .92rem; color: #1F2937; }
  .source .meta  { font-size: .8rem; color: #6B7280; }

  .etiquette {
    display: inline-block; padding: .15rem .55rem; border-radius: 999px;
    font-size: .75rem; font-weight: 600; letter-spacing: .01em;
  }
  .vert  { background: #DCFCE7; color: #166534; }
  .rouge { background: #FEE2E2; color: #991B1B; }
  .gris  { background: #F3F4F6; color: #374151; }

  .chiffre { font-size: 1.6rem; font-weight: 650; color: #111827; line-height: 1.1; }
  .legende { font-size: .78rem; color: #6B7280; text-transform: uppercase; letter-spacing: .04em; }
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)


# --- présentation ----------------------------------------------------------------------


def afficher_refus(resultat: dict) -> None:
    statut = resultat.get("statut", "erreur")
    niveau, defaut = REFUS.get(statut, REFUS["erreur"])
    getattr(st, niveau)(resultat.get("message") or defaut)


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


def afficher_sql(resultat: dict) -> None:
    """E3 : la requête est montrée qu'elle ait été exécutée ou rejetée."""
    if resultat.get("sql"):
        with st.expander("Requête SQL"):
            st.code(resultat["sql"], language="sql")


def afficher_tableau(resultat: dict) -> None:
    colonnes, lignes = resultat.get("colonnes", []), resultat.get("lignes", [])
    if not lignes:
        st.caption("Aucun résultat.")
        return
    st.dataframe(
        [dict(zip(colonnes, ligne)) for ligne in lignes], use_container_width=True
    )
    if resultat.get("tronque"):
        st.caption(f"Affichage limité aux {len(lignes)} premières lignes.")


# --- vues métier -----------------------------------------------------------------------


def vue_produit(profil: str, tools: list[str]) -> None:
    st.subheader("Fiche produit")
    st.caption(
        "Documentation, disponibilité et conditions d'une référence, rassemblées en une vue."
    )
    reference = st.text_input(
        "Référence", placeholder="REF-8842", key="ref_produit"
    ).strip().upper()

    if not st.button("Consulter", key="btn_produit", type="primary") or not reference:
        return
    if not MOTIF_REFERENCE.fullmatch(reference):
        st.warning("Format attendu : REF-XXXX (quatre chiffres).")
        return

    if "check_stock" in tools:
        st.markdown("#### Disponibilité")
        stock = appeler(profil, "check_stock", {"ref": reference})
        if stock.get("statut") == "ok":
            colonnes, lignes = stock.get("colonnes", []), stock.get("lignes", [])
            if not lignes:
                st.caption("Aucun stock enregistré pour cette référence.")
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
            afficher_refus(stock)

    if "ask_database" in tools:
        st.markdown("#### Conditions commerciales")
        conditions = appeler(
            profil,
            "ask_database",
            {"question": f"donne le nom, la catégorie et le prix de vente du produit {reference}"},
        )
        if conditions.get("statut") == "ok":
            afficher_tableau(conditions)
        else:
            afficher_refus(conditions)
        afficher_sql(conditions)

    if "answer_question" in tools:
        st.markdown("#### Ce que dit la documentation")
        with st.spinner("Analyse du corpus documentaire…"):
            doc = appeler(
                profil,
                "answer_question",
                {"question": f"quelles sont les caractéristiques techniques du {reference} ?"},
            )
        if doc.get("statut") == "ok":
            st.write(doc["reponse"])
            afficher_sources(doc.get("citations", []))
        else:
            afficher_refus(doc)


def vue_question(profil: str, tools: list[str]) -> None:
    st.subheader("Poser une question")
    st.caption(
        "Documentation technique et procédures SAV. Les réponses citent toujours leurs sources ; "
        "hors du corpus, l'assistant le dit plutôt que d'inventer."
    )
    question = st.text_input(
        "Question",
        placeholder="Quel disjoncteur pour un départ moteur en triphasé ?",
        key="question_doc",
    )
    if st.button("Rechercher", key="btn_question", type="primary") and question:
        with st.spinner("Analyse du corpus documentaire…"):
            resultat = appeler(profil, "answer_question", {"question": question})
        if resultat.get("statut") == "ok":
            st.write(resultat["reponse"])
            afficher_sources(resultat.get("citations", []))
        else:
            afficher_refus(resultat)


def vue_donnees(profil: str, tools: list[str]) -> None:
    st.subheader("Interroger les données")
    st.caption(
        "Produits, stocks, clients, commandes et ventes, en langage naturel. "
        "Consultation seule : la requête produite est toujours affichée."
    )
    question = st.text_input(
        "Question",
        placeholder="Combien de commandes en avril ?",
        key="question_sql",
    )
    if st.button("Interroger", key="btn_donnees", type="primary") and question:
        with st.spinner("Interrogation de la base…"):
            resultat = appeler(profil, "ask_database", {"question": question})
        if resultat.get("statut") == "ok":
            afficher_tableau(resultat)
        else:
            afficher_refus(resultat)
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
    identifiant = st.text_input(
        "Identifiant", placeholder="CMD-2025-0004", key="id_commande"
    ).strip().upper()
    if st.button("Rechercher", key="btn_commande", type="primary") and identifiant:
        resultat = appeler(profil, "order_status", {"order_id": identifiant})
        if resultat.get("statut") != "ok":
            afficher_refus(resultat)
            return
        colonnes, lignes = resultat.get("colonnes", []), resultat.get("lignes", [])
        if not lignes:
            st.caption("Aucune commande à cet identifiant.")
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


def vue_documentation(profil: str, tools: list[str]) -> None:
    st.subheader("Parcourir la documentation")
    st.caption("Inventaire des documents indexés, restreint au périmètre de votre profil.")
    type_document = st.selectbox(
        "Type",
        [None, "fiche_technique", "notice", "procedure_sav", "note_interne"],
        format_func=lambda t: "Tous les types" if t is None else t.replace("_", " "),
        key="type_doc",
    )
    if st.button("Afficher", key="btn_sources", type="primary"):
        resultat = appeler(profil, "list_sources", {"type_document": type_document})
        if resultat.get("statut") != "ok":
            afficher_refus(resultat)
            return
        sources = resultat.get("sources", [])
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

VUES = [
    ("Fiche produit", "check_stock", vue_produit),
    ("Question", "answer_question", vue_question),
    ("Données", "ask_database", vue_donnees),
    ("Commande", "order_status", vue_commande),
    ("Documentation", "list_sources", vue_documentation),
]

with st.sidebar:
    st.markdown("### Sorabel Data Gateway")
    profil = st.selectbox(
        "Profil connecté", list(PROFILS), format_func=lambda p: PROFILS[p], key="profil"
    )
    if st.session_state.get("_profil_charge") != profil:
        with st.spinner("Ouverture de la session…"):
            st.session_state["_tools"] = lister_tools(profil)
        st.session_state["_profil_charge"] = profil
    tools = st.session_state.get("_tools", [])

    st.markdown("**Accès accordés**")
    st.markdown(
        "".join(f"<span class='etiquette gris'>{t}</span> " for t in tools),
        unsafe_allow_html=True,
    )
    st.caption(
        "Ce que ce profil ne peut pas appeler n'apparaît pas : la matrice d'accès est "
        "appliquée par le serveur, cette page ne fait que la refléter."
    )

st.markdown(
    f"<div class='bandeau'><span class='titre'>Poste commercial</span>"
    f"<span class='sous'>{PROFILS[profil]}</span></div>",
    unsafe_allow_html=True,
)

vues_actives = [(nom, vue) for nom, tool, vue in VUES if tool in tools]
if not vues_actives:
    st.warning("Aucune fonctionnalité n'est accessible avec ce profil.")
else:
    for (nom, vue), onglet in zip(vues_actives, st.tabs([n for n, _ in vues_actives])):
        with onglet:
            vue(profil, tools)
