# Mise en production de la Sorabel Data Gateway sur GCP — conception

**Date** : 7 septembre 2026
**Objectif** : une vitrine de soutenance — deux URL publiques, durables quelques semaines,
sous 5 €/mois hors appels LLM.

## 1. Ce qu'on livre

Deux surfaces exposées sur Internet :

1. **`sorabel-front`** — le poste de travail Streamlit, ouvert par le jury dans un navigateur.
2. **`sorabel-mcp`** — le serveur MCP en HTTP streamable, auquel un client MCP tiers peut se
   connecter avec un jeton OAuth 2.1.

Hors périmètre, explicitement : haute disponibilité, sauvegardes, plusieurs environnements,
astreinte, migration de l'inférence vers Vertex AI, évaluation E6.

## 2. Architecture

```
   Jury / navigateur                     Client MCP tiers
          │ HTTPS                                │ HTTPS + Bearer JWT
   ┌──────▼──────────────────┐                   │
   │ Identity-Aware Proxy    │                   │
   │ (authentifie, signe)    │                   │
   └──────┬──────────────────┘                   │
          │ + X-Goog-IAP-JWT-Assertion           │
┌─────────▼───────────────┐          ┌───────────▼──────────────────────────┐
│ Cloud Run sorabel-front │─────────►│ Cloud Run sorabel-mcp                │
│ Streamlit               │ MCP HTTP │ /.well-known/oauth-protected-resource│
│ min 0 / max 2           │ + jeton  │ /mcp  (streamable HTTP)              │
│ SA sorabel-front@       │  relayé  │ min 0 / max 4 · SA sorabel-mcp@      │
│ session-affinity ON     │          └───┬───────────┬──────────┬───────────┘
└────────┬────────────────┘              │           │          │
         │ lecture + écriture ───────────┼───────────┤          │
         │ des identités                 │           │          │
                         ┌───────────────▼──┐  ┌─────▼──────┐  ┌▼─────────────┐
                         │ Dans l'image     │  │ Firestore  │  │ Google       │
                         │ (lecture seule)  │  │ identites  │  │ Identity /   │
                         │ canonique, chroma│  │            │  │ IAP — JWKS   │
                         │ bm25, sorabel.db │  └────────────┘  └──────────────┘
                         │ matrice figée    │   ↑ mcp : lecture seule
                         └──────────────────┘   ↑ front : lecture + écriture

                                               ┌────────────────────────────┐
                                               │ Azure AI Foundry           │
   Journal : stdout JSON → Cloud Logging       │ clés via Secret Manager    │
   CI : push main → Cloud Build                └────────────────────────────┘
```

**Région** : `europe-west1`. **Image unique, deux entrypoints** : une seule construction, un
seul artefact à tracer, deux services qui la démarrent différemment.

## 3. Authentification

### 3.1 Le serveur MCP est un Resource Server

Conformément à la révision de juin 2025 de la spécification MCP, le serveur ne délivre aucun
jeton : il les valide et délègue leur émission à Google Identity Platform.

Le SDK installé (`mcp>=1.20,<2`) fournit tout le nécessaire, vérifié :

- `AuthSettings(issuer_url, resource_server_url, required_scopes)` — le SDK sert lui-même
  `/.well-known/oauth-protected-resource` (RFC 9728) et répond `401` avec l'en-tête
  `WWW-Authenticate` attendu.
- `TokenVerifier.verify_token(token) -> AccessToken | None` — le seul point à écrire.
- `get_access_token()` dans `mcp.server.auth.middleware.auth_context` — donne le jeton
  courant à l'intérieur d'un tool.
- `FastMCP.run(transport="streamable-http")`.

Aucune dépendance nouvelle côté MCP.

**À écrire** : `mcp_server/authentification.py`, portant un `VerificateurJeton` qui valide
signature (via JWKS mis en cache), `iss`, `aud` et expiration, puis retourne un `AccessToken`
dont `subject` est le `sub` de l'émetteur.

Le vérificateur accepte **deux émetteurs** :

