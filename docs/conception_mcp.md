# Dossier de conception — Chantier 3 : exposition MCP et matrice d'accès

> Sorabel Data Gateway. Périmètre : le catalogue de tools, la gouvernance des accès et la
> journalisation (exigences E4, E5). Les chantiers 1 et 2 sont traités dans
> `conception_rag.md` et `conception_sql.md`.

## 0. Ce que la Gateway expose, et à qui

Un serveur MCP unique remplace les bricolages gelés par la DSI.

### Un seul client, quatre profils

`scripts/mcp_client.py` est un **client unique** qui prend le profil en argument
(`--profil support`). **Il n'y a pas quatre clients** : il y a un client et quatre jeux de
droits.

Ce n'est pas une commodité de démonstration, c'est ce qui rend le contraste **prouvable** :
même code client, même serveur, même séquence d'appels — seul le profil change. Avec quatre
clients différents, on ne pourrait pas écarter l'hypothèse que la différence de réponse vient
du client plutôt que de la matrice.

Corollaire assumé : **le profil est déclaré par l'appelant**, ce qui n'est pas une
authentification. Voir les points ouverts.

### Les quatre profils

Un profil est un **jeu de droits**, pas un logiciel. La colonne « métier modélisé » rappelle
seulement quelle situation de travail chaque jeu de droits reproduit — ce sont les usages
internes cités par le brief, pas des applications à développer.

| Profil | Métier modélisé | Besoin |
|---|---|---|
| `support` | technicien du support client | répondre à un client : documentation, stock, statut de commande |
| `commercial` | commercial en clientèle | analyse chiffrée, marges, négociation |
| `dev` | développeur intégrant la Gateway | comprendre le corpus et l'API, **sans lire les données de production** |
| `admin` | exploitation | accès total, diagnostic, démonstration du contraste |

## 1. Le catalogue : huit tools, deux niveaux

### Pourquoi le RAG est exposé à deux niveaux

`answer_question` fait `search_docs` **plus** une génération. Exposer les deux n'est pas une
redondance : ce sont deux contrats différents.

| | `answer_question` | `search_docs` + `get_document` |
|---|---|---|
| Rend | une réponse rédigée + sources | des extraits bruts + scores + métadonnées |
| Coûte | un appel LLM | zéro appel LLM |
| Pour quel profil | `support`, `commercial` | `dev` |
| Défaillance | le LLM reformule mal | aucune, le texte est celui du corpus |

Le profil `dev` veut le passage exact d'une notice, pas une prose de LLM qui la
paraphrase. Il veut aussi enchaîner : chercher, regarder les scores, ouvrir le document
complet. Le test d'acceptance le formule ainsi — « les briques du RAG fonctionnent
séparément ».

Même raisonnement côté données : `ask_database` (génératif, longue traîne) coexiste avec
`check_stock` et `order_status` (figés, fiables, sans LLM), et avec `get_schema` qui n'est ni
l'un ni l'autre.

### Catalogue complet

| Tool | Entrées | Sorties | Garanties |
|---|---|---|---|
| `answer_question` | `question`, `collections?` | `statut`, `reponse`, `sources[]` | Cite toujours (E1) · refuse sous le seuil sans appeler le LLM |
| `search_docs` | `requete`, `k?`, `type_document?`, `inclure_versions_anciennes?` | `resultats[]` | Hybride + rerank · réf exacte en tête (E2) · aucune génération |
| `get_document` | `doc_id` \| (`reference` + `version?`) | document complet | Version courante par défaut · sert le canonique |
| `list_sources` | `type_document?`, `reference?` | inventaire + versions | Reflète l'index et le périmètre du profil |
| `ask_database` | `question` | `statut`, `sql`, `colonnes`, `lignes` | Lecture seule (4 barrières) · SQL renvoyé (E3) |
| `get_schema` | — | tables, colonnes commentées, valeurs types | Reflète exactement le périmètre du profil |
| `check_stock` | `ref` | stock par entrepôt + alerte réappro | Requête figée, paramètre lié, zéro LLM |
| `order_status` | `order_id` | statut, date, montant | Requête figée, paramètre lié, zéro LLM |

### Décrire les tools pour que le LLM du client choisisse le bon

Le client n'appelle pas nos tools : **son LLM les choisit** à partir de leur description.
Une description vague produit de mauvais choix, et le coupable est invisible côté serveur.

