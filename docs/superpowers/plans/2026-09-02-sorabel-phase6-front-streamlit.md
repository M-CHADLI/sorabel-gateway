# Phase 6 — Front Streamlit de test (client MCP + inspection bas niveau)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Donner une interface Streamlit qui permet de tester chaque brique de la Gateway
séparément — c'est la demande initiale de ce chantier. Deux sections : un debug bas niveau du
pipeline RAG (extraction, chunking, comparaison des 3 configurations de recherche) et un vrai
client des 8 tools MCP, gouverné par le profil choisi dans la barre latérale.

**Architecture:** `front/mcp_client.py` ouvre une connexion stdio de courte durée par appel
(Streamlit ré-exécute tout le script à chaque interaction — pas de session MCP persistante
possible entre deux clics). `front/app.py` est purement présentation : il ne contient aucune
logique métier, uniquement de la composition de `front.mcp_client` (section gouvernée) et de
`sorabel_rag` (section debug).

**Tech Stack:** `streamlit` 1.59.1 (déjà installé), SDK `mcp` (Phase 5).

## Global Constraints

- Langue de l'interface et du code : français.
- **La section « Pipeline RAG (debug) » contourne délibérément la gouvernance** — elle appelle
  `sorabel_rag` directement, sans `Perimetre`, donc affiche tout le corpus quel que soit le
  profil choisi dans la barre latérale. C'est une décision assumée (vue développeur
  d'inspection), pas un oubli — l'interface l'affiche en toutes lettres (caption dans la barre
  latérale) pour qu'elle ne soit jamais confondue avec la section gouvernée.
- **La section « Tools MCP » est la seule à respecter le profil** — chaque appel relance un
  processus serveur MCP avec `SORABEL_PROFIL` fixé au profil choisi.
