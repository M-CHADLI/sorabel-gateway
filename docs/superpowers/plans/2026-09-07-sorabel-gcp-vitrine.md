# Mise en production GCP (vitrine) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer la Sorabel Data Gateway sur GCP en deux services Cloud Run — un front Streamlit derrière IAP et un serveur MCP en HTTP streamable authentifié par OAuth 2.1 — sans perdre aucune garantie de gouvernance.

**Architecture:** Le serveur MCP devient un *Resource Server* : il valide des jetons (assertion IAP pour le front, Google Identity Platform pour les clients tiers) et résout le sujet en profil via un dépôt d'identités. Le périmètre, aujourd'hui figé au démarrage, est résolu à chaque requête par le décorateur déjà unique. L'état de lecture reste figé dans l'image ; seules les identités s'écrivent, dans Firestore.

**Tech Stack:** Python 3.12, `mcp>=1.20,<2` (auth et streamable-http natifs), PyJWT, `google-cloud-firestore`, Streamlit 1.59, Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Identity-Aware Proxy.

## Global Constraints

- **Spécification de référence** : `docs/superpowers/specs/2026-09-07-sorabel-gcp-vitrine-design.md`. En cas de contradiction avec ce plan, la spec fait foi — signaler l'écart plutôt que de trancher seul.
- **Les 117 tests existants doivent continuer de passer**, sans réseau et sans secret. Aucun test nouveau ne doit appeler Internet, ni Firestore, ni Google.
- **`required_scopes` est vide** : un jeton valide suffit, les droits viennent de la matrice. Ne pas superposer un second système d'autorisation.
- **Un sujet inconnu du dépôt d'identités n'obtient jamais de profil par défaut.** Le serveur MCP répond `{"statut": "non_autorise"}` ; seul le front propose l'inscription.
- **`SORABEL_PROFIL` n'est lu qu'en transport stdio.** En HTTP il est ignoré, sans exception.
- **Colonnes sensibles E5** — `produits.prix_achat_ht`, `produits.marge_pct`, `ventes.marge_ht` — hors périmètre pour `support` et `dev`. Aucune modification de ce plan ne doit les rendre atteignables.
- **Langue** : code de domaine, messages et commentaires en français (`reference`, `est_version_courante`, `statut`, `sources`). Les commentaires expliquent *pourquoi*.
- **Le journal ne contient jamais le contenu des résultats** — question, requête et volume seulement.
- **Aucun secret dans le dépôt ni dans l'image finale.**

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `gouvernance/identites.py` | **Créer.** Contrat `DepotIdentites` + implémentation SQLite |
| `gouvernance/identites_firestore.py` | **Créer.** Implémentation Firestore du même contrat |
| `gouvernance/journal.py` | **Modifier.** Sortie `stdout` ou fichier, `autorise` réel |
| `mcp_server/authentification.py` | **Créer.** `VerificateurJeton` (TokenVerifier du SDK), multi-émetteurs |
| `mcp_server/tools.py` | **Modifier.** 8 tools enregistrés, décorateur `_gouverne` par requête |
| `mcp_server/serveur.py` | **Modifier.** Transport stdio ou streamable-http, `AuthSettings` |
| `front/passerelle.py` | **Créer.** Client MCP HTTP relayant l'assertion IAP, lecture du sujet |
| `front/depot.py` | **Créer.** Fabrique choisissant SQLite ou Firestore selon l'environnement |
| `front/app_client.py` | **Modifier.** Page d'inscription, changement de profil, plus de sélecteur libre |
| `Dockerfile` | **Créer.** Deux étapes, image unique, deux entrypoints |
| `cloudbuild.yaml` | **Créer.** Tests, build, push, déploiement des deux services |
| `docs/EXPLOITATION.md` | **Créer.** Provisionnement GCP, commandes, exploitation |

---

### Task 1: Dépôt d'identités (SQLite)

**Files:**
- Create: `gouvernance/identites.py`
- Test: `tests/test_gouvernance_identites.py`

**Interfaces:**
- Consumes: la table `identites (sujet, profil, source)` de `gouvernance/schema.sql`, déjà présente.
- Produces: `DepotIdentitesSqlite(chemin_db)` avec `profil_de(sujet) -> str | None` et `attribuer(sujet, profil, source) -> None`. Toute la suite consomme ce contrat, jamais SQLite directement.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_gouvernance_identites.py
"""Le dépôt d'identités : la seule donnée qui s'écrit en production.

Les tests utilisent SQLite ; Firestore est testé séparément par une doublure. Le contrat
est duck-typé, sur le patron de Perimetre : rien n'importe la classe concrète.
"""

import sqlite3
from pathlib import Path

import pytest

from gouvernance.identites import DepotIdentitesSqlite
from gouvernance.seed import peupler


@pytest.fixture
def depot(tmp_path: Path) -> DepotIdentitesSqlite:
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    return DepotIdentitesSqlite(chemin)


def test_sujet_inconnu_ne_donne_aucun_profil(depot):
    # Jamais de profil par défaut : un inconnu reste un inconnu.
    assert depot.profil_de("sub-jamais-vu") is None


def test_attribuer_puis_relire(depot):
    depot.attribuer("sub-123", "commercial", source="demo")
    assert depot.profil_de("sub-123") == "commercial"


def test_attribuer_deux_fois_remplace_le_profil(depot):
    # Le bouton « changer de profil » réécrit la ligne au lieu d'en empiler une seconde.
    depot.attribuer("sub-123", "commercial", source="demo")
    depot.attribuer("sub-123", "support", source="demo")
    assert depot.profil_de("sub-123") == "support"


def test_la_source_est_conservee(depot, tmp_path):
    depot.attribuer("sub-123", "admin", source="demo")
    connexion = sqlite3.connect(tmp_path / "gouvernance.db")
    try:
        source = connexion.execute(
            "SELECT source FROM identites WHERE sujet = ?", ("sub-123",)
        ).fetchone()[0]
    finally:
        connexion.close()
    assert source == "demo"


def test_profil_inexistant_est_refuse(depot):
    # La matrice est la référence : on n'attribue pas un profil qui n'existe pas.
    with pytest.raises(ValueError, match="profil inconnu"):
        depot.attribuer("sub-123", "directeur", source="demo")
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `python -m pytest tests/test_gouvernance_identites.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'gouvernance.identites'`

- [ ] **Step 3: Écrire l'implémentation**

