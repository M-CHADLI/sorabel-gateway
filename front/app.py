"""Front Streamlit : teste chaque brique de la Sorabel Data Gateway séparément.

Section "Pipeline RAG (debug)" appelle sorabel_rag directement, SANS passer par la
gouvernance — vue développeur pour inspecter extraction/chunking/recherche brute, y compris
les documents confidentiels quel que soit le profil choisi dans la barre latérale.

Section "Tools MCP (gouvernés)" appelle le vrai serveur MCP via front.mcp_client, donc
respecte strictement le profil sélectionné — c'est la vue qui démontre la matrice d'accès (E5).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import glob
import json

import streamlit as st

from front.mcp_client import appeler, lister_tools
from sorabel_rag.chunking import chunker
from sorabel_rag.extraction import EXTRACTEURS
from sorabel_rag.ingestion import CORPUS, SORTIE
from sorabel_rag.recherche import rechercher

st.set_page_config(page_title="Sorabel Data Gateway — test des briques", layout="wide")
st.title("Sorabel Data Gateway — test des briques")

PROFILS = ["support", "commercial", "dev", "admin"]
profil = st.sidebar.selectbox("Profil (section « Tools MCP » uniquement)", PROFILS, index=0)
st.sidebar.caption(
    "La section « Pipeline RAG (debug) » ignore ce profil : accès direct, hors gouvernance. "
    "Seule la section « Tools MCP » l'applique strictement."
)

onglet_debug, onglet_mcp = st.tabs(["Pipeline RAG (debug)", "Tools MCP (gouvernés)"])

with onglet_debug:
    st.subheader("Extraction")
    fichiers = sorted(glob.glob(str(CORPUS / "*" / "*")))
    chemin_choisi = st.selectbox(
        "Fichier source",
        fichiers,
        format_func=lambda p: str(Path(p).relative_to(CORPUS)),
        key="chemin_choisi",
    )
    if chemin_choisi and st.button("Extraire"):
        dossier = Path(chemin_choisi).parent.name
        extracteur, _ = EXTRACTEURS[dossier]
        document = extracteur(Path(chemin_choisi))
        st.session_state["document_extrait"] = document
        st.json(document.en_dict())

    st.subheader("Chunking")
    if "document_extrait" not in st.session_state:
        st.info("Extraire un document ci-dessus d'abord.")
    elif st.button("Chunker le document extrait"):
        document = st.session_state["document_extrait"]
        manifeste = json.loads((SORTIE / "_manifeste.json").read_text(encoding="utf-8"))
        for c in chunker(document, manifeste):
            st.markdown(f"**{c.chunk_id}** ({c.n_tokens} tokens)")
            st.code(c.texte)

    st.subheader("Recherche — comparaison des trois configurations (E6)")
    requete = st.text_input("Requête", value="REF-1024", key="requete_debug")
    k = st.slider("k", 1, 10, 5, key="k_debug")
    if st.button("Comparer dense / hybride / hybride_rerank"):
        colonnes = st.columns(3)
        for config, colonne in zip(["dense", "hybride", "hybride_rerank"], colonnes):
            with colonne:
                st.markdown(f"**{config}**")
                for r in rechercher(requete, k=k, config=config):
                    st.write(f"{r.titre} ({r.reference}) — {r.score:.4f}")

with onglet_mcp:
    st.subheader(f"Tools disponibles pour le profil « {profil} »")
    if st.button("Rafraîchir tools/list"):
        st.session_state["tools_disponibles"] = lister_tools(profil)
    st.write(st.session_state.get("tools_disponibles") or "— clique sur « Rafraîchir tools/list »")

    st.divider()

    st.subheader("answer_question")
    question_rag = st.text_input("Question (RAG)", key="question_rag")
    if st.button("Appeler answer_question"):
        st.json(appeler(profil, "answer_question", {"question": question_rag}))

    st.subheader("search_docs")
    requete_mcp = st.text_input("Requête (search_docs)", key="requete_mcp")
    if st.button("Appeler search_docs"):
        st.json(appeler(profil, "search_docs", {"requete": requete_mcp}))

    st.subheader("get_schema")
    if st.button("Appeler get_schema"):
        resultat = appeler(profil, "get_schema", {})
        st.code(resultat.get("schema", json.dumps(resultat, ensure_ascii=False)))

    st.subheader("ask_database")
    question_sql = st.text_input("Question (SQL)", key="question_sql")
    if st.button("Appeler ask_database"):
        st.json(appeler(profil, "ask_database", {"question": question_sql}))

    st.subheader("check_stock")
    ref_stock = st.text_input("Référence (REF-XXXX)", key="ref_stock")
    if st.button("Appeler check_stock"):
        st.json(appeler(profil, "check_stock", {"ref": ref_stock}))

    st.subheader("order_status")
    id_commande = st.text_input("Identifiant commande (CMD-AAAA-NNNN)", key="id_commande")
    if st.button("Appeler order_status"):
        st.json(appeler(profil, "order_status", {"order_id": id_commande}))

    st.subheader("get_document")
    st.caption("Renseigner soit doc_id, soit reference (+ version optionnelle).")
    doc_id = st.text_input("doc_id", key="doc_id")
    reference_doc = st.text_input("reference (ex. REF-1024)", key="reference_doc")
    version_doc = st.text_input("version (optionnel)", key="version_doc")
    if st.button("Appeler get_document"):
        st.json(appeler(profil, "get_document", {
            "doc_id": doc_id or None,
            "reference": reference_doc or None,
            "version": version_doc or None,
        }))

    st.subheader("list_sources")
    type_doc_filtre = st.selectbox(
        "type_document",
        [None, "fiche_technique", "notice", "procedure_sav", "note_interne"],
        key="type_doc_filtre",
    )
    if st.button("Appeler list_sources"):
        st.json(appeler(profil, "list_sources", {"type_document": type_doc_filtre}))