| Émetteur | Qui l'utilise | `aud` attendu |
|---|---|---|
| Identity-Aware Proxy | le front, qui relaie l'assertion | l'identifiant de la ressource IAP |
| Google Identity Platform | les clients MCP tiers | le `client_id` du client déclaré |

### 3.2 Le front ne manipule aucun jeton

Le service front est placé derrière **IAP**. Google authentifie la personne avant que la
requête n'atteigne Streamlit et injecte un en-tête signé `X-Goog-IAP-JWT-Assertion`. Le front
**recopie cet en-tête** dans ses appels au serveur MCP, qui le valide comme n'importe quel
jeton.

C'est le choix qui supprime le risque plutôt que de le contourner : `st.login()` n'expose pas
de manière garantie le jeton brut, et on n'écrit pas de flux OIDC à la main.

### 3.3 Du sujet au profil

`resoudre_profil()` cesse de lire `SORABEL_PROFIL`. Le profil vient de la table `identites`,
interrogée avec le `sub` du jeton validé.

**Un sujet inconnu du dépôt d'identités n'obtient jamais de profil par défaut.** Les deux
surfaces traitent ce cas différemment, et c'est voulu :

- **Le serveur MCP** répond `{"statut": "non_autorise"}` — il n'inscrit personne.
- **Le front** n'appelle pas le serveur : il affiche la page d'inscription (§6), obtient un
  profil, puis reprend le cours normal.

`required_scopes` est vide : un jeton valide, émis par un émetteur accepté et destiné à cette
ressource, suffit. Les droits ne viennent pas des portées OAuth mais de la matrice — deux
systèmes d'autorisation superposés se contrediraient tôt ou tard.

`SORABEL_PROFIL` reste accepté **uniquement** en transport stdio (développement local, tests,
`scripts/mcp_client.py` en mode local). Le mode HTTP l'ignore, sans exception.

## 4. Le périmètre devient par requête

C'est le changement structurel du chantier, et il faut le documenter plutôt que le subir.

**Aujourd'hui** : un processus sert un profil, `enregistrer_tools()` n'enregistre que les
tools autorisés, et « `tools/list` filtré **est** l'intercepteur d'entrée ».

**En HTTP multi-utilisateurs** : le processus ne connaît plus le profil au démarrage. Donc :

- les **8 tools sont enregistrés** inconditionnellement ;
- le décorateur `_avec_journalisation` devient `_gouverne` et, à **chaque appel** : résout le
  périmètre depuis le jeton, vérifie `peut_appeler()`, journalise, et renvoie
  `{"statut": "non_autorise"}` si le droit manque ;
- `enregistrer_tools()` ne reçoit plus un `Perimetre` mais un **résolveur** de périmètre.

**Ce qu'on garde** : E4 exige la matrice « à l'entrée du serveur *et* dans chaque tool ». Elle
l'est toujours — l'entrée est désormais le middleware d'authentification.

**Ce qu'on perd** : la propriété « structurellement inappelable ». À corriger dans
`docs/DOSSIER_TECHNIQUE.md` (§1, §4, §7) et `CLAUDE.md`, qui l'affirment aujourd'hui.

**Ce qu'on gagne** : la lacune du §12 — « le journal ne trace pas les refus » — se referme.
Un appel refusé devient un événement journalisé avec `autorise=False`.

Le décorateur étant déjà le point de passage unique, le changement tient en un seul endroit.

## 5. L'état

| Donnée | Emplacement | Écriture |
|---|---|---|
| `data/canonique/`, `data/chroma/`, `bm25.pkl` | image, lecture seule | jamais |
| `data/sorabel.db` | image, lecture seule (`mode=ro`) | jamais |
| Matrice : profils, tools, collections, tables, colonnes interdites | image, lecture seule | jamais |
| **Identités** (sujet → profil) | **Firestore**, mode natif | inscription, changement de profil |
| Journal des appels | `stdout` → Cloud Logging | à chaque appel |