```python
# gouvernance/identites.py
"""Le dépôt d'identités : quel profil est attribué à quel sujet authentifié.

C'est la seule donnée qui s'écrit en production — la matrice, elle, est figée dans l'image.
Le contrat est duck-typé comme `Perimetre` : les appelants ne connaissent que deux méthodes,
ce qui permet de servir SQLite en développement et Firestore en production sans qu'aucun
d'eux n'importe l'autre.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class DepotIdentitesSqlite:
    """Implémentation locale, utilisée en développement et par les tests."""

    def __init__(self, chemin_db: Path | str):
        self._chemin = Path(chemin_db)

    def _connexion(self, lecture_seule: bool = True) -> sqlite3.Connection:
        if lecture_seule:
            return sqlite3.connect(f"file:{self._chemin.as_posix()}?mode=ro", uri=True)
        return sqlite3.connect(self._chemin)

    def profil_de(self, sujet: str) -> str | None:
        connexion = self._connexion()
        try:
            ligne = connexion.execute(
                "SELECT profil FROM identites WHERE sujet = ?", (sujet,)
            ).fetchone()
        finally:
            connexion.close()
        return ligne[0] if ligne else None

    def attribuer(self, sujet: str, profil: str, source: str) -> None:
        connexion = self._connexion(lecture_seule=False)
        try:
            connu = connexion.execute(
                "SELECT 1 FROM profils WHERE code = ? AND actif = 1", (profil,)
            ).fetchone()
            if not connu:
                raise ValueError(f"profil inconnu : {profil!r}")
            # REPLACE plutôt qu'INSERT : changer de profil réécrit la ligne du sujet,
            # sinon `profil_de` deviendrait ambigu.
            connexion.execute(
                "INSERT OR REPLACE INTO identites (sujet, profil, source) VALUES (?, ?, ?)",
                (sujet, profil, source),
            )
            connexion.commit()
        finally:
            connexion.close()
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `python -m pytest tests/test_gouvernance_identites.py -q`
Expected: PASS — 5 tests

- [ ] **Step 5: Lancer la suite complète**

Run: `python -m pytest -q`
Expected: PASS — 122 tests

- [ ] **Step 6: Commit**

```bash
git add gouvernance/identites.py tests/test_gouvernance_identites.py
git commit -m "feat(gouvernance): depot d'identites, contrat duck-type et implementation SQLite"
```

---

### Task 2: Journal vers la sortie standard, et refus réellement tracés

**Files:**
- Modify: `gouvernance/journal.py`
- Test: `tests/test_gouvernance_journal.py`

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: `journaliser(...)` inchangée dans sa signature. Nouveau comportement piloté par la variable d'environnement `SORABEL_JOURNAL` : `"stdout"` écrit une ligne JSON sur la sortie standard, toute autre valeur (ou son absence) conserve l'écriture dans `logs/appels.jsonl`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# À AJOUTER à tests/test_gouvernance_journal.py
import json


def test_journal_sur_stdout_quand_la_variable_le_demande(monkeypatch, capsys):
    """Cloud Logging indexe la sortie standard sans agent : en production, on n'écrit
    plus de fichier, qui serait de toute façon perdu au recyclage du conteneur."""
    monkeypatch.setenv("SORABEL_JOURNAL", "stdout")
    from gouvernance.journal import journaliser

    journaliser(
        profil="support",
        tool="ask_database",
        autorise=False,
        statut="non_autorise",
        entrees={"question": "quelles marges ?"},
        motif="tool hors perimetre",
    )
    ligne = json.loads(capsys.readouterr().out.strip())
    assert ligne["profil"] == "support"
    assert ligne["autorise"] is False
    assert ligne["statut"] == "non_autorise"


def test_journal_dans_un_fichier_par_defaut(monkeypatch, tmp_path):
    monkeypatch.delenv("SORABEL_JOURNAL", raising=False)
    import gouvernance.journal as journal

    monkeypatch.setattr(journal, "CHEMIN_JOURNAL", tmp_path / "appels.jsonl")
    journal.journaliser(
        profil="commercial", tool="check_stock", autorise=True,
        statut="ok", entrees={"ref": "REF-8842"},
    )
    contenu = (tmp_path / "appels.jsonl").read_text(encoding="utf-8")
    assert json.loads(contenu.strip())["tool"] == "check_stock"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `python -m pytest tests/test_gouvernance_journal.py -q`
Expected: FAIL — le premier test échoue, rien n'est écrit sur stdout

- [ ] **Step 3: Modifier `gouvernance/journal.py`**

Remplacer les deux dernières lignes de `journaliser` (l'ouverture du fichier) par :

```python
    # Sur Cloud Run, un fichier disparaît avec le conteneur : la sortie standard est le
    # seul journal durable, et Cloud Logging l'indexe sans agent.
    if os.environ.get("SORABEL_JOURNAL") == "stdout":
        print(json.dumps(ligne, ensure_ascii=False), flush=True)
        return

    CHEMIN_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with CHEMIN_JOURNAL.open("a", encoding="utf-8") as fichier:
        fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")
```

Ajouter `import os` en tête du fichier.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `python -m pytest tests/test_gouvernance_journal.py -q`
Expected: PASS

- [ ] **Step 5: Suite complète et commit**

```bash
python -m pytest -q
git add gouvernance/journal.py tests/test_gouvernance_journal.py
git commit -m "feat(gouvernance): journal sur stdout pour Cloud Logging"
```

---

### Task 3: Vérificateur de jeton

**Files:**
- Create: `mcp_server/authentification.py`
- Test: `tests/test_mcp_authentification.py`
- Modify: `pyproject.toml` (ajouter `pyjwt[crypto]>=2.8`)

**Interfaces:**
- Consumes: `TokenVerifier` et `AccessToken` de `mcp.server.auth.provider`.
- Produces: `VerificateurJeton(emetteurs: dict[str, str], recuperer_cles=None)` — implémente `async def verify_token(token: str) -> AccessToken | None`. `emetteurs` associe une URL d'émetteur à l'audience attendue. `recuperer_cles` est injectable pour les tests.

- [ ] **Step 1: Ajouter la dépendance**

```bash
uv add "pyjwt[crypto]>=2.8"
```

- [ ] **Step 2: Écrire les tests qui échouent**

```python
# tests/test_mcp_authentification.py
"""Validation des jetons. Aucun appel réseau : les clés sont injectées.

Deux émetteurs sont acceptés — l'assertion signée d'IAP, que le front relaie, et les jetons
de Google Identity Platform présentés par les clients MCP tiers. Un jeton valide chez l'un
mais destiné à l'autre doit être refusé : c'est la protection contre la confusion d'audience.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_server.authentification import VerificateurJeton

CLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
EMETTEURS = {
    "https://cloud.google.com/iap": "/projects/1/apps/sorabel",
    "https://securetoken.google.com/sorabel": "sorabel",
}


def _jeton(**surcharges) -> str:
    charge = {
        "iss": "https://cloud.google.com/iap",
        "aud": "/projects/1/apps/sorabel",
        "sub": "sub-123",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    charge.update(surcharges)
    return jwt.encode(charge, CLE, algorithm="RS256")


def _verificateur() -> VerificateurJeton:
    return VerificateurJeton(EMETTEURS, recuperer_cles=lambda _: CLE.public_key())


@pytest.mark.anyio
async def test_jeton_valide_donne_le_sujet():
    acces = await _verificateur().verify_token(_jeton())
    assert acces is not None
    assert acces.subject == "sub-123"


@pytest.mark.anyio
async def test_jeton_expire_est_refuse():
    jeton = _jeton(exp=int(time.time()) - 10)
    assert await _verificateur().verify_token(jeton) is None


@pytest.mark.anyio
async def test_emetteur_inconnu_est_refuse():
    jeton = _jeton(iss="https://attaquant.example")
    assert await _verificateur().verify_token(jeton) is None


@pytest.mark.anyio
async def test_audience_d_un_autre_emetteur_est_refusee():
    # Confusion d'audience : un jeton IAP valide, mais présenté avec l'audience de l'autre
    # émetteur, ne doit pas ouvrir la porte.
    jeton = _jeton(aud="sorabel")
    assert await _verificateur().verify_token(jeton) is None


@pytest.mark.anyio
async def test_jeton_illisible_est_refuse():
    assert await _verificateur().verify_token("pas-un-jeton") is None
```

Ajouter en tête du fichier de test la fixture `anyio_backend` si le projet n'en a pas :

```python
@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

Run: `python -m pytest tests/test_mcp_authentification.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.authentification'`

- [ ] **Step 4: Écrire l'implémentation**

```python
# mcp_server/authentification.py
"""Validation des jetons entrants — le serveur MCP est un Resource Server, pas un émetteur.

Il n'y a rien à déchiffrer ni à stocker : on vérifie une signature, un émetteur, une
audience et une expiration, puis on rend le sujet. Tout le reste de la gouvernance part de
ce sujet.