Trois règles de rédaction :

1. **Dire quand ne PAS l'utiliser.** « `search_docs` — recherche documentaire hybride.
   *N'utilisez pas ce tool pour obtenir une réponse rédigée : voyez `answer_question`.* »
   Sans cette phrase, un LLM appelle `search_docs` puis reformule lui-même, en perdant les
   citations construites par le code.
2. **Distinguer les tools proches par leur déclencheur, pas par leur mécanique.**
   `check_stock` : « quand la question porte sur **une référence précise** ». `ask_database` :
   « quand la question demande un **calcul ou un agrégat** ». Un LLM ne sait pas ce qu'est un
   « tool figé » ; il sait reconnaître une forme de question.
3. **Documenter les statuts de retour dans la description.** Un client qui sait que
   `hors_corpus` existe le gère ; un client qui l'apprend à l'exécution l'affiche comme une
   réponse.

## 2. La matrice d'accès

### Les collections ne sont pas les quatre dossiers

Le corpus **porte son propre marqueur de confidentialité**, vérifié sur les 80 notes :

| Sous-type de note | Volume | Mention « Diffusion restreinte » |
|---|---|---|
| `politique_tarifaire` | 16 | **16/16** |
| `reunion_achat` | 16 | 0/16 |
| `retour_terrain` | 16 | 0/16 |
| `logistique` | 16 | 0/16 |
| `alerte_qualite` | 16 | 0/16 |

Une note de politique tarifaire dit : *« La marge cible reste fixée par la direction
commerciale ; la référence REF-4590 passe en revue au prochain comité. Diffusion
restreinte. »* La faire ressortir pour le profil `support` contournerait E5 **par la porte
du RAG** — le support n'aurait pas accès aux marges en SQL, mais les lirait en clair dans un
extrait documentaire.

Les comptes rendus de réunion achats (« négociation en cours avec Fixor : conditions de
remise sur volumes ») ne portent pas le marqueur mais relèvent de la même sensibilité
commerciale. Leur classement est une **décision métier assumée**, pas une lecture des
données.

D'où cinq collections, et non quatre :

| Collection | Contenu | Volume |
|---|---|---|
| `fiches` | fiches techniques | 150 |
| `notices` | notices d'installation | 80 |
| `sav` | procédures SAV | 90 |
| `notes_operationnelles` | alerte qualité, logistique, retour terrain | 48 |
| `notes_confidentielles` | politique tarifaire, réunion achats | 32 |

**Conséquence sur le chantier 1** : l'extracteur de notes doit produire deux métadonnées
supplémentaires — `sous_type` (tiré du nom de fichier, seul endroit où il figure : le
front-matter déclare `note_interne` pour les 80) et `diffusion_restreinte` (booléen, tiré du
corps). Sans elles, la matrice n'a rien sur quoi filtrer. C'est un manque identifié dans
l'implémentation actuelle.

### Matrice profil × tool

| Tool | `support` | `commercial` | `dev` | `admin` |
|---|:---:|:---:|:---:|:---:|
| `answer_question` | ✓ | ✓ | **✗** | ✓ |
| `search_docs` | ✓ | ✓ | ✓ | ✓ |
| `get_document` | ✓ | ✓ | ✓ | ✓ |
| `list_sources` | ✓ | ✓ | ✓ | ✓ |
| `ask_database` | ✓ *(restreint)* | ✓ | **✗** | ✓ |
| `get_schema` | ✓ | ✓ | ✓ | ✓ |
| `check_stock` | ✓ | ✓ | ✗ | ✓ |
| `order_status` | ✓ | ✓ | ✗ | ✓ |

Deux refus méritent une justification, parce qu'ils ne sont pas des oublis :

- **`dev` n'a pas `answer_question`.** Ce n'est pas une punition : c'est le cas d'usage cité
  par le brief : chercher sans générer. Lui donner le tool génératif l'inciterait
  à payer un appel LLM pour un besoin qui n'en demande pas.
- **`dev` n'a aucun accès aux données réelles.** Il a `get_schema` pour comprendre la forme
  des données, pas `ask_database` pour les lire. Un environnement de développement n'a pas à
  contenir les commandes des clients.

**`support` conserve `ask_database`** : sans lui, le test d'acceptance « profil support,
question sur les marges → refusée selon la matrice » ne pourrait pas s'exécuter. Le refus
doit se produire *dans* le tool, sur les colonnes, pas en amont sur le tool entier.