Le corpus source (320 PDF, 80 Markdown, 90 HTML) **ne part pas en production** : il n'est lu
que pendant la construction de l'image.

**Contrat `DepotIdentites`**, duck-typé sur le patron de `Perimetre` :

```python
depot.profil_de(sujet: str) -> str | None
depot.attribuer(sujet: str, profil: str, source: str) -> None
```

Deux implémentations : `DepotIdentitesSqlite` (développement, tests — la table `identites`
existe déjà dans `gouvernance/schema.sql`) et `DepotIdentitesFirestore` (production). Les
tests continuent de tourner sans réseau ni émulateur.

Firestore : collection `identites`, document par sujet, champs `profil` et `source`. L'offre
gratuite quotidienne couvre très largement l'usage d'une vitrine ; coût attendu 0 €.

## 6. Page d'accueil et inscription de démonstration

À l'ouverture, IAP a déjà établi **qui** est la personne. Reste à savoir **quel profil** lui
est attribué :

```
sub présent dans identites ? ─oui─► l'écran métier, profil appliqué
                             └─non─► page d'accueil « Créez votre accès de démonstration »
                                     choix : support · commercial · dev · admin
                                     → depot.attribuer(sub, profil, source="demo")
                                     → journalisé
```

Un bouton **« Changer de profil »** reste accessible en permanence : il réécrit la ligne et
journalise le changement. Le jury prend `admin` pour un essai complet, puis bascule sur
`support` pour voir la matrice mordre.

**Ce qui rend la chose défendable** : l'identité est prouvée par IAP et n'est jamais choisie ;
seule l'attribution du profil est en libre-service, elle est **enregistrée** et **auditable**,
et le serveur continue de dériver le profil du dépôt d'identités — jamais d'une déclaration
de l'appelant.

**L'honnêteté est explicite** : un bandeau « mode démonstration — en exploitation réelle, les
profils sont attribués par un administrateur » figure sur la page d'accueil, et la colonne
`source` distingue `demo` de `annuaire`. Mieux vaut l'annoncer que se le faire demander.

## 7. Secrets et moindre privilège

Deux comptes de service, deux périmètres :

| Secret / droit | `sorabel-mcp@` | `sorabel-front@` |
|---|---|---|
| `AZURE_OPENAI_API_KEY`, endpoint, déploiements | ✅ | ❌ |
| Lecture Firestore `identites` | ✅ | ✅ |
| Écriture Firestore `identites` | ❌ | ✅ |
| Écriture de journal (`logging.logWriter`) | ✅ | ✅ |
| Invocation de `sorabel-mcp` (`run.invoker`) | — | ✅ |

Le front n'a **aucun** accès aux clés d'inférence : il ne parle qu'au serveur MCP. Le serveur
MCP ne peut pas écrire d'identités : seule l'inscription le fait, côté front.

`sorabel-mcp` n'accepte pas les appels non authentifiés au niveau IAM, mais son
authentification applicative reste la barrière qui compte pour les clients MCP tiers.

## 8. Journal et observabilité

`gouvernance/journal.py` écrit sur `stdout` une ligne JSON par appel, au format que Cloud
Logging indexe sans agent : les champs existants (`profil`, `tool`, `statut`, `sql`,
`n_lignes`, `duree_ms`, `motif`) deviennent interrogeables, et `autorise` cesse d'être
toujours vrai.

Une **métrique fondée sur les logs** compte les `statut = non_autorise` par profil. C'est la
pièce la plus parlante du dossier de gouvernance, et elle se construit en deux clics.

L'écriture dans `logs/appels.jsonl` reste le comportement par défaut hors production, pour ne
pas casser les tests ni le développement local. Le choix se fait sur une variable
d'environnement.

## 9. Construction et déploiement

**`Dockerfile`, deux étapes.** L'étape de construction embarque le corpus et exécute
`scripts/ingerer.py` puis `scripts/indexer.py` — elle a besoin de la clé d'embeddings, fournie
par Secret Manager pendant le build. L'étape finale ne copie que les sorties et le code.