Deux émetteurs sont acceptés, et l'audience est vérifiée **par émetteur** : accepter
n'importe quelle audience de n'importe quel émetteur rouvrirait la confusion d'audience,
c'est-à-dire la possibilité de rejouer ici un jeton émis pour un autre service.
"""

from __future__ import annotations

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier

ALGORITHMES = ["RS256", "ES256"]


class VerificateurJeton(TokenVerifier):
    def __init__(self, emetteurs: dict[str, str], recuperer_cles=None, jwks: dict[str, str] | None = None):
        """`emetteurs` : URL d'émetteur → audience attendue.

        `recuperer_cles(jeton) -> clé publique` est injectable pour les tests ; à défaut, les
        clés sont récupérées par JWKS et mises en cache par PyJWKClient.
        """
        self._emetteurs = emetteurs
        self._jwks = jwks or {}
        self._recuperer_cles = recuperer_cles or self._cles_par_jwks
        self._clients: dict[str, PyJWKClient] = {}

    def _cles_par_jwks(self, jeton: str):
        emetteur = jwt.decode(jeton, options={"verify_signature": False})["iss"]
        if emetteur not in self._clients:
            self._clients[emetteur] = PyJWKClient(self._jwks[emetteur], cache_keys=True)
        return self._clients[emetteur].get_signing_key_from_jwt(jeton).key

    async def verify_token(self, token: str) -> AccessToken | None:
        """Renvoie None sur tout jeton douteux — le SDK traduit cela en 401.

        On ne distingue pas les causes de rejet dans la valeur de retour : un attaquant
        n'apprend pas si c'est l'émetteur, l'audience ou la signature qui a échoué.
        """
        try:
            emetteur = jwt.decode(token, options={"verify_signature": False}).get("iss")
        except jwt.PyJWTError:
            return None

        audience = self._emetteurs.get(emetteur)
        if audience is None:
            return None

        try:
            charge = jwt.decode(
                token,
                self._recuperer_cles(token),
                algorithms=ALGORITHMES,
                audience=audience,
                issuer=emetteur,
            )
        except jwt.PyJWTError:
            return None

        sujet = charge.get("sub")
        if not sujet:
            return None

        return AccessToken(
            token=token,
            client_id=charge.get("azp") or emetteur,
            scopes=[],
            expires_at=charge.get("exp"),
            subject=sujet,
            claims=charge,
        )
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `python -m pytest tests/test_mcp_authentification.py -q`
Expected: PASS — 5 tests

- [ ] **Step 6: Suite complète et commit**

```bash
python -m pytest -q
git add mcp_server/authentification.py tests/test_mcp_authentification.py pyproject.toml uv.lock
git commit -m "feat(mcp): verificateur de jeton multi-emetteurs, audience verifiee par emetteur"
```

---

### Task 4: Périmètre résolu à chaque requête

**Files:**
- Modify: `mcp_server/tools.py`
- Test: `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `DepotIdentitesSqlite` (Task 1), `get_access_token` de `mcp.server.auth.middleware.auth_context`.
- Produces: `enregistrer_tools(mcp, resolveur_perimetre)` où `resolveur_perimetre() -> Perimetre` est appelé **à chaque requête**. Les 8 tools sont désormais enregistrés inconditionnellement.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# À AJOUTER à tests/test_mcp_tools.py
"""Le contrôle passe du démarrage à la requête : c'est le changement structurel du
passage en HTTP. Un processus ne sert plus un profil unique."""


class _PerimetreFactice:
    def __init__(self, profil, tools):
        self.profil = profil
        self._tools = set(tools)

    def peut_appeler(self, tool):
        return tool in self._tools

    def collections_autorisees(self):
        return frozenset({"fiches"})

    def tables_autorisees(self):
        return frozenset({"produits"})

    def colonnes_interdites(self, table):
        return frozenset()


def test_les_huit_tools_sont_enregistres_quel_que_soit_le_profil():
    from mcp.server.fastmcp import FastMCP
    from mcp_server.tools import enregistrer_tools

    mcp = FastMCP(name="test")
    enregistrer_tools(mcp, lambda: _PerimetreFactice("dev", {"search_docs"}))
    noms = {outil.name for outil in mcp._tool_manager.list_tools()}
    assert len(noms) == 8


@pytest.mark.anyio
async def test_un_tool_hors_perimetre_renvoie_non_autorise_et_est_journalise(monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from mcp_server.tools import enregistrer_tools
    import gouvernance.journal as journal

    traces = []
    monkeypatch.setattr(journal, "journaliser", lambda **kw: traces.append(kw))
    import mcp_server.tools as tools_module
    monkeypatch.setattr(tools_module, "journaliser", lambda **kw: traces.append(kw))

    mcp = FastMCP(name="test")
    enregistrer_tools(mcp, lambda: _PerimetreFactice("dev", {"search_docs"}))
    resultat = await mcp._tool_manager.call_tool("ask_database", {"question": "combien ?"})

    assert resultat["statut"] == "non_autorise"
    assert traces and traces[-1]["autorise"] is False
    assert traces[-1]["tool"] == "ask_database"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `python -m pytest tests/test_mcp_tools.py -q`
Expected: FAIL — `enregistrer_tools` attend un `Perimetre`, pas un appelable

- [ ] **Step 3: Réécrire l'ossature de `mcp_server/tools.py`**

Remplacer la signature et le décorateur ; le corps des huit fonctions de tool reste identique, à ceci près qu'elles obtiennent `perimetre` par `_perimetre_courant()` au lieu de la fermeture.

```python
def enregistrer_tools(mcp, resolveur_perimetre) -> None:
    """Enregistre les 8 tools. Le périmètre est résolu à CHAQUE appel.

    En stdio, un processus servait un profil et `tools/list` filtré tenait lieu
    d'intercepteur d'entrée. En HTTP, le processus sert tout le monde : le contrôle
    descend donc dans le décorateur, qui reste le point de passage unique.
    """

    def _gouverne(nom_tool: str):
        """Résout le périmètre, applique la matrice, journalise — dans cet ordre.

        Un refus est journalisé comme un appel : c'est ce que le brief demande, et ce que
        l'architecture stdio ne permettait pas puisqu'un tool non autorisé n'existait pas.
        """
        def decorateur(func):
            @functools.wraps(func)
            def enveloppe(*args, **kwargs):
                debut = time.monotonic()
                try:
                    perimetre = resolveur_perimetre()
                except Exception as erreur:
                    journaliser(
                        profil="inconnu", tool=nom_tool, autorise=False,
                        statut="non_autorise", entrees=kwargs,
                        duree_ms=(time.monotonic() - debut) * 1000,
                        motif=str(erreur),
                    )
                    return {
                        "statut": "non_autorise",
                        "message": "Identité inconnue : aucun profil ne vous est attribué.",
                    }

                if not perimetre.peut_appeler(nom_tool):
                    journaliser(
                        profil=perimetre.profil, tool=nom_tool, autorise=False,
                        statut="non_autorise", entrees=kwargs,
                        duree_ms=(time.monotonic() - debut) * 1000,
                        motif="tool hors perimetre du profil",
                    )
                    return {
                        "statut": "non_autorise",
                        "message": f"le profil {perimetre.profil!r} n'a pas accès au tool {nom_tool!r}",
                    }

                resultat = func(*args, perimetre=perimetre, **kwargs)
                journaliser(
                    profil=perimetre.profil, tool=nom_tool, autorise=True,
                    statut=resultat.get("statut", "ok"), entrees=kwargs,
                    sql=resultat.get("sql"), n_lignes=resultat.get("n_lignes", 0),
                    duree_ms=(time.monotonic() - debut) * 1000,
                    motif=resultat.get("message"),
                )
                return resultat
            return enveloppe
        return decorateur
```

Puis chaque tool perd son `if perimetre.peut_appeler(...)` englobant et reçoit `perimetre` en paramètre nommé. Exemple complet pour deux d'entre eux — appliquer le même patron aux six autres :

```python
    @mcp.tool()
    @_gouverne("answer_question")
    def answer_question(question: str, *, perimetre) -> dict:
        """Réponse rédigée avec sources, à partir du corpus documentaire Sorabel.
        N'utilisez PAS ce tool pour obtenir des extraits bruts : voyez search_docs.
        Statuts possibles : ok, hors_corpus (aucune réponse trouvée, à afficher tel quel,
        pas comme une panne)."""
        return repondre(question, perimetre=perimetre)

    @mcp.tool()
    @_gouverne("check_stock")
    def check_stock(ref: str, *, perimetre) -> dict:
        """Stock par entrepôt pour UNE référence précise (format REF-XXXX). Utilisez ce
        tool quand la question porte sur une référence précise, pas un agrégat — pour un
        agrégat (ex. "quelles références sont sous le seuil ?"), voyez ask_database."""
        return _sql_check_stock(ref)
```

**Attention** : `functools.wraps` conserve la signature, or FastMCP la lit pour construire le schéma du tool. Le paramètre `perimetre` étant injecté par le décorateur, il doit être retiré du schéma exposé. Vérifier au Step 4 que `mcp._tool_manager.list_tools()` n'expose pas `perimetre` ; si c'est le cas, remplacer `functools.wraps(func)` par une copie explicite de `__name__`, `__doc__` et d'une signature amputée du paramètre.

- [ ] **Step 4: Vérifier que le schéma exposé ne contient pas `perimetre`**

Run:
```bash
python -c "
from mcp.server.fastmcp import FastMCP
from mcp_server.tools import enregistrer_tools
class P:
    profil='admin'
    def peut_appeler(self,t): return True
    def collections_autorisees(self): return frozenset()
    def tables_autorisees(self): return frozenset()
    def colonnes_interdites(self,t): return frozenset()
m=FastMCP(name='t'); enregistrer_tools(m, lambda: P())
for o in m._tool_manager.list_tools():
    assert 'perimetre' not in str(o.inputSchema), o.name
print('schemas propres')
"
```
Expected: `schemas propres`

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `python -m pytest tests/test_mcp_tools.py -q`
Expected: PASS

- [ ] **Step 6: Suite complète et commit**

```bash
python -m pytest -q
git add mcp_server/tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): perimetre resolu par requete, refus journalises"
```

---

### Task 5: Transport HTTP et métadonnées de ressource protégée

**Files:**
- Modify: `mcp_server/serveur.py`
- Test: `tests/test_mcp_serveur.py`

**Interfaces:**
- Consumes: `VerificateurJeton` (Task 3), `enregistrer_tools` (Task 4), `DepotIdentitesSqlite` (Task 1).
- Produces: `construire_serveur(chemin_gouvernance_db=…, depot_identites=None) -> FastMCP`. Le transport est choisi par `SORABEL_TRANSPORT` (`stdio` par défaut, `http` en production).

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# À AJOUTER à tests/test_mcp_serveur.py

def test_en_stdio_le_profil_vient_de_la_variable_d_environnement(monkeypatch, tmp_path):
    from gouvernance.seed import peupler
    from mcp_server.serveur import construire_serveur

    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    monkeypatch.setenv("SORABEL_TRANSPORT", "stdio")
    monkeypatch.setenv("SORABEL_PROFIL", "support")
    serveur = construire_serveur(chemin)
    assert serveur is not None


def test_en_http_la_variable_de_profil_est_ignoree(monkeypatch, tmp_path):
    """Accepter SORABEL_PROFIL en HTTP rouvrirait exactement la faille qu'on ferme :
    l'appelant qui déclare son identité."""
    from gouvernance.seed import peupler
    from mcp_server.serveur import resoudre_profil_http

    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    monkeypatch.setenv("SORABEL_TRANSPORT", "http")
    monkeypatch.setenv("SORABEL_PROFIL", "admin")

    from gouvernance.identites import DepotIdentitesSqlite
    depot = DepotIdentitesSqlite(chemin)

    with pytest.raises(PermissionError, match="aucun profil"):
        resoudre_profil_http(depot, sujet="sub-inconnu")


