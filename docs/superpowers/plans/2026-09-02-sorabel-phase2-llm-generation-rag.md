# Phase 2 — Client LLM Azure AI Foundry + génération de réponse RAG

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter le client LLM partagé (Azure AI Foundry, déploiement GPT-5.4-mini) et le
tool `answer_question` du chantier 1 (`sorabel_rag/generation.py`) : refus déterministe sous
le seuil (E1, sans appel LLM), citations reconstruites en code depuis les métadonnées des
chunks réellement utilisés.

**Architecture:** Un nouveau package `sorabel_llm/` isole tout l'accès réseau derrière une
fonction `completer(messages) -> str`, réutilisée telle quelle par le Text-to-SQL en Phase 3.
`sorabel_rag/generation.py` compose `rechercher()` (existant, Phase 1 terminée) et
`sorabel_llm.completer()` sans dupliquer la logique de retrieval.

**Tech Stack:** `openai` (client `AzureOpenAI`) et `python-dotenv`, déjà installés dans
l'environnement (`openai==2.29.0`, `python-dotenv==1.2.2`) — vérifié par introspection de la
signature `AzureOpenAI.__init__` et `Completions.create` avant d'écrire ce plan.

## Global Constraints

- Langue du code de domaine, messages et tests : français.
- **Citations construites par le code, jamais par le LLM** (contrainte non négociable de
  `CLAUDE.md`) — dérivées uniquement des métadonnées des chunks passés au prompt.
- **Refus déterministe sous le seuil** : `resultats[0].score < SEUIL_REFUS` (import de
  `sorabel_rag.recherche.SEUIL_REFUS`, ne pas redéfinir la valeur) doit empêcher tout appel LLM
  — testé en vérifiant qu'un espion (spy) sur `completer` n'est jamais invoqué.
- Aucun appel réseau réel dans les tests automatisés (Task 1 et Task 2) : la frontière LLM
  (`completer`) et la frontière retrieval (`rechercher`) sont monkeypatchées. Le seul test avec
  un vrai appel Azure est Task 3, exécuté manuellement par un humain disposant d'un `.env` réel.
- `.env` ne doit jamais être committé — ajouté à `.gitignore` dans Task 1.
- Exécuter les tests avec `python -m pytest` depuis la racine du dépôt.

---

## File Structure

```
sorabel_llm/__init__.py      NOUVEAU : vide, fait de sorabel_llm/ un package
sorabel_llm/client.py         NOUVEAU : obtenir_client(), completer(messages) -> str
.env.example                   NOUVEAU : gabarit des 4 variables Azure, committé
.gitignore                     MODIFIÉ : ajoute .env
requirements.txt               MODIFIÉ : ajoute openai, python-dotenv
tests/test_llm_client.py       NOUVEAU : completer() avec client factice, erreur si var manquante
sorabel_rag/generation.py     NOUVEAU : repondre(question, k=5) -> dict
tests/test_generation.py       NOUVEAU : hors_corpus sans appel LLM, ok avec citations, dédoublonnage
```

---

### Task 1: Client LLM partagé (`sorabel_llm`)

**Files:**
- Create: `sorabel_llm/__init__.py`
- Create: `sorabel_llm/client.py`
- Create: `.env.example`
- Modify: `.gitignore`
- Modify: `requirements.txt`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: rien (nouveau package, aucune dépendance interne au dépôt).
- Produces: `sorabel_llm.client.completer(messages: list[dict], **kwargs) -> str` — Task 2 et
  la Phase 3 (Text-to-SQL) importent exactement cette fonction, avec cette signature.
  `sorabel_llm.client.obtenir_client()` — point d'extension interne, monkeypatché par les tests.

- [ ] **Step 1: Ajouter les dépendances**

Dans `requirements.txt`, ajouter à la fin :

```
# LLM (Azure AI Foundry)
openai>=2.0
python-dotenv>=1.2
```

- [ ] **Step 2: Créer le gabarit `.env.example` et ignorer `.env`**

Créer `.env.example` :

```
AZURE_OPENAI_ENDPOINT=https://<votre-ressource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<votre-cle>
AZURE_OPENAI_DEPLOYMENT=gpt-5.4-mini
AZURE_OPENAI_API_VERSION=2024-10-21
```

Dans `.gitignore`, ajouter une ligne (nouvelle section) :

```
# Secrets locaux
.env
```

- [ ] **Step 3: Créer le package et écrire le test qui échoue**

Créer `sorabel_llm/__init__.py` (vide).

Créer `tests/test_llm_client.py` :