### Matrice profil × collections

| Collection | `support` | `commercial` | `dev` | `admin` |
|---|:---:|:---:|:---:|:---:|
| `fiches` | ✓ | ✓ | ✓ | ✓ |
| `notices` | ✓ | ✓ | ✓ | ✓ |
| `sav` | ✓ | ✓ | ✓ | ✓ |
| `notes_operationnelles` | ✓ | ✓ | ✗ | ✓ |
| `notes_confidentielles` | **✗** | ✓ | ✗ | ✓ |

Le filtre s'applique **dans le retrieval**, comme une condition Chroma supplémentaire — pas
en post-traitement des résultats. Un document non autorisé ne doit jamais entrer dans le
top-k, sans quoi il occuperait la place d'un document légitime et dégraderait la réponse
tout en étant invisible.

### Matrice profil × tables et colonnes

| | `support` | `commercial` | `dev` | `admin` |
|---|---|---|---|---|
| `produits` | ✓ **sauf** `prix_achat_ht`, `marge_pct` | ✓ | schéma seul | ✓ |
| `stocks` | ✓ | ✓ | schéma seul | ✓ |
| `clients` | ✓ | ✓ | schéma seul | ✓ |
| `commandes` | ✓ | ✓ | schéma seul | ✓ |
| `ventes` | ✓ **sauf** `marge_ht` | ✓ | schéma seul | ✓ |

Les trois colonnes sensibles de E5 sont exactement `produits.prix_achat_ht`,
`produits.marge_pct`, `ventes.marge_ht`. `produits.prix_vente_ht` est un prix public,
présent en clair sur les fiches techniques : le restreindre n'aurait aucun sens.

### Forme de la matrice : base de données + Pydantic + `Perimetre`

La matrice n'est pas une suite de `if profil == "support"` dispersés dans huit tools. Elle est
**stockée en base**, **validée par Pydantic au démarrage**, et **exposée aux tools par un seul
objet** : le `Perimetre`.

Trois couches, trois responsabilités.

#### Couche 1 — le stockage : `gouvernance.db`

Une base SQLite **distincte de `sorabel.db`**, dédiée à la gouvernance.

```sql
-- Référentiels
CREATE TABLE profils      (code TEXT PRIMARY KEY, libelle TEXT, actif INTEGER DEFAULT 1);
CREATE TABLE tools        (code TEXT PRIMARY KEY, description TEXT);
CREATE TABLE collections  (code TEXT PRIMARY KEY, libelle TEXT);

-- Droits : profil × tool
CREATE TABLE profil_tool (
  profil TEXT REFERENCES profils(code),
  tool   TEXT REFERENCES tools(code),
  PRIMARY KEY (profil, tool)
);

-- Droits : profil × collection documentaire
CREATE TABLE profil_collection (
  profil     TEXT REFERENCES profils(code),
  collection TEXT REFERENCES collections(code),
  PRIMARY KEY (profil, collection)
);

-- Droits : profil × table SQL, et exclusions de colonnes (E5)
CREATE TABLE profil_table (
  profil     TEXT REFERENCES profils(code),
  table_sql  TEXT,
  lecture_seule_schema INTEGER DEFAULT 0,  -- profil `dev` : schéma sans données
  PRIMARY KEY (profil, table_sql)
);
CREATE TABLE colonne_interdite (
  profil    TEXT REFERENCES profils(code),
  table_sql TEXT,
  colonne   TEXT,
  motif     TEXT,                          -- « colonne sensible E5 » → journalisable
  PRIMARY KEY (profil, table_sql, colonne)
);

-- Pont authentification → autorisation
CREATE TABLE identites (
  sujet  TEXT PRIMARY KEY,                 -- `sub` du jeton OAuth, ou nom de compte
  profil TEXT REFERENCES profils(code),
  source TEXT                              -- 'oauth' | 'env' | 'demo'
);
```

Ce que le stockage relationnel apporte face à un fichier plat :

| | Fichier YAML | Base de données |
|---|---|---|
| Intégrité | aucune — `notes_confidentielle` (faute de frappe) passe | **clés étrangères** : la ligne est rejetée à l'écriture |
| Audit | `git blame` | requêtable : « quels profils voient `marge_ht` ? » en une requête |
| Motif du refus | absent | colonne `motif`, directement journalisable |
| Évolution | réécriture manuelle | `INSERT` par script d'administration |