def test_en_http_le_profil_vient_du_depot(monkeypatch, tmp_path):
    from gouvernance.identites import DepotIdentitesSqlite
    from gouvernance.seed import peupler
    from mcp_server.serveur import resoudre_profil_http

    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    depot = DepotIdentitesSqlite(chemin)
    depot.attribuer("sub-123", "support", source="demo")
    assert resoudre_profil_http(depot, sujet="sub-123") == "support"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `python -m pytest tests/test_mcp_serveur.py -q`
Expected: FAIL — `ImportError: cannot import name 'resoudre_profil_http'`

- [ ] **Step 3: Réécrire `mcp_server/serveur.py`**

```python
"""Serveur MCP : stdio en développement, HTTP streamable en production.

`resoudre_profil_stdio` et `resoudre_profil_http` sont les DEUX seuls points liés au
transport. Le reste — matrice, Perimetre, tools — est identique d'un mode à l'autre.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from gouvernance.identites import DepotIdentitesSqlite
from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre

from .authentification import VerificateurJeton
from .tools import enregistrer_tools

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_GOUVERNANCE_DB = RACINE / "gouvernance" / "gouvernance.db"


def transport() -> str:
    return os.environ.get("SORABEL_TRANSPORT", "stdio")


def resoudre_profil_stdio() -> str:
    profil = os.environ.get("SORABEL_PROFIL")
    if not profil:
        raise RuntimeError(
            "SORABEL_PROFIL doit être défini en transport stdio "
            "(ex. SORABEL_PROFIL=support python -m mcp_server.serveur)"
        )
    return profil


def resoudre_profil_http(depot, sujet: str) -> str:
    """Le profil vient du dépôt d'identités, jamais de l'appelant.

    Un sujet authentifié mais inconnu du dépôt n'obtient AUCUN profil par défaut : le
    serveur n'inscrit personne, c'est le front qui propose l'inscription.
    """
    profil = depot.profil_de(sujet)
    if profil is None:
        raise PermissionError(f"aucun profil attribué au sujet {sujet!r}")
    return profil


def _emetteurs() -> dict[str, str]:
    """URL d'émetteur → audience attendue, l'un pour IAP, l'autre pour les clients tiers."""
    emetteurs = {}
    if audience_iap := os.environ.get("SORABEL_IAP_AUDIENCE"):
        emetteurs["https://cloud.google.com/iap"] = audience_iap
    if emetteur := os.environ.get("SORABEL_OIDC_ISSUER"):
        emetteurs[emetteur] = os.environ["SORABEL_OIDC_AUDIENCE"]
    return emetteurs


def construire_serveur(
    chemin_gouvernance_db: Path = CHEMIN_GOUVERNANCE_DB, depot_identites=None
) -> FastMCP:
    matrice = charger_matrice(chemin_gouvernance_db)
    depot = depot_identites or DepotIdentitesSqlite(chemin_gouvernance_db)

    if transport() == "stdio":
        perimetre_fige = Perimetre(resoudre_profil_stdio(), matrice)
        mcp = FastMCP(name="sorabel-data-gateway")
        enregistrer_tools(mcp, lambda: perimetre_fige)
        return mcp

    def resolveur() -> Perimetre:
        acces = get_access_token()
        if acces is None:
            raise PermissionError("appel non authentifié")
        return Perimetre(resoudre_profil_http(depot, acces.subject), matrice)

    mcp = FastMCP(
        name="sorabel-data-gateway",
        token_verifier=VerificateurJeton(
            _emetteurs(),
            jwks={
                "https://cloud.google.com/iap": "https://www.gstatic.com/iap/verify/public_key-jwk",
                os.environ.get("SORABEL_OIDC_ISSUER", ""): os.environ.get("SORABEL_OIDC_JWKS", ""),
            },
        ),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(os.environ["SORABEL_OIDC_ISSUER"]),
            resource_server_url=AnyHttpUrl(os.environ["SORABEL_URL_PUBLIQUE"]),
            required_scopes=[],
        ),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
    enregistrer_tools(mcp, resolveur)
    return mcp


if __name__ == "__main__":
    mode = "stdio" if transport() == "stdio" else "streamable-http"
    construire_serveur().run(transport=mode)
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `python -m pytest tests/test_mcp_serveur.py -q`
Expected: PASS

- [ ] **Step 5: Vérifier les métadonnées à la main**

Run:
```bash
SORABEL_TRANSPORT=http SORABEL_URL_PUBLIQUE=http://localhost:8080 \
SORABEL_OIDC_ISSUER=https://securetoken.google.com/test SORABEL_OIDC_AUDIENCE=test \
SORABEL_OIDC_JWKS=https://example.invalid/jwks \
python -m mcp_server.serveur &
sleep 3
curl -s -i http://localhost:8080/mcp | head -5
curl -s http://localhost:8080/.well-known/oauth-protected-resource
kill %1
```
Expected: `401` avec un en-tête `WWW-Authenticate` mentionnant `resource_metadata`, puis un JSON contenant `authorization_servers`.

- [ ] **Step 6: Suite complète et commit**

```bash
python -m pytest -q
git add mcp_server/serveur.py tests/test_mcp_serveur.py
git commit -m "feat(mcp): transport HTTP streamable et metadonnees de ressource protegee"
```

---

### Task 6: Dépôt d'identités Firestore

**Files:**
- Create: `gouvernance/identites_firestore.py`
- Test: `tests/test_gouvernance_identites_firestore.py`
- Modify: `pyproject.toml` (ajouter `google-cloud-firestore>=2.16`)

**Interfaces:**
- Consumes: le contrat de Task 1.
- Produces: `DepotIdentitesFirestore(client, collection="identites", profils_valides=frozenset())` — mêmes deux méthodes. `client` est injecté, ce qui rend le test possible sans réseau.

- [ ] **Step 1: Ajouter la dépendance**

```bash
uv add "google-cloud-firestore>=2.16"
```

- [ ] **Step 2: Écrire les tests qui échouent**

```python
# tests/test_gouvernance_identites_firestore.py
"""Firestore avec un client factice : le contrat est testé, pas le SDK de Google.

Aucun appel réseau ni émulateur — la suite doit rester exécutable dans Cloud Build sans
aucun secret.
"""