- Coût accepté : chaque clic dans la section MCP relance un sous-processus serveur (et donc
  recharge les modèles d'embedding pour `search_docs`/`answer_question`) — latence de
  quelques secondes par appel, acceptable pour un front de test, pas pour de la production.
- Exécuter les tests avec `python -m pytest` depuis la racine du dépôt.
- Aucun test automatisé pour `front/app.py` lui-même (script Streamlit, pas testable par
  pytest) — seule `front/mcp_client.py` a des tests automatisés ; `front/app.py` se vérifie
  manuellement (Task 3).

---

## File Structure

```
front/__init__.py       NOUVEAU : vide
front/mcp_client.py      NOUVEAU : appeler(profil, tool, arguments), lister_tools(profil)
front/app.py             NOUVEAU : interface Streamlit à deux sections
requirements.txt         MODIFIÉ : ajoute streamlit
tests/test_front_mcp_client.py  NOUVEAU
```

---

### Task 1: Pont Streamlit ↔ serveur MCP (`front/mcp_client.py`)

**Files:**
- Create: `front/__init__.py`
- Create: `front/mcp_client.py`
- Modify: `requirements.txt`
- Test: `tests/test_front_mcp_client.py`

**Interfaces:**
- Consumes: `mcp_server.serveur` (Phase 5, lancé comme sous-processus) ;
  `gouvernance.seed.peupler` (Phase 4, pour la fixture de test) ;
  `mcp_server.serveur.CHEMIN_GOUVERNANCE_DB` (Phase 5).
- Produces: `front.mcp_client.lister_tools(profil: str) -> list[str]` ;
  `front.mcp_client.appeler(profil: str, tool: str, arguments: dict) -> dict` — si `tool`
  n'est pas dans `tools/list` pour ce profil, retourne
  `{"statut": "non_autorise", "message": str}` sans tenter l'appel. Task 2 (`front/app.py`)
  est le seul appelant.

**Suppose que la Phase 5 est terminée** (serveur MCP fonctionnel) et que
`scripts/seed_gouvernance.py` peut peupler `gouvernance/gouvernance.db`.

- [ ] **Step 1: Ajouter la dépendance**

Dans `requirements.txt`, ajouter à la fin :

```
# Front de test
streamlit>=1.30
```

- [ ] **Step 2: Écrire les tests qui échouent**

Créer `front/__init__.py` (vide).

Créer `tests/test_front_mcp_client.py` :

```python
"""Pont Streamlit <-> serveur MCP : une connexion stdio de courte durée par appel."""

from gouvernance.seed import peupler
from mcp_server.serveur import CHEMIN_GOUVERNANCE_DB

from front.mcp_client import appeler, lister_tools


def test_lister_tools_dev_exclut_ask_database():
    peupler(CHEMIN_GOUVERNANCE_DB)  # même base que scripts/seed_gouvernance.py
    noms = lister_tools("dev")
    assert "ask_database" not in noms
    assert "search_docs" in noms


def test_lister_tools_support_a_les_huit_tools():
    peupler(CHEMIN_GOUVERNANCE_DB)
    noms = lister_tools("support")
    assert len(noms) == 8


def test_appeler_get_schema_fonctionne_sans_llm():
    peupler(CHEMIN_GOUVERNANCE_DB)
    resultat = appeler("commercial", "get_schema", {})
    assert resultat["statut"] == "ok"
    assert "marge_pct" in resultat["schema"]


def test_appeler_get_schema_support_exclut_marge_pct():
    peupler(CHEMIN_GOUVERNANCE_DB)
    resultat = appeler("support", "get_schema", {})
    assert "marge_pct" not in resultat["schema"]


def test_appeler_tool_non_autorise_est_signale_sans_exception():
    peupler(CHEMIN_GOUVERNANCE_DB)
    resultat = appeler("dev", "ask_database", {"question": "combien de produits ?"})
    assert resultat["statut"] == "non_autorise"
```

- [ ] **Step 3: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_front_mcp_client.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'front.mcp_client'`

- [ ] **Step 4: Écrire `front/mcp_client.py`**

```python
"""Pont entre Streamlit et le serveur MCP : une connexion stdio de courte durée par appel.

Streamlit ré-exécute le script à chaque interaction : pas de session MCP persistante possible
entre deux clics. Le coût (rechargement des modèles d'embedding à chaque appel RAG) est
accepté pour un front de test — cf. Global Constraints du plan.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RACINE = Path(__file__).resolve().parent.parent


def _parametres(profil: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.serveur"],
        env={"SORABEL_PROFIL": profil},
        cwd=str(RACINE),
    )


async def _lister_async(profil: str) -> list[str]:
    async with stdio_client(_parametres(profil)) as (lecture, ecriture):
        async with ClientSession(lecture, ecriture) as session:
            await session.initialize()
            outils = await session.list_tools()
            return sorted(t.name for t in outils.tools)


async def _appeler_async(profil: str, tool: str, arguments: dict) -> dict:
    async with stdio_client(_parametres(profil)) as (lecture, ecriture):
        async with ClientSession(lecture, ecriture) as session:
            await session.initialize()
            outils = await session.list_tools()
            noms = {t.name for t in outils.tools}
            if tool not in noms:
                return {
                    "statut": "non_autorise",
                    "message": f"le profil {profil!r} n'a pas accès au tool {tool!r}",
                }
            resultat = await session.call_tool(tool, arguments)
            bloc = resultat.content[0] if resultat.content else None
            if bloc is None or not hasattr(bloc, "text"):
                return {"erreur": "réponse MCP sans contenu textuel"}
            return json.loads(bloc.text)


def lister_tools(profil: str) -> list[str]:
    return asyncio.run(_lister_async(profil))


def appeler(profil: str, tool: str, arguments: dict) -> dict:
    return asyncio.run(_appeler_async(profil, tool, arguments))
```

- [ ] **Step 5: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_front_mcp_client.py -v`
Expected: `5 passed` (chaque test relance un vrai sous-processus serveur ; quelques secondes
par test, c'est attendu)

- [ ] **Step 6: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `111 passed` (106 des Phases 1-5 + 5 de cette tâche)

- [ ] **Step 7: Commit**

```bash
git add front/__init__.py front/mcp_client.py requirements.txt tests/test_front_mcp_client.py
git commit -m "feat(front): pont Streamlit vers le serveur MCP (appeler, lister_tools)"
```

---

### Task 2: Interface Streamlit (`front/app.py`)

**Files:**
- Create: `front/app.py`

**Interfaces:**
- Consumes: `front.mcp_client.appeler`/`lister_tools` (Task 1) ; `sorabel_rag.extraction.EXTRACTEURS`,
  `sorabel_rag.chunking.chunker`, `sorabel_rag.ingestion.CORPUS`/`SORTIE`,
  `sorabel_rag.recherche.rechercher` (Phase 1, inchangés).
- Produces: rien consommé par une autre tâche — c'est le livrable terminal de ce chantier.

Pas de test automatisé (script Streamlit). Vérification manuelle en Task 3.

- [ ] **Step 1: Écrire `front/app.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add front/app.py
git commit -m "feat(front): interface Streamlit à deux sections (debug pipeline, tools MCP gouvernés)"
```

---

### Task 3: Vérification manuelle du front

**⚠️ Nécessite toutes les phases précédentes terminées** (`.env` réel, index Chroma régénéré,
`gouvernance/gouvernance.db` peuplé). Consomme de vrais appels Azure AI Foundry.

**Files:** aucun.

- [ ] **Step 1: Lancer l'application**

Run: `python -m streamlit run front/app.py`
Expected: le navigateur s'ouvre sur `http://localhost:8501`, titre « Sorabel Data Gateway —
test des briques » visible, deux onglets.

- [ ] **Step 2: Section « Pipeline RAG (debug) »**

- Choisir un fichier `fiches/REF-1024-v2.1.pdf`, cliquer « Extraire » → le JSON du document
  canonique s'affiche, `qualite.statut` vaut `"ok"`.
- Cliquer « Chunker le document extrait » → au moins un chunk affiché avec son texte complet
  (en-tête + corps).
- Requête `REF-1024`, cliquer « Comparer... » → trois colonnes de résultats, `REF-1024` en
  tête dans les trois (bonus de référence sujet).

- [ ] **Step 3: Section « Tools MCP » — profil `support`**

- Sélectionner `support` dans la barre latérale, cliquer « Rafraîchir tools/list » → 8 tools
  listés.
- `check_stock` avec `REF-1024` → `statut: ok`, `entrepot`/`quantite` affichés.
- `ask_database` avec « quelle est la marge sur REF-1024 ? » → `statut: non_autorise`.
- `get_schema` → le schéma affiché ne contient pas `marge_pct`.

- [ ] **Step 4: Section « Tools MCP » — profil `dev`**

- Sélectionner `dev`, rafraîchir → seulement 4 tools (`search_docs`, `get_document`,
  `list_sources`, `get_schema`).
- `search_docs` avec une requête quelconque → fonctionne (pas besoin de LLM).
- Note : les boutons `answer_question`/`ask_database`/`check_stock`/`order_status` restent
  visibles dans l'interface (l'UI ne masque pas les formulaires par profil, seule la liste
  `tools/list` reflète le périmètre) — cliquer dessus renvoie `statut: non_autorise` via
  `front.mcp_client.appeler`, ce n'est pas un bug.

Si les quatre étapes se comportent comme décrit, le front démontre correctement les 6
chantiers du projet de bout en bout. Aucun commit pour cette tâche.
