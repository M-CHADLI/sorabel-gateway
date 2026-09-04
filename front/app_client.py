"""Interface utilisateur final de la Sorabel Data Gateway.

Contrairement à `front/app.py` (outil de debug développeur, accès direct sans gouvernance),
cette page passe exclusivement par le serveur MCP (`front.mcp_client`) : elle respecte donc
strictement le profil sélectionné, n'affiche que les tools autorisés (E4), affiche les
citations construites par le code (E1), la transparence du SQL exécuté ou rejeté (E3), et
traduit chaque statut de refus en message clair plutôt qu'en erreur technique (E5).

Cette page ne fait aucune application de la matrice d'accès elle-même : elle se contente de
refléter ce que le serveur autorise. Toute la gouvernance réelle est appliquée côté serveur
(`gouvernance/`, `mcp_server/`) — cette interface est un client parmi d'autres possibles.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from front.mcp_client import appeler, lister_tools

st.set_page_config(page_title="Sorabel — Assistant données", page_icon="⚡", layout="centered")

PROFILS = {
    "support": "Support client",
    "commercial": "Commercial",
    "dev": "Développeur",
    "admin": "Exploitation",
}

STATUTS_REFUS = {
    "hors_corpus": ("info", "Cette question ne trouve pas de réponse dans la documentation Sorabel."),
    "hors_schema": ("warning", "Cette question ne correspond à aucune donnée ou document disponible."),
    "non_autorise": ("warning", "Votre profil n'a pas accès à cette information."),
    "refuse_ecriture": ("error", "Cette action a été refusée : seule la lecture des données est autorisée."),
}


def _afficher_statut_refus(statut: str, message_serveur: str | None) -> None:
    niveau, message_defaut = STATUTS_REFUS.get(statut, ("error", "Une erreur est survenue."))
    texte = message_serveur or message_defaut
    getattr(st, niveau)(texte)


def _afficher_citations(citations: list[dict]) -> None:
    if not citations:
        return
    st.caption("Sources")
    for c in citations:
        morceaux = [p for p in (c.get("reference"), c.get("date")) if p]
        sous_titre = " · ".join(morceaux)
        st.markdown(f"- **{c.get('titre', 'Document')}**" + (f" — {sous_titre}" if sous_titre else ""))


with st.sidebar:
    st.markdown("### Sorabel Data Gateway")
    profil = st.selectbox(
        "Connecté en tant que", list(PROFILS), format_func=lambda p: PROFILS[p], key="profil"
    )
    if st.session_state.get("_profil_charge") != profil:
        st.session_state["_tools"] = lister_tools(profil)
        st.session_state["_profil_charge"] = profil
    tools = st.session_state.get("_tools", [])
    st.caption(f"{len(tools)} fonctionnalité(s) disponible(s) pour ce profil.")

st.title("⚡ Assistant Sorabel")
st.caption("Documentation technique et données produits, en langage naturel.")

onglets_config = [
    ("Poser une question", "answer_question", "💬"),
    ("Interroger les données", "ask_database", "📊"),
    ("Vérifier un stock", "check_stock", "📦"),
    ("Suivre une commande", "order_status", "🚚"),
]
onglets_actifs = [(nom, tool, icone) for nom, tool, icone in onglets_config if tool in tools]

if not onglets_actifs:
    st.warning("Aucune fonctionnalité disponible pour ce profil.")
else:
    onglets = st.tabs([f"{icone} {nom}" for nom, _, icone in onglets_actifs])

    for (nom, tool, _icone), onglet in zip(onglets_actifs, onglets):
        with onglet:
            if tool == "answer_question":
                question = st.text_input(
                    "Votre question", placeholder="Ex. : quel disjoncteur pour du triphasé ?"
                )
                if st.button("Rechercher", key="btn_answer_question") and question:
                    with st.spinner("Recherche dans la documentation…"):
                        resultat = appeler(profil, "answer_question", {"question": question})
                    if resultat.get("statut") == "ok":
                        st.write(resultat["reponse"])
                        _afficher_citations(resultat.get("citations", []))
                    else:
                        _afficher_statut_refus(resultat.get("statut", ""), resultat.get("message"))

            elif tool == "ask_database":
                question_sql = st.text_input(
                    "Votre question", placeholder="Ex. : combien de commandes en avril ?"
                )
                if st.button("Interroger", key="btn_ask_database") and question_sql:
                    with st.spinner("Interrogation des données…"):
                        resultat = appeler(profil, "ask_database", {"question": question_sql})
                    if resultat.get("statut") == "ok":
                        colonnes = resultat.get("colonnes", [])
                        lignes = resultat.get("lignes", [])
                        st.dataframe(
                            [dict(zip(colonnes, ligne)) for ligne in lignes],
                            use_container_width=True,
                        )
                        if resultat.get("tronque"):
                            st.caption(f"Résultat tronqué à {len(lignes)} lignes.")
                    else:
                        _afficher_statut_refus(resultat.get("statut", ""), resultat.get("message"))
                    if resultat.get("sql"):
                        with st.expander("Requête SQL exécutée"):
                            st.code(resultat["sql"], language="sql")

            elif tool == "check_stock":
                ref = st.text_input("Référence produit", placeholder="Ex. : REF-1024")
                if st.button("Vérifier", key="btn_check_stock") and ref:
                    resultat = appeler(profil, "check_stock", {"ref": ref})
                    if resultat.get("statut") == "ok":
                        colonnes = resultat.get("colonnes", [])
                        lignes = resultat.get("lignes", [])
                        st.dataframe(
                            [dict(zip(colonnes, ligne)) for ligne in lignes],
                            use_container_width=True,
                        )
                        if resultat.get("sous_seuil_reappro"):
                            st.warning("Au moins un entrepôt est sous le seuil de réapprovisionnement.")
                    else:
                        _afficher_statut_refus(resultat.get("statut", ""), resultat.get("message"))

            elif tool == "order_status":
                order_id = st.text_input("Identifiant commande", placeholder="Ex. : CMD-2025-0004")
                if st.button("Suivre", key="btn_order_status") and order_id:
                    resultat = appeler(profil, "order_status", {"order_id": order_id})
                    if resultat.get("statut") == "ok":
                        colonnes = resultat.get("colonnes", [])
                        lignes = resultat.get("lignes", [])
                        st.dataframe(
                            [dict(zip(colonnes, ligne)) for ligne in lignes],
                            use_container_width=True,
                        )
                    else:
                        _afficher_statut_refus(resultat.get("statut", ""), resultat.get("message"))