import pytest

from gouvernance.identites_firestore import DepotIdentitesFirestore


class _Document:
    def __init__(self, magasin, identifiant):
        self._magasin, self._id = magasin, identifiant

    def get(self):
        return _Instantane(self._magasin.get(self._id))

    def set(self, donnees):
        self._magasin[self._id] = dict(donnees)


class _Instantane:
    def __init__(self, donnees):
        self._donnees = donnees

    @property
    def exists(self):
        return self._donnees is not None

    def to_dict(self):
        return self._donnees


class _Collection:
    def __init__(self, magasin):
        self._magasin = magasin

    def document(self, identifiant):
        return _Document(self._magasin, identifiant)


class _ClientFactice:
    def __init__(self):
        self.magasin = {}

    def collection(self, _nom):
        return _Collection(self.magasin)


@pytest.fixture
def depot():
    return DepotIdentitesFirestore(
        _ClientFactice(), profils_valides=frozenset({"support", "commercial", "dev", "admin"})
    )


def test_sujet_inconnu_ne_donne_aucun_profil(depot):
    assert depot.profil_de("sub-jamais-vu") is None


def test_attribuer_puis_relire(depot):
    depot.attribuer("sub-123", "commercial", source="demo")
    assert depot.profil_de("sub-123") == "commercial"


def test_attribuer_deux_fois_remplace_le_profil(depot):
    depot.attribuer("sub-123", "commercial", source="demo")
    depot.attribuer("sub-123", "support", source="demo")
    assert depot.profil_de("sub-123") == "support"


def test_profil_inexistant_est_refuse(depot):
    with pytest.raises(ValueError, match="profil inconnu"):
        depot.attribuer("sub-123", "directeur", source="demo")
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

Run: `python -m pytest tests/test_gouvernance_identites_firestore.py -q`
Expected: FAIL — module introuvable

- [ ] **Step 4: Écrire l'implémentation**

```python
# gouvernance/identites_firestore.py
"""Dépôt d'identités sur Firestore — la seule donnée en écriture de la production.

Le client est injecté plutôt que construit ici : c'est ce qui permet de tester le contrat
avec une doublure, sans réseau ni émulateur, et de garder la suite exécutable dans Cloud
Build sans le moindre secret.

La liste des profils valides est passée à la construction, extraite de la matrice figée
dans l'image : Firestore ne connaît pas la matrice, et on n'écrit pas une identité qui
pointerait vers un profil inexistant.
"""

from __future__ import annotations


class DepotIdentitesFirestore:
    def __init__(self, client, collection: str = "identites", profils_valides=frozenset()):
        self._collection = client.collection(collection)
        self._profils_valides = frozenset(profils_valides)

    def profil_de(self, sujet: str) -> str | None:
        instantane = self._collection.document(sujet).get()
        if not instantane.exists:
            return None
        return (instantane.to_dict() or {}).get("profil")

    def attribuer(self, sujet: str, profil: str, source: str) -> None:
        if self._profils_valides and profil not in self._profils_valides:
            raise ValueError(f"profil inconnu : {profil!r}")
        # `set` sans merge : changer de profil réécrit le document entier, comme le
        # INSERT OR REPLACE de l'implémentation SQLite.
        self._collection.document(sujet).set({"profil": profil, "source": source})
```

- [ ] **Step 5: Lancer les tests et la suite, puis commiter**

```bash
python -m pytest tests/test_gouvernance_identites_firestore.py -q
python -m pytest -q
git add gouvernance/identites_firestore.py tests/test_gouvernance_identites_firestore.py pyproject.toml uv.lock
git commit -m "feat(gouvernance): depot d'identites Firestore, client injecte"
```

---

### Task 7: Passerelle HTTP du front

**Files:**
- Create: `front/passerelle.py`
- Test: `tests/test_front_passerelle.py`

**Interfaces:**
- Consumes: rien du projet ; `mcp.client.streamable_http` et `mcp.ClientSession`.
- Produces: `assertion_iap() -> str | None` (lit `st.context.headers`), `sujet_du_jeton(assertion: str | None) -> str | None`, `lister_tools(assertion: str | None) -> list[str]`, `appeler(assertion: str | None, tool: str, arguments: dict) -> dict`. Remplace `front/mcp_client.py` pour le déploiement ; le fichier stdio est conservé pour le développement local.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_front_passerelle.py
"""La passerelle relaie l'assertion IAP sans jamais la fabriquer ni la modifier."""

import pytest

from front import passerelle


def test_assertion_lue_dans_l_entete(monkeypatch):
    monkeypatch.setattr(
        passerelle, "_entetes", lambda: {"X-Goog-IAP-JWT-Assertion": "jeton-abc"}
    )
    assert passerelle.assertion_iap() == "jeton-abc"


def test_entete_absent_donne_none(monkeypatch):
    monkeypatch.setattr(passerelle, "_entetes", lambda: {})
    assert passerelle.assertion_iap() is None


def test_entete_insensible_a_la_casse(monkeypatch):
    # Les serveurs HTTP normalisent la casse des en-têtes de façons variées.
    monkeypatch.setattr(passerelle, "_entetes", lambda: {"x-goog-iap-jwt-assertion": "jeton-abc"})
    assert passerelle.assertion_iap() == "jeton-abc"


def test_sujet_lu_sans_verifier_la_signature():
    """Le front lit le sujet pour l'afficher et interroger le dépôt ; il ne VÉRIFIE rien.

    La vérification est faite par le serveur MCP, qui seul décide. Décoder ici sans
    vérifier est donc sûr — à condition que rien de sensible n'en dépende côté front.
    """
    import jwt

    jeton = jwt.encode({"sub": "sub-123", "aud": "peu-importe"}, "secret", algorithm="HS256")
    assert passerelle.sujet_du_jeton(jeton) == "sub-123"


def test_sujet_de_none_est_none():
    assert passerelle.sujet_du_jeton(None) is None


def test_sujet_d_un_jeton_illisible_est_none():
    assert passerelle.sujet_du_jeton("pas-un-jeton") is None


def test_appel_sans_assertion_ne_contacte_pas_le_serveur(monkeypatch):
    appels = []
    monkeypatch.setattr(passerelle, "_appeler_distant", lambda *a, **k: appels.append(a))
    resultat = passerelle.appeler(None, "check_stock", {"ref": "REF-8842"})
    assert resultat["statut"] == "non_autorise"
    assert appels == []
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `python -m pytest tests/test_front_passerelle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'front.passerelle'`

- [ ] **Step 3: Écrire l'implémentation**