```python
"""Client LLM partagé (Azure AI Foundry) : erreurs de configuration et appel."""

import pytest

from sorabel_llm import client as llm_client


def test_variable_manquante_leve_une_erreur_explicite(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    with pytest.raises(RuntimeError, match="AZURE_OPENAI_DEPLOYMENT"):
        llm_client._variable_requise("AZURE_OPENAI_DEPLOYMENT")


class _CompletionsFactice:
    def __init__(self):
        self.appels = []

    def create(self, **kwargs):
        self.appels.append(kwargs)
        return _ReponseFactice("réponse factice")


class _ChatFactice:
    def __init__(self):
        self.completions = _CompletionsFactice()


class _ClientFactice:
    def __init__(self):
        self.chat = _ChatFactice()


class _MessageFactice:
    def __init__(self, contenu):
        self.content = contenu


class _ChoixFactice:
    def __init__(self, contenu):
        self.message = _MessageFactice(contenu)


class _ReponseFactice:
    def __init__(self, contenu):
        self.choices = [_ChoixFactice(contenu)]


def test_completer_appelle_le_deploiement_configure_et_retourne_le_texte(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4-mini-test")
    client_factice = _ClientFactice()
    monkeypatch.setattr(llm_client, "obtenir_client", lambda: client_factice)

    resultat = llm_client.completer([{"role": "user", "content": "bonjour"}])

    assert resultat == "réponse factice"
    appel = client_factice.chat.completions.appels[0]
    assert appel["model"] == "gpt-5.4-mini-test"
    assert appel["messages"] == [{"role": "user", "content": "bonjour"}]
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'sorabel_llm'`

- [ ] **Step 5: Écrire `sorabel_llm/client.py`**

```python
"""Client LLM partagé : Azure AI Foundry (déploiement GPT-5.4-mini).

Un seul point d'appel pour la génération RAG (chantier 1) et Text-to-SQL (chantier 2) — un
seul endroit à changer si le déploiement ou le fournisseur change.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_client = None


def _variable_requise(nom: str) -> str:
    valeur = os.environ.get(nom)
    if not valeur:
        raise RuntimeError(
            f"{nom} manquante : copier .env.example vers .env et renseigner "
            "les identifiants Azure AI Foundry."
        )
    return valeur


def obtenir_client():
    """Chargé paresseusement : les modules qui importent ce fichier n'ont pas tous
    besoin d'un appel LLM — les tests unitaires du RAG et du SQL le monkeypatchent."""
    global _client
    if _client is None:
        from openai import AzureOpenAI

        _client = AzureOpenAI(
            azure_endpoint=_variable_requise("AZURE_OPENAI_ENDPOINT"),
            api_key=_variable_requise("AZURE_OPENAI_API_KEY"),
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
    return _client


def completer(messages: list[dict], **kwargs) -> str:
    """Un tour de conversation → le texte de la réponse. `messages` au format OpenAI
    ([{"role": "system"|"user"|"assistant", "content": str}, ...])."""
    deploiement = _variable_requise("AZURE_OPENAI_DEPLOYMENT")
    reponse = obtenir_client().chat.completions.create(
        model=deploiement, messages=messages, **kwargs
    )
    return reponse.choices[0].message.content
```

- [ ] **Step 6: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: `2 passed`

- [ ] **Step 7: Lancer toute la suite (pas de régression sur la Phase 1)**

Run: `python -m pytest -v`
Expected: `12 passed` (les 10 de la Phase 1 + les 2 de cette tâche)

- [ ] **Step 8: Commit**

```bash
git add sorabel_llm/ .env.example .gitignore requirements.txt tests/test_llm_client.py
git commit -m "feat: ajouter le client LLM partagé Azure AI Foundry (sorabel_llm)"
```

---

### Task 2: `answer_question` — génération de réponse RAG avec citations et refus déterministe

**Files:**
- Create: `sorabel_rag/generation.py`
- Test: `tests/test_generation.py`

**Interfaces:**
- Consumes: `sorabel_rag.recherche.rechercher(requete, k, config) -> list[Resultat]` et
  `sorabel_rag.recherche.SEUIL_REFUS` (`float`, existants, inchangés) ; `Resultat.chunk_id`
  (`str`), `Resultat.texte` (`str`, brut), `Resultat.score` (`float`), `Resultat.metadonnees`
  (`dict` avec au moins `doc_id`, `titre`, `type_document`, `reference`, `date`),
  `Resultat.reference` / `Resultat.titre` (propriétés `str`) — tous définis dans
  `sorabel_rag/recherche.py` (Phase 1, inchangé par cette tâche) ; `sorabel_rag.chunking.texte_complet(meta, texte_brut) -> str`
  (existant) ; `sorabel_llm.client.completer(messages: list[dict]) -> str` (Task 1).