**Règle non négociable : le serveur MCP ouvre `gouvernance.db` en lecture seule**, exactement
comme `sorabel.db`. La matrice se modifie hors ligne, par un script d'administration séparé.
La Gateway n'écrit dans **aucune** base — c'est une propriété plus forte, et plus facile à
défendre, qu'une exception à expliquer.

#### Couche 2 — la validation : Pydantic au démarrage

Une base garantit l'intégrité *référentielle*, pas l'intégrité *métier*. Rien n'empêche
d'insérer un tool `answer_questionn` dans la table `tools`. Pydantic ferme cette porte :

```python
from typing import Literal
from pydantic import BaseModel, field_validator

CodeTool = Literal[
    "answer_question", "search_docs", "get_document", "list_sources",
    "ask_database", "get_schema", "check_stock", "order_status",
]
CodeCollection = Literal[
    "fiches", "notices", "sav", "notes_operationnelles", "notes_confidentielles",
]
TableSql = Literal["produits", "stocks", "clients", "commandes", "ventes"]


class DroitsProfil(BaseModel):
    code: str
    tools: frozenset[CodeTool]
    collections: frozenset[CodeCollection]
    tables: frozenset[TableSql]
    colonnes_interdites: dict[TableSql, frozenset[str]]

    @field_validator("colonnes_interdites")
    @classmethod
    def colonnes_sensibles_couvertes(cls, valeur, infos):
        """E5 : aucun profil hors `commercial`/`admin` ne peut voir les trois colonnes
        sensibles. La règle est vérifiée ici, pas espérée dans les données."""
        if infos.data.get("code") in ("commercial", "admin"):
            return valeur
        obligatoires = {
            "produits": {"prix_achat_ht", "marge_pct"},
            "ventes": {"marge_ht"},
        }
        for table, colonnes in obligatoires.items():
            if table in infos.data.get("tables", frozenset()):
                manquantes = colonnes - valeur.get(table, frozenset())
                if manquantes:
                    raise ValueError(f"E5 violée : {table}.{manquantes} non exclues")
        return valeur


class MatriceAcces(BaseModel):
    profils: dict[str, DroitsProfil]
```

Deux garanties que ça donne :

1. **Un code inconnu fait échouer le serveur au démarrage**, pas silencieusement à l'appel.
   Une faute de frappe dans `notes_confidentielles` ne peut pas ouvrir un accès par accident.
2. **E5 est vérifiée par un validateur**, pas seulement par les données. Si quelqu'un retire
   la ligne d'exclusion de `marge_ht` pour le profil support, **le serveur refuse de
   démarrer**. La règle du brief devient une invariante du code.

Le chargement se fait **une fois au démarrage**, en mémoire. Aucune requête à
`gouvernance.db` dans le chemin d'un appel : la matrice est petite et ne change pas en cours
d'exécution.

#### Couche 3 — l'usage : l'objet `Perimetre`

Les huit tools ne lisent ni la base ni le modèle Pydantic. Ils reçoivent un `Perimetre`,
construit **une fois par appel**, et lui posent des questions :

```python
class Perimetre:
    """Les droits d'un profil, sous la forme que les tools consomment."""

    def __init__(self, profil: str, matrice: MatriceAcces):
        self.profil = profil
        self._droits = matrice.profils[profil]

    # --- niveau 1 : intercepteur d'entrée ---
    def peut_appeler(self, tool: CodeTool) -> bool: ...

    # --- niveau 2 : dans les tools ---
    def collections_autorisees(self) -> list[str]: ...          # → filtre Chroma
    def tables_autorisees(self) -> set[str]: ...                # → validation SQL
    def colonnes_interdites(self, table: str) -> set[str]: ...  # → validation SQL (E5)
    def schema_pour_prompt(self) -> str: ...                    # → génération SQL
```

C'est ce qui résout la tension du §3 : **le contrôle est au plus près de la donnée sans que
la matrice soit dupliquée huit fois.** Un tool ne sait pas ce qu'est un profil ; il sait
demander ce qu'il a le droit de lire.

### Authentification et autorisation : deux étapes, dans cet ordre