```python
# front/passerelle.py
"""Pont HTTP entre Streamlit et le serveur MCP déployé.

Le front ne fabrique aucun jeton : Identity-Aware Proxy authentifie la personne avant que
la requête n'atteigne Streamlit et dépose une assertion signée dans un en-tête. La
passerelle la recopie telle quelle vers le serveur MCP, qui la valide. Streamlit ne
manipule donc jamais de secret d'identité — c'est ce qui rend ce chemin sûr sans qu'on ait
à écrire de flux OAuth côté interface.
"""

from __future__ import annotations

import asyncio
import json
import os

ENTETE_IAP = "x-goog-iap-jwt-assertion"
URL_MCP = os.environ.get("SORABEL_URL_MCP", "http://localhost:8080/mcp")
DELAI = 300.0


def _entetes() -> dict:
    """Isolé pour être remplaçable en test : `st.context` n'existe qu'en session."""
    import streamlit as st

    return dict(st.context.headers or {})


def assertion_iap() -> str | None:
    entetes = {cle.lower(): valeur for cle, valeur in _entetes().items()}
    return entetes.get(ENTETE_IAP)


def sujet_du_jeton(assertion: str | None) -> str | None:
    """Lit le `sub` sans vérifier la signature — le front n'est pas juge.

    C'est le serveur MCP qui valide et décide ; le front n'a besoin du sujet que pour
    afficher qui est connecté et demander son profil au dépôt. Un jeton forgé ne donnerait
    donc rien de plus qu'un écran mal rempli : aucun appel de tool ne passerait.
    """
    if not assertion:
        return None
    import jwt

    try:
        return jwt.decode(assertion, options={"verify_signature": False}).get("sub")
    except jwt.PyJWTError:
        return None


async def _session(assertion: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    entetes = {"Authorization": f"Bearer {assertion}"}
    async with streamablehttp_client(URL_MCP, headers=entetes) as (lecture, ecriture, _):
        async with ClientSession(lecture, ecriture) as session:
            await session.initialize()
            yield session


async def _appeler_distant(assertion: str, tool: str | None, arguments: dict | None):
    async for session in _session(assertion):
        if tool is None:
            outils = await session.list_tools()
            return sorted(o.name for o in outils.tools)
        resultat = await session.call_tool(tool, arguments or {})
        bloc = resultat.content[0] if resultat.content else None
        if bloc is None or not hasattr(bloc, "text"):
            return {"statut": "erreur", "message": "réponse MCP sans contenu textuel"}
        try:
            return json.loads(bloc.text)
        except json.JSONDecodeError:
            return {"statut": "erreur", "message": bloc.text}


def _executer(coroutine):
    return asyncio.run(asyncio.wait_for(coroutine, timeout=DELAI))


def lister_tools(assertion: str | None) -> list[str]:
    if not assertion:
        return []
    return _executer(_appeler_distant(assertion, None, None))


def appeler(assertion: str | None, tool: str, arguments: dict) -> dict:
    if not assertion:
        return {
            "statut": "non_autorise",
            "message": "Session non authentifiée : rechargez la page.",
        }
    return _executer(_appeler_distant(assertion, tool, arguments))
```

- [ ] **Step 4: Lancer les tests, vérifier le succès, commiter**

```bash
python -m pytest tests/test_front_passerelle.py -q
python -m pytest -q
git add front/passerelle.py tests/test_front_passerelle.py
git commit -m "feat(front): passerelle HTTP relayant l'assertion IAP"
```

---

### Task 8: Page d'inscription et changement de profil

**Décision d'architecture, arbitrée avant l'écriture de cette tâche (revue de la Task 4).**
Depuis la Task 4, `tools/list` renvoie **les 8 tools pour tout appelant** — le filtrage par
profil a migré de l'enregistrement vers le décorateur, résolu à chaque requête. Un front qui
dériverait sa navigation de `lister_tools()` (donc de `tools/list`) afficherait 8/8 pour
*tous* les profils, y compris `dev` : le bandeau de gouvernance mentirait, et quatre entrées
de menu mortes apparaîtraient en profil restreint. C'est un vrai bug, pas une nuance.

**La correction ne touche pas FastMCP.** La matrice d'accès est figée dans l'image, en
lecture seule, au même endroit pour les deux services (§5 de la conception GCP). Le front
peut donc calculer les droits d'un profil en lisant **la même matrice que le serveur**, sans
passer par le protocole MCP :

```python
from gouvernance.modeles import charger_matrice
from gouvernance.perimetre import Perimetre

matrice = charger_matrice(RACINE / "gouvernance" / "gouvernance.db")
perimetre = Perimetre(profil, matrice)
tools_accordes = {t for t in CodeTool.__args__ if perimetre.peut_appeler(t)}
```

`tools/list` (via `lister_tools()`) garde un rôle, mais un rôle différent : vérifier que le
transport répond, pas décider ce qui s'affiche. Aucune UI ne doit plus se brancher dessus.

**Files:**
- Modify: `front/app_client.py`
- Create: `front/depot.py`

**Interfaces:**
- Consumes: `assertion_iap`, `sujet_du_jeton`, `appeler` de `front.passerelle` (Task 7) ; `DepotIdentitesSqlite` (Task 1) et `DepotIdentitesFirestore` (Task 6) ; `charger_matrice` de `gouvernance.modeles` et `Perimetre` de `gouvernance.perimetre` (déjà existants, Phase 4).
- Produces: `front.depot.depot_identites()` — la fabrique, seule à connaître les deux implémentations d'identités. `front.depot.tools_accordes(profil) -> frozenset[str]` — les droits du profil, lus depuis la matrice figée, indépendamment du protocole MCP.

- [ ] **Step 1: Remplacer la source des tools et du profil**

Dans la barre latérale, le `st.selectbox` de profil disparaît. La navigation cesse de
dépendre de `tools/list` :

```python
from front.depot import depot_identites, tools_accordes
from front.passerelle import appeler, assertion_iap, sujet_du_jeton

assertion = assertion_iap()
sujet = sujet_du_jeton(assertion)
profil = depot_identites().profil_de(sujet) if sujet else None
tools = tools_accordes(profil) if profil else frozenset()
```

`tools` remplace l'ancien `st.session_state["_tools"]` alimenté par `lister_tools()` partout
où `NAVIGATION` et le panneau « Accès accordés » le consultent. Les appels
`appeler(profil, "tool", {...})` deviennent `appeler(assertion, "tool", {...})` dans les huit
vues — le profil n'est plus un paramètre d'appel, il est porté par le jeton.

- [ ] **Step 2: Écrire la page d'inscription**

Rendue à la place de l'application quand `profil is None` :

```python
def page_inscription(sujet: str) -> None:
    """Affichée quand l'identité est établie mais qu'aucun profil n'est attribué.

    L'identité vient d'IAP et n'est pas négociable ; seul le profil est en libre-service, et
    seulement en mode démonstration. Le bandeau le dit, pour qu'un visiteur ne prenne pas
    cette facilité pour le fonctionnement normal du produit.
    """
    st.markdown(
        "<div class='bandeau'><span class='marque'>" + LOGO + "</span>"
        "<span class='titre'>Bienvenue sur la Sorabel Data Gateway</span></div>",
        unsafe_allow_html=True,
    )
    st.info(
        "**Mode démonstration** — vous choisissez ici votre profil. En exploitation réelle, "
        "les profils sont attribués par un administrateur ; votre identité, elle, est déjà "
        "établie par Google et n'est pas modifiable."
    )
    st.caption(f"Connecté en tant que {sujet}")

    for code, (libelle, _) in PROFILS.items():
        colonne_texte, colonne_action = st.columns([4, 1])
        with colonne_texte:
            st.markdown(f"**{libelle}** — {DESCRIPTIONS_PROFIL[code]}")
        with colonne_action:
            if st.button("Choisir", key=f"choisir_{code}", use_container_width=True):
                depot_identites().attribuer(sujet, code, source="demo")
                st.rerun()
```

Avec, en tête de fichier :