- Produces: `sorabel_rag.generation.repondre(question: str, k: int = 5) -> dict` — retourne
  `{"statut": "hors_corpus", "message": str}` ou
  `{"statut": "ok", "reponse": str, "citations": list[dict], "chunks_utilises": list[str]}`.
  Chaque élément de `citations` est `{"titre": str, "reference": str | None, "date": str | None,
  "type_document": str}`. Cette signature est celle que Phase 4 (gouvernance) étendra avec un
  paramètre `perimetre` — ne pas anticiper ce paramètre ici.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_generation.py` :

```python
"""Génération de réponse RAG : refus déterministe (E1) et citations construites en code."""

import sorabel_rag.generation as generation
from sorabel_rag.recherche import Resultat


def _resultat(score, doc_id="fiche_technique:REF-1024:v2.1", chunk_id=None, **meta_extra):
    meta = {
        "doc_id": doc_id,
        "titre": "Disjoncteur différentiel 30mA",
        "type_document": "fiche_technique",
        "reference": "REF-1024",
        "date": "2025-01-10",
        **meta_extra,
    }
    return Resultat(chunk_id or f"{doc_id}#0", "corps du chunk", score, meta)


def test_hors_corpus_sous_le_seuil_naspelle_pas_le_llm(monkeypatch):
    appele = False

    def _completer_espion(messages):
        nonlocal appele
        appele = True
        return "ne devrait jamais être retourné"

    monkeypatch.setattr(generation, "rechercher", lambda question, k, config: [_resultat(1e-6)])
    monkeypatch.setattr(generation, "completer", _completer_espion)

    resultat = generation.repondre("capitale de l'Australie ?")

    assert resultat["statut"] == "hors_corpus"
    assert not appele


def test_hors_corpus_quand_aucun_resultat(monkeypatch):
    monkeypatch.setattr(generation, "rechercher", lambda question, k, config: [])
    resultat = generation.repondre("question quelconque")
    assert resultat["statut"] == "hors_corpus"


def test_reponse_ok_construit_les_citations_depuis_les_metadonnees(monkeypatch):
    monkeypatch.setattr(generation, "rechercher", lambda question, k, config: [_resultat(0.9)])
    monkeypatch.setattr(generation, "completer", lambda messages: "Le REF-1024 supporte 30mA.")

    resultat = generation.repondre("Quel est le seuil du REF-1024 ?")

    assert resultat["statut"] == "ok"
    assert resultat["reponse"] == "Le REF-1024 supporte 30mA."
    assert resultat["citations"] == [
        {"titre": "Disjoncteur différentiel 30mA", "reference": "REF-1024",
         "date": "2025-01-10", "type_document": "fiche_technique"}
    ]
    assert resultat["chunks_utilises"] == ["fiche_technique:REF-1024:v2.1#0"]


def test_citations_dedupliquees_par_document(monkeypatch):
    resultats = [
        _resultat(0.9, doc_id="procedure_sav:proc-casse-transport-01:v2.0", chunk_id="a#0",
                  titre="Procédure casse transport", type_document="procedure_sav",
                  reference="", date="2025-02-01"),
        _resultat(0.8, doc_id="procedure_sav:proc-casse-transport-01:v2.0", chunk_id="a#1",
                  titre="Procédure casse transport", type_document="procedure_sav",
                  reference="", date="2025-02-01"),
    ]
    monkeypatch.setattr(generation, "rechercher", lambda question, k, config: resultats)
    monkeypatch.setattr(generation, "completer", lambda messages: "réponse")

    resultat = generation.repondre("comment déclarer une casse transport ?")

    assert len(resultat["citations"]) == 1
    assert resultat["citations"][0]["reference"] is None  # chaîne vide -> None
    assert resultat["chunks_utilises"] == ["a#0", "a#1"]
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `python -m pytest tests/test_generation.py -v`
Expected: `FAILED` — `ModuleNotFoundError: No module named 'sorabel_rag.generation'`

- [ ] **Step 3: Écrire `sorabel_rag/generation.py`**