```
1. OAuth valide le jeton    → QUI ?    (sub, scopes)      ← aucun accès base
2. gouvernance.db résout    → QUOI ?   (table identites)
3. Perimetre construit      → passé aux tools
```

**OAuth n'interroge jamais la base, et la base ne valide jamais un jeton.** L'authentification
se termine avant la première requête SQL : interroger la base pour un appelant non authentifié
serait une surface d'attaque gratuite.

Le pont est la table `identites`, qui associe le `sub` du jeton à un profil.

**Pourquoi ne pas mettre le profil directement dans un scope OAuth** : si le profil vit dans le
jeton, changer les droits de quelqu'un impose de réémettre son jeton, et un jeton volé conserve
ses droits jusqu'à expiration. Avec la table, une ligne modifiée prend effet au prochain appel.

**MCP ne définit pas de RBAC** — pas de notion de rôle dans le protocole. Il fournit deux
points d'ancrage : `tools/list`, qui est par session et peut donc être filtré, et un profil
d'autorisation OAuth 2.1 pour les transports HTTP, où le serveur agit en *Resource Server*. En
transport stdio, il n'y a aucune authentification dans le protocole : l'identité vient de
l'environnement du sous-processus.

D'où une conséquence d'architecture : **la résolution de l'identité est isolée dans une seule
fonction**.

```python
def resoudre_profil(contexte) -> str:
    """Le SEUL point qui dépend du transport."""
    # stdio  : os.environ["SORABEL_PROFIL"], vérifié contre identites.sujet
    # HTTP   : jeton OAuth validé → sub → identites.profil
```

Tout le reste — matrice, validation Pydantic, `Perimetre`, filtrage — est inchangé d'un
transport à l'autre. Passer de la démonstration stdio à un déploiement OAuth ne toucherait
que cette fonction.

## 3. Où la matrice est appliquée

**Aux deux niveaux.** La question du brief appelle une défense en profondeur, et chaque
niveau couvre un angle mort de l'autre.

| Niveau | Ce qu'il contrôle | L'angle mort qu'il laisse |
|---|---|---|
| **Entrée du serveur** (intercepteur commun) | le profil a-t-il droit à *ce tool* ? journalisation systématique | un tool appelé **en interne** par un autre ne repasse pas par l'entrée |
| **Dans chaque tool** | collections, tables, colonnes — le périmètre *fin* | rien, mais la logique serait dupliquée 8 fois si elle n'était pas factorisée |

L'angle mort du premier niveau est concret : `answer_question` appelle le retrieval en
interne. Si seul l'intercepteur d'entrée filtrait les collections, un profil `support`
obtiendrait une réponse rédigée **à partir d'une note confidentielle**, sans qu'aucun appel
non autorisé n'apparaisse au journal. Le contrôle doit être au plus près de la donnée.

En pratique, la vérification fine est factorisée dans un objet `Perimetre` construit une
fois par appel à partir du profil, puis passé aux fonctions de retrieval et de SQL. Les
tools ne réimplémentent rien ; ils propagent un périmètre.

### Catalogue filtré

`tools/list` ne renvoie que les tools autorisés pour le profil. Le LLM du client ne peut donc
pas choisir un tool interdit — on évite un échec inutile et une description trompeuse.

Cela ne remplace pas le contrôle à l'appel : un client peut appeler un tool dont il n'a
jamais vu la description. Le catalogue filtré est une **commodité**, la vérification à
l'appel est la **sécurité**.

## 4. Ce que renvoie un appel refusé

### Un refus n'est pas une panne

Tous les refus sont des **retours normaux** portant un `statut`, jamais des exceptions de
protocole. Seules les défaillances techniques réelles (base injoignable, index corrompu)
remontent en erreur MCP. C'est la règle qui permet à un client de faire la différence.

| `statut` | Cause | Réaction attendue du client |
|---|---|---|
| `ok` | — | afficher |
| `hors_corpus` | score sous le seuil (E1) | « je ne sais pas », **pas** une réponse |
| `hors_schema` | table ou colonne inexistante | « cette donnée n'existe pas en base » |
| `ambigu` | plusieurs interprétations | relancer avec le critère choisi |
| `non_autorise` | matrice d'accès | « votre profil n'y a pas droit » |
| `refuse_ecriture` | tentative d'écriture SQL | incident de sécurité, à remonter |
| `erreur` | panne technique | incident d'exploitation |