```python
DESCRIPTIONS_PROFIL = {
    "admin": "accès complet aux 8 outils — recommandé pour un essai complet",
    "commercial": "8 outils, marges et notes confidentielles accessibles",
    "support": "8 outils, mais marges et prix d'achat hors périmètre",
    "dev": "4 outils documentaires, ni génération ni interrogation de la base",
}
```

- [ ] **Step 3: Ajouter le changement de profil**

En bas de la barre latérale :

```python
    with st.expander("Changer de profil"):
        st.caption("Mode démonstration : la bascule est journalisée comme tout appel.")
        nouveau = st.selectbox(
            "Profil", list(PROFILS), format_func=lambda p: PROFILS[p][0], key="bascule"
        )
        if st.button("Appliquer", key="btn_bascule") and nouveau != profil:
            depot_identites().attribuer(sujet, nouveau, source="demo")
            st.rerun()
```

Le `st.session_state.pop("_tools", None)` disparaît : il n'y a plus de cache de tools issu de
`tools/list` à invalider. `tools_accordes(profil)` est recalculé à chaque script Streamlit à
partir du nouveau `profil`, sans état à purger.

- [ ] **Step 4: Créer la fabrique de dépôt et le calcul des droits**

```python
# front/depot.py
"""Choisit l'implémentation du dépôt d'identités selon l'environnement, et calcule les
droits d'un profil depuis la matrice figée dans l'image.

Ce module ne parle jamais au serveur MCP : la matrice est un fichier en lecture seule,
identique pour les deux services (§5 de la conception GCP). Calculer les droits ici plutôt
que via `tools/list` est une décision délibérée (revue de la Task 4) : depuis que le
périmètre est résolu par requête, `tools/list` renvoie les 8 tools à tout appelant, et ne
dit donc plus rien sur ce qu'un profil PEUT appeler.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from gouvernance.modeles import CodeTool, charger_matrice
from gouvernance.perimetre import Perimetre

RACINE = Path(__file__).resolve().parent.parent


@functools.lru_cache(maxsize=1)
def _matrice():
    return charger_matrice(RACINE / "gouvernance" / "gouvernance.db")


def tools_accordes(profil: str) -> frozenset[str]:
    """Les tools que ce profil peut appeler, lus dans la matrice — jamais dans `tools/list`."""
    perimetre = Perimetre(profil, _matrice())
    return frozenset(t for t in CodeTool.__args__ if perimetre.peut_appeler(t))


@functools.lru_cache(maxsize=1)
def depot_identites():
    if os.environ.get("SORABEL_DEPOT") == "firestore":
        from google.cloud import firestore

        from gouvernance.identites_firestore import DepotIdentitesFirestore

        return DepotIdentitesFirestore(
            firestore.Client(), profils_valides=frozenset(_matrice().profils)
        )

    from gouvernance.identites import DepotIdentitesSqlite

    return DepotIdentitesSqlite(RACINE / "gouvernance" / "gouvernance.db")
```