```python
"""Génération de réponse RAG : retrieval + appel LLM + citations construites en code.

Les citations ne sont JAMAIS demandées au LLM : elles sont dérivées des métadonnées des
chunks réellement passés au prompt (titre, référence, date) — contrainte non négociable.
"""

from __future__ import annotations

from sorabel_llm.client import completer

from .chunking import texte_complet
from .recherche import SEUIL_REFUS, Resultat, rechercher

PROMPT_SYSTEME = (
    "Tu es l'assistant documentaire de Sorabel, distributeur B2B de matériel électrique. "
    "Réponds à la question UNIQUEMENT à partir des extraits fournis ci-dessous, en français. "
    "Si les extraits ne permettent pas de répondre complètement, dis-le explicitement. "
    "Ne cite jamais tes sources toi-même : elles sont ajoutées automatiquement par le système."
)


def _construire_prompt(question: str, resultats: list[Resultat]) -> list[dict]:
    extraits = "\n\n---\n\n".join(
        texte_complet(r.metadonnees, r.texte) for r in resultats
    )
    return [
        {"role": "system", "content": PROMPT_SYSTEME},
        {"role": "user", "content": f"Extraits :\n\n{extraits}\n\nQuestion : {question}"},
    ]


def _construire_citations(resultats: list[Resultat]) -> list[dict]:
    """Une citation par document source, dédoublonnée, dans l'ordre de première apparition."""
    vues: dict[str, dict] = {}
    for r in resultats:
        doc_id = r.metadonnees.get("doc_id", r.chunk_id)
        if doc_id not in vues:
            vues[doc_id] = {
                "titre": r.titre,
                "reference": r.reference or None,
                "date": r.metadonnees.get("date") or None,
                "type_document": r.metadonnees.get("type_document", ""),
            }
    return list(vues.values())


def repondre(question: str, k: int = 5) -> dict:
    """Le tool `answer_question` du catalogue MCP (chantier 1)."""
    resultats = rechercher(question, k=k, config="hybride_rerank")
    if not resultats or resultats[0].score < SEUIL_REFUS:
        return {
            "statut": "hors_corpus",
            "message": "Je ne trouve pas de réponse à cette question dans le corpus documentaire.",
        }

    reponse = completer(_construire_prompt(question, resultats))
    return {
        "statut": "ok",
        "reponse": reponse,
        "citations": _construire_citations(resultats),
        "chunks_utilises": [r.chunk_id for r in resultats],
    }
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `python -m pytest tests/test_generation.py -v`
Expected: `4 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `python -m pytest -v`
Expected: `16 passed`

- [ ] **Step 6: Commit**

```bash
git add sorabel_rag/generation.py tests/test_generation.py
git commit -m "feat: ajouter answer_question (génération RAG, citations en code, refus E1)"
```

---

### Task 3: Vérification manuelle avec Azure AI Foundry réel

**⚠️ Cette tâche nécessite un `.env` réel (identifiants Azure AI Foundry de l'utilisateur) et
consomme de vrais appels API. Ne pas dispatcher cette tâche à un sous-agent sans que
l'utilisateur ait fourni ces identifiants et confirmé vouloir consommer son quota Azure pour
cette vérification.** Elle suppose aussi que la Phase 1 a été exécutée jusqu'au bout (Task 4 :
`data/canonique/` et `data/chroma/` régénérés avec `sous_type`/`diffusion_restreinte`).

**Files:** aucun — vérification manuelle, rien à committer.

- [ ] **Step 1: Créer le `.env` réel**

Copier `.env.example` vers `.env` et renseigner les 4 valeurs Azure AI Foundry réelles
(fournies par l'utilisateur).

- [ ] **Step 2: Question dans le corpus — vérifier le statut `ok` et les citations**

Run :
```bash
python -c "
from sorabel_rag.generation import repondre
r = repondre('Quelle est la procédure en cas de casse transport ?')
print(r['statut'])
print(r['reponse'][:200])
print(r['citations'])
"
```
Expected: `statut` vaut `ok`, `reponse` est un texte cohérent en français, `citations` contient
au moins un élément avec un `titre` non vide et `type_document == "procedure_sav"`.

- [ ] **Step 3: Question hors corpus — vérifier le statut `hors_corpus` et l'absence d'appel LLM**

Run :
```bash
python -c "
from sorabel_rag.generation import repondre
r = repondre('Quelle est la capitale de l\'Australie ?')
print(r)
"
```
Expected: `{'statut': 'hors_corpus', 'message': '...'}` — pas de clé `reponse` (donc pas d'appel
LLM déclenché, cohérent avec le test automatisé de Task 2).

- [ ] **Step 4: Consigner le résultat**

Aucun commit de code. Si les deux vérifications passent, la Phase 2 est validée de bout en
bout ; sinon, documenter l'écart observé avant de passer à la Phase 3.