Distinguer `hors_schema` de `non_autorise` est important et souvent négligé : « la donnée
n'existe pas » et « vous n'y avez pas droit » appellent des actions opposées de la part de
l'utilisateur.

### Forme d'un refus

```json
{
  "statut": "non_autorise",
  "code": "PROFIL_TOOL_INTERDIT",
  "message": "Le profil « dev » n'est pas autorisé à appeler ask_database.",
  "profil": "dev",
  "tool": "ask_database",
  "alternative": "get_schema donne la structure des tables sans accéder aux données."
}
```

Le champ `alternative` n'est pas de la politesse : il évite que le LLM du client entre dans
une boucle de tentatives. Un refus qui indique la sortie est un refus utile.

## 5. Journalisation (E5)

**Tout appel est journalisé, autorisé comme refusé.** Une ligne JSON par appel, en ajout
seul, dans `logs/appels.jsonl`.

```json
{"horodatage":"2026-09-01T14:22:31Z","profil":"support","tool":"ask_database",
 "autorise":false,"statut":"non_autorise","code":"COLONNE_INTERDITE",
 "entrees":{"question":"quelle est la marge sur REF-1024 ?"},
 "sql":null,"n_lignes":0,"duree_ms":3,"motif":"produits.marge_pct hors périmètre"}
```

| Champ | Pourquoi il est là |
|---|---|
| `horodatage`, `profil`, `tool` | qui a demandé quoi, quand — le minimum d'un audit |
| `autorise`, `statut`, `code` | distinguer un refus de gouvernance d'un refus métier |
| `entrees` | rejouer l'appel à l'identique |
| `sql` | **E3** : transparence de la requête exécutée ou rejetée |
| `n_lignes`, `duree_ms` | détecter une fuite de masse ou une requête lente |
| `motif` | rendre le refus compréhensible sans relire le code |

**Le format JSONL est un choix, pas un défaut.** Le test d'acceptance dit « quand on ouvre le
journal » : un fichier s'ouvre, se `grep`, se lit à l'œil en démonstration, et se charge en
pandas pour agréger par profil. Une table SQLite serait plus requêtable — mais écrire dans
une base alors que tout le chantier 2 garantit la lecture seule brouille le message.

Ce qui **n'est pas** journalisé : le contenu des résultats. On trace la question, la requête
et le volume, pas les lignes renvoyées — un journal ne doit pas devenir une copie de la base
sans les contrôles d'accès de la base.

## 6. Démontrer deux profils (livrable)

`scripts/mcp_client.py` rejoue la même séquence sous `support` puis sous `commercial` :

| # | Appel | `support` | `commercial` |
|---|---|---|---|
| 1 | `search_docs("politique tarifaire")` | notes confidentielles **absentes** | notes confidentielles présentes |
| 2 | `ask_database("quelle est la marge sur REF-1024 ?")` | `non_autorise` | `ok` + SQL + résultat |
| 3 | `ask_database("combien de commandes en avril ?")` | `ok` — 27 | `ok` — 27 |
| 4 | `ask_database("supprime les commandes de test")` | `refuse_ecriture` | `refuse_ecriture` |
| 5 | `get_schema()` | schéma **sans** `marge_pct` | schéma complet |
| 6 | `search_docs` puis `get_document` | ✓ briques séparées | ✓ |

Puis on ouvre `logs/appels.jsonl` : les douze appels y figurent, autorisés comme refusés.
C'est la démonstration la plus directe de E4 et E5 — le contraste est visible sur la même
séquence, sans commentaire.

L'appel 4 est identique pour les deux profils : **aucun profil n'écrit**, y compris `admin`.
La lecture seule n'est pas une restriction de profil, c'est une propriété de la Gateway.

## Points ouverts

- **Transport et identification du profil** : le profil vient-il d'un en-tête de session, du
  jeton du client, d'un paramètre de tool ? Un profil déclaré par l'appelant lui-même n'est
  pas une authentification — acceptable pour la démonstration pédagogique, à nommer
  explicitement comme une limite.
- **`sous_type` et `diffusion_restreinte`** ne sont pas encore produits par l'extracteur de
  notes (chantier 1). Sans eux, les collections `notes_operationnelles` et
  `notes_confidentielles` ne sont pas séparables.
- **Rotation du journal** : hors périmètre à 6 jours, à mentionner en soutenance.