Image attendue : **~500 Mo**, mesurée à partir de l'environnement local ramené à 0,52 Go après
retrait de `sentence-transformers` (commit `337ee18`).

**`cloudbuild.yaml`, sur push vers `main`** :

```
pytest -q            ← 117 tests, entièrement bouchonnés, aucun secret requis
docker build         ← ingestion + indexation
push Artifact Registry
gcloud run deploy sorabel-mcp
gcloud run deploy sorabel-front
```

L'échec des tests interrompt le déploiement. Durée attendue ~5 minutes, dans les 2 500 minutes
gratuites mensuelles.

**Paramètres Cloud Run notables** : `--session-affinity` sur le front (Streamlit maintient un
WebSocket), `--min-instances=0` par défaut, `--cpu-boost` au démarrage.

## 10. Coûts

| Poste | Estimation mensuelle |
|---|---|
| Cloud Run (deux services, trafic de vitrine) | 0 € — dans l'offre gratuite |
| Artifact Registry (~500 Mo) | ~0,05 € |
| Secret Manager (4 secrets) | ~0,25 € |
| Firestore | 0 € — offre gratuite |
| Cloud Logging | 0 € — offre gratuite (50 Gio) |
| Cloud Build | 0 € — offre gratuite |
| **Total GCP** | **< 1 €/mois** |
| Appels LLM | facturés par Azure à l'usage |
| Option jour J : `--min-instances=1` pendant 24 h | ~0,40 € |

## 11. Risques et parades

| Risque | Parade retenue |
|---|---|
| Streamlit n'expose pas le jeton brut | Écarté par conception : IAP fournit l'assertion signée, le front la relaie sans la manipuler |
| Google Identity ne fait pas d'enregistrement dynamique de clients | Un `client_id` de démonstration est déclaré à l'avance et `scripts/mcp_client.py` devient un client MCP HTTP déjà configuré. Le serveur étant un Resource Server, changer d'émetteur ne coûte qu'une URL de configuration |
| Démarrage à froid | Image à 500 Mo (~3 s) ; ping Cloud Scheduler toutes les 5 min le jour J ; `--min-instances=1` en garantie absolue |
| La clé d'embeddings est requise au build | Cloud Build lit Secret Manager ; l'image finale ne la contient pas |
| Le corpus change | Reconstruire l'image. Un job Cloud Run de réindexation est possible plus tard, hors périmètre ici |

## 12. Critères d'acceptation

1. Ouvrir l'URL du front sans compte Google → IAP refuse l'accès.
2. Ouvrir avec un compte autorisé inconnu → page d'accueil d'inscription, choix du profil,
   puis l'écran métier.
3. En `admin` : les 8 tools répondent, les 4 thèmes du menu sont présents.
4. Basculer en `support` : « Périmètre accessible » n'affiche plus `prix_achat_ht`,
   `marge_pct`, `ventes.marge_ht` ; une question sur les marges renvoie `non_autorise` avec le
   SQL rejeté visible.
5. Cloud Logging contient une entrée pour cet appel, avec `autorise=false`.
6. `curl` sur `/mcp` sans jeton → `401` avec `WWW-Authenticate` désignant les métadonnées ;
   `curl` sur `/.well-known/oauth-protected-resource` → l'émetteur attendu.
7. Un client MCP configuré avec le `client_id` de démonstration obtient un jeton, appelle
   `search_docs`, et se voit refuser `ask_database` s'il porte le profil `dev`.
8. Les 117 tests existants passent toujours, sans réseau.
9. `git push` sur `main` déclenche le déploiement des deux services.

## 13. Documents à mettre à jour

`docs/DOSSIER_TECHNIQUE.md` (§1 transport, §4 périmètre par requête, §7 identités et
Firestore, §10 commandes, §12 lacune du journal refermée) et `CLAUDE.md` (contrainte
« matrice appliquée à l'entrée » à reformuler). Ne pas laisser cohabiter deux descriptions du
transport.