**Attention** : `CodeTool.__args__` suppose que `CodeTool` reste un `Literal[...]` dans
`gouvernance/modeles.py` (vérifié à la Task 1 — c'est le cas). Si ce type change de forme,
adapter l'énumération en conséquence plutôt que de coder les 8 noms en dur ici : une seule
source de vérité pour la liste des tools.

- [ ] **Step 5: Vérifier à la main en local**

```bash
SORABEL_TRANSPORT=http SORABEL_URL_PUBLIQUE=http://localhost:8080 \
  SORABEL_OIDC_ISSUER=https://securetoken.google.com/test \
  SORABEL_OIDC_AUDIENCE=test SORABEL_OIDC_JWKS=https://example.invalid/jwks \
  python -m mcp_server.serveur &
streamlit run front/app_client.py
```
Expected: sans en-tête IAP, la page annonce une session non authentifiée. Le parcours complet se vérifie après déploiement (Task 11).

- [ ] **Step 6: Suite complète et commit**

```bash
python -m pytest -q
git add front/app_client.py front/depot.py
git commit -m "feat(front): page d'inscription de demonstration et changement de profil"
```

---

### Task 9: Image conteneur

**Files:**
- Create: `Dockerfile`, `.dockerignore`

**Interfaces:**
- Consumes: `scripts/ingerer.py`, `scripts/indexer.py`, `scripts/seed_gouvernance.py`.
- Produces: une image dont l'entrypoint est surchargeable — `python -m mcp_server.serveur` ou `streamlit run front/app_client.py`.

- [ ] **Step 1: Écrire `.dockerignore`**

```
.venv/
.git/
.claude/
docs/
tests/
logs/
data/canonique/
data/chroma/
__pycache__/
*.pyc
.env
```

- [ ] **Step 2: Écrire le `Dockerfile`**

```dockerfile
# Étape 1 : construire l'index. Le corpus n'est lu QU'ICI — il ne part pas en production.
FROM python:3.12-slim AS index

RUN pip install --no-cache-dir uv
WORKDIR /build

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY sorabel_rag/ sorabel_rag/
COPY sorabel_llm/ sorabel_llm/
COPY gouvernance/ gouvernance/
COPY scripts/ scripts/
COPY data/corpus/ data/corpus/
COPY data/sorabel.db data/sorabel.db

# La clé d'embeddings est montée par Cloud Build depuis Secret Manager et ne subsiste
# dans aucune couche de l'image finale.
RUN --mount=type=secret,id=azure_embedding_key \
    AZURE_EMBEDDING_API_KEY="$(cat /run/secrets/azure_embedding_key)" \
    .venv/bin/python scripts/seed_gouvernance.py \
 && AZURE_EMBEDDING_API_KEY="$(cat /run/secrets/azure_embedding_key)" \
    .venv/bin/python scripts/ingerer.py \
 && AZURE_EMBEDDING_API_KEY="$(cat /run/secrets/azure_embedding_key)" \
    .venv/bin/python scripts/indexer.py

# Étape 2 : l'image servie. Ni corpus, ni outils de construction.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    SORABEL_JOURNAL=stdout \
    SORABEL_TRANSPORT=http \
    SORABEL_DEPOT=firestore \
    PATH="/app/.venv/bin:$PATH"

COPY --from=index /build/.venv /app/.venv
COPY --from=index /build/data/canonique/ data/canonique/
COPY --from=index /build/data/chroma/ data/chroma/
COPY --from=index /build/data/sorabel.db data/sorabel.db
COPY --from=index /build/gouvernance/gouvernance.db gouvernance/gouvernance.db

COPY sorabel_rag/ sorabel_rag/
COPY sorabel_sql/ sorabel_sql/
COPY sorabel_llm/ sorabel_llm/
COPY gouvernance/ gouvernance/
COPY mcp_server/ mcp_server/
COPY front/ front/
COPY .streamlit/ .streamlit/

EXPOSE 8080
CMD ["python", "-m", "mcp_server.serveur"]
```

- [ ] **Step 3: Construire et mesurer**

```bash
echo "$AZURE_EMBEDDING_API_KEY" > /tmp/cle
DOCKER_BUILDKIT=1 docker build --secret id=azure_embedding_key,src=/tmp/cle -t sorabel:local .
rm /tmp/cle
docker images sorabel:local --format "{{.Size}}"
```
Expected: une taille de l'ordre de 500 Mo. Au-delà de 800 Mo, chercher ce que `.dockerignore` a laissé passer.

- [ ] **Step 4: Vérifier que le corpus est absent et que la clé n'a pas fuité**

```bash
docker run --rm sorabel:local ls data/
docker history --no-trunc sorabel:local | grep -ci "AZURE_EMBEDDING_API_KEY" || echo "aucune fuite"
```
Expected: `data/` contient `canonique`, `chroma`, `sorabel.db` mais **pas** `corpus` ; et `aucune fuite`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat(deploiement): image a deux etapes, corpus exclu de la production"
```

---

### Task 10: Chaîne CI/CD

**Files:**
- Create: `cloudbuild.yaml`

**Interfaces:**
- Consumes: l'image de Task 9.
- Produces: le déploiement des deux services Cloud Run.

- [ ] **Step 1: Écrire `cloudbuild.yaml`**

```yaml
# Déclenché sur push vers main. Les tests sont une barrière : leur échec arrête tout.
steps:
  - id: tests
    name: python:3.12-slim
    entrypoint: bash
    args:
      - -c
      - pip install --no-cache-dir uv && uv sync --frozen && uv run pytest -q

  - id: build
    name: gcr.io/cloud-builders/docker
    entrypoint: bash
    secretEnv: [AZURE_EMBEDDING_API_KEY]
    args:
      - -c
      - |
        echo "$$AZURE_EMBEDDING_API_KEY" > /workspace/cle
        DOCKER_BUILDKIT=1 docker build \
          --secret id=azure_embedding_key,src=/workspace/cle \
          -t "$_IMAGE:$SHORT_SHA" -t "$_IMAGE:latest" .
        rm /workspace/cle

  - id: push
    name: gcr.io/cloud-builders/docker
    args: [push, --all-tags, "$_IMAGE"]

  - id: deploy-mcp
    name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: gcloud
    args:
      - run
      - deploy
      - sorabel-mcp
      - --image=$_IMAGE:$SHORT_SHA
      - --region=$_REGION
      - --service-account=sorabel-mcp@$PROJECT_ID.iam.gserviceaccount.com
      - --command=python
      - --args=-m,mcp_server.serveur
      - --set-env-vars=SORABEL_TRANSPORT=http,SORABEL_JOURNAL=stdout,SORABEL_DEPOT=firestore
      - --set-secrets=AZURE_OPENAI_API_KEY=azure-openai-key:latest
      - --min-instances=0
      - --max-instances=4

  - id: deploy-front
    name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: gcloud
    args:
      - run
      - deploy
      - sorabel-front
      - --image=$_IMAGE:$SHORT_SHA
      - --region=$_REGION
      - --service-account=sorabel-front@$PROJECT_ID.iam.gserviceaccount.com
      - --command=streamlit
      - --args=run,front/app_client.py,--server.port=8080,--server.address=0.0.0.0
      - --set-env-vars=SORABEL_DEPOT=firestore,SORABEL_JOURNAL=stdout
      - --session-affinity
      - --min-instances=0
      - --max-instances=2

availableSecrets:
  secretManager:
    - versionName: projects/$PROJECT_ID/secrets/azure-embedding-key/versions/latest
      env: AZURE_EMBEDDING_API_KEY

substitutions:
  _REGION: europe-west1
  _IMAGE: europe-west1-docker.pkg.dev/${PROJECT_ID}/sorabel/gateway

options:
  logging: CLOUD_LOGGING_ONLY
```

- [ ] **Step 2: Valider la syntaxe**

Run: `gcloud builds submit --config cloudbuild.yaml --no-source --dry-run` *(ou, à défaut, `python -c "import yaml,sys; yaml.safe_load(open('cloudbuild.yaml'))"`)*
Expected: aucune erreur de syntaxe

- [ ] **Step 3: Commit**

```bash
git add cloudbuild.yaml
git commit -m "feat(ci): chaine Cloud Build, tests en barriere de deploiement"
```

---

### Task 11: Provisionnement GCP et document d'exploitation

**Files:**
- Create: `docs/EXPLOITATION.md`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: la documentation d'exploitation ; aucune interface de code.

- [ ] **Step 1: Écrire les commandes de provisionnement dans `docs/EXPLOITATION.md`**

Le document contient, dans l'ordre : création du projet et activation des API (`run`, `cloudbuild`, `artifactregistry`, `secretmanager`, `firestore`, `iap`) ; création du dépôt Artifact Registry ; création de la base Firestore en mode natif ; création des deux comptes de service avec **exactement** les droits du tableau §7 de la spec ; création des secrets ; création du client OAuth et activation d'IAP sur `sorabel-front` ; déclencheur Cloud Build sur `main` ; enfin les variables `SORABEL_IAP_AUDIENCE`, `SORABEL_OIDC_ISSUER`, `SORABEL_OIDC_AUDIENCE`, `SORABEL_OIDC_JWKS`, `SORABEL_URL_MCP`, `SORABEL_URL_PUBLIQUE`.

- [ ] **Step 2: Y ajouter la métrique de refus**

```bash
gcloud logging metrics create sorabel_refus \
  --description="Appels refuses par la matrice d'acces" \
  --log-filter='resource.type="cloud_run_revision" jsonPayload.autorise=false'
```

- [ ] **Step 3: Y ajouter le parcours de démonstration**

Reprendre les 9 critères d'acceptation du §12 de la spec sous forme de liste à cocher, en y intégrant ces commandes :

```bash
# Critère 6 — le serveur exige un jeton et publie ses métadonnées
MCP="$(gcloud run services describe sorabel-mcp --region=europe-west1 --format='value(status.url)')"

curl -s -i "$MCP/mcp" | head -3
# Attendu : HTTP/2 401 puis
#   www-authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"

curl -s "$MCP/.well-known/oauth-protected-resource" | python -m json.tool
# Attendu : "authorization_servers" contenant l'émetteur Google Identity Platform

# Critère 7 — un jeton valide ouvre search_docs, et le profil dev se voit refuser ask_database
JETON="<jeton obtenu par le client de démonstration>"
curl -s -X POST "$MCP/mcp" \
  -H "Authorization: Bearer $JETON" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"search_docs","arguments":{"requete":"REF-8842","k":3}}}'
# Attendu : "statut": "ok" avec des extraits

curl -s -X POST "$MCP/mcp" \
  -H "Authorization: Bearer $JETON" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"ask_database","arguments":{"question":"combien de commandes ?"}}}'
# Attendu (profil dev) : "statut": "non_autorise"

# Critère 5 — le refus est journalisé
gcloud logging read \
  'resource.type="cloud_run_revision" jsonPayload.autorise=false' \
  --limit=5 --format='value(jsonPayload.profil,jsonPayload.tool,jsonPayload.motif)'
```

- [ ] **Step 4: Commit**

```bash
git add docs/EXPLOITATION.md
git commit -m "docs: provisionnement GCP et exploitation de la vitrine"
```

---

### Task 12: Mettre la documentation en accord avec le code

**Files:**
- Modify: `docs/DOSSIER_TECHNIQUE.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: l'état réel après Task 11.
- Produces: rien.

- [ ] **Step 1: Corriger le dossier technique**

Quatre passages deviennent faux et doivent être réécrits, sans en laisser subsister de trace contradictoire :

1. §1 — « un processus serveur ne sert qu'un seul profil » : vrai en stdio, faux en HTTP.
2. §4 — « `tools/list` filtré **est** l'intercepteur » : remplacé par le contrôle par requête.
3. §7 — ajouter le dépôt d'identités et Firestore au tableau des trois niveaux d'application.
4. §12 — retirer la lacune « le journal ne trace que les appels autorisés », désormais comblée.

Ajouter une section « Déploiement » renvoyant à `docs/EXPLOITATION.md`.

- [ ] **Step 2: Corriger `CLAUDE.md`**

La contrainte « matrice appliquée à l'entrée du serveur et dans chaque tool » devient : « appliquée par le middleware d'authentification **et** à chaque appel de tool ; en stdio, le filtrage à l'enregistrement subsiste ». Ajouter `SORABEL_TRANSPORT`, `SORABEL_JOURNAL` et `SORABEL_DEPOT` à la liste des variables.

- [ ] **Step 3: Vérifier qu'aucune contradiction ne subsiste**

Run: `grep -rn "structurellement inappelable\|tools/list filtré\|un seul profil" docs/ CLAUDE.md`
Expected: aucune occurrence hors contexte historique de `docs/superpowers/`

- [ ] **Step 4: Suite complète et commit**

```bash
python -m pytest -q
git add docs/DOSSIER_TECHNIQUE.md CLAUDE.md
git commit -m "docs: accorder le dossier technique au deploiement HTTP"
```
