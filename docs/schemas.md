# Schémas des trois chantiers

Diagrammes Mermaid, rendus par GitHub. Le dossier technique (`DOSSIER_TECHNIQUE.md`) porte les mêmes flux en ASCII, lisible hors navigateur.

---

- [Chantier RAG avancé](#chantier-rag-avancé)
- [Chantier Text-to-SQL](#chantier-text-to-sql)
- [Chantier MCP et matrice d'accès](#chantier-mcp-et-matrice-daccès)

---

## Chantier RAG avancé

### 1. Schéma du RAG avancé

```mermaid
flowchart TB
    subgraph INGEST["INGESTION (hors ligne, rejouable)"]
        direction TB
        PDF["fiches + notices<br/>230 PDF"]
        MD["notes internes<br/>80 MD"]
        HTML["procédures SAV<br/>90 HTML"]
        CACHE{"hash_source<br/>et schema_version<br/>inchangés ?"}
        NORM["Extracteur par format<br/>texte + tableaux → Markdown<br/>+ métadonnées (réf, version, date, titre)<br/>+ contrôles qualité"]
        CANON[("<b>documents canoniques</b><br/>1 JSON par fichier source<br/>fonction pure de la source")]
        RAPP["_rapport.md<br/>alertes d'extraction<br/>→ lu avant indexation"]
        VERS["<b>Regroupement des versions</b><br/>rassembler les fichiers qui sont<br/>le MÊME document à des versions différentes<br/>clé : (référence, type) — (famille, type) pour le SAV"]
        MANIF[("<b>_manifeste.json</b><br/>pour chaque groupe :<br/>versions[] + laquelle est courante<br/>propriété du corpus, pas du doc")]
        CHUNK["Chunking structurel<br/>1 section = 1 chunk<br/>&gt; 500 tk : redécoupe · &lt; 100 tk : fusion<br/>+ en-tête contextuelle<br/>+ est_version_courante"]
        PDF --> CACHE
        MD --> CACHE
        HTML --> CACHE
        CACHE -->|non| NORM --> CANON
        CACHE -->|"oui (cache)"| CANON
        NORM -.-> RAPP
        CANON --> VERS --> MANIF
        CANON --> CHUNK
        MANIF -.->|est_version_courante| CHUNK
    end

    subgraph INDEX["INDEX"]
        CHROMA[("Chroma<br/>vecteurs + métadonnées")]
        BM25[("BM25<br/>index lexical")]
    end

    CHUNK -->|"embedding<br/>multilingual-e5"| CHROMA
    CHUNK -->|"tokens"| BM25

    subgraph RETR["RETRIEVAL (en ligne)"]
        direction TB
        Q(["question"])
        REGEX{"contient<br/>REF-\d{4} ?"}
        FILT["filtre métadonnée<br/>reference = REF-8842"]
        DENSE["dense<br/>top 30"]
        LEX["BM25<br/>top 30"]
        RRF["fusion RRF<br/>k=60 → 30 candidats"]
        RERANK["cross-encoder<br/>rerank → top 3"]
        SEUIL{"score_max<br/>&ge; seuil ?"}
        Q --> REGEX
        REGEX -->|oui| FILT
        FILT --> DENSE
        REGEX -->|non| DENSE
        REGEX -->|non| LEX
        FILT --> LEX
        DENSE --> RRF
        LEX --> RRF
        RRF --> RERANK --> SEUIL
    end

    CHROMA -.->|"filtre est_version_courante"| DENSE
    BM25 -.-> LEX

    REFUS["REFUS motivé<br/>statut: hors_corpus<br/>aucun appel LLM"]
    GEN["Génération<br/>prompt ancré sur les 3 extraits"]
    CIT["Citations construites par le code<br/>titre + réf + date"]
    OUT(["réponse + sources[]"])

    SEUIL -->|non| REFUS
    SEUIL -->|oui| GEN --> CIT --> OUT

    style REFUS fill:#fde8e8,stroke:#c53030
    style RERANK fill:#e8f0fe,stroke:#1a56db
    style RRF fill:#e8f0fe,stroke:#1a56db
    style FILT fill:#e8f0fe,stroke:#1a56db
```

Les trois blocs bleus sont ce qui distingue « avancé » de « naïf ».
Le bloc rouge est ce qui garantit E1.

#### Le regroupement, en clair

Le corpus contient plusieurs fichiers qui sont **le même document à des versions
différentes**. Le regroupement sert uniquement à les rassembler pour savoir **laquelle est la
plus récente**. Il ne fusionne rien et ne supprime rien : chaque version reste un document
indexé à part entière.

```
                        ┌─ REF-1024-v1.0.pdf ──> doc_id  fiche_technique:REF-1024:v1.0
groupe                  │                        est_version_courante = false
"fiche_technique:REF-1024"
                        └─ REF-1024-v2.1.pdf ──> doc_id  fiche_technique:REF-1024:v2.1
                                                 est_version_courante = TRUE  ← la plus récente
```

**La clé de regroupement dépend du type**, parce que l'identité d'un document n'est pas
portée par le même champ partout :

| Type | Clé | Exemple | Pourquoi |
|---|---|---|---|
| Fiche technique | `(référence, type)` | `fiche_technique:REF-1024` | la référence produit identifie la fiche |
| Notice | `(référence, type)` | `notice:REF-1459` | idem |
| Procédure SAV | `(**famille**, type)` | `procedure_sav:proc-casse-transport-01` | une procédure n'a pas de référence produit ; son identité est sa **famille**, extraite du nom de fichier |
| Note interne | aucune | — | les notes n'ont pas de versions multiples |

Le piège du SAV : la clé est `proc-casse-transport-01`, **pas** le nom de fichier complet
`proc-casse-transport-01-v2.0`. Grouper sur le nom complet créerait un groupe d'un seul
membre par fichier — donc chaque version se croirait courante, et le filtre par défaut
laisserait passer les deux.

Ce que le regroupement produit, et rien d'autre : le **manifeste**, qui dit pour chaque
groupe quelles versions existent et laquelle est courante. Le chunking lit ensuite ce
manifeste pour écrire `est_version_courante` sur chaque chunk — là où le filtre de recherche
en a besoin.

**Mesuré sur le corpus** : 350 groupes au total, dont **50 contiennent plusieurs versions**.
Les 300 autres n'ont qu'un seul fichier, qui est donc courant d'office.

---

### 2. Modèle des chunks et métadonnées

```mermaid
erDiagram
    FICHIER ||--|| DOCUMENT : "normalisé en (canonique)"
    GROUPE_VERSIONS ||--o{ DOCUMENT : "regroupe"
    DOCUMENT ||--|{ CHUNK : "découpé en"
    CHUNK ||--|| VECTEUR : "indexé comme"
    CHUNK ||--|| POSTING : "indexé comme"

    FICHIER {
        str chemin "corpus/fiches/REF-1024-v2.1.pdf"
        str format "pdf | md | html"
    }
    GROUPE_VERSIONS {
        str cle PK "fiche_technique:REF-1024 — le MÊME document, toutes versions"
        str reference "REF-1024 — ou la famille, pour le SAV"
        str type_document "second membre de la clé"
        str versions "1.0, 2.1 — toutes indexées, aucune supprimée"
        str version_courante "2.1 — vit dans _manifeste.json, pas dans le canonique"
        str doc_id_courant ""
    }
    DOCUMENT {
        str doc_id PK "fiche_technique:REF-1024:v2.1"
        int schema_version "invalide le cache"
        str titre "→ citation E1"
        str reference FK "→ pivot vers le SQL"
        str version "2.1"
        date date "→ citation E1"
        str type_document "fiche|notice|note|procedure_sav"
        str source_path "→ get_document"
        str url "→ citation E1"
        str hash_source "SHA-256 du fichier → cache"
        str hash_texte "SHA-256 du texte → dédoublonnage"
        json qualite "statut + alertes d'extraction"
    }
    CHUNK {
        str chunk_id PK "doc_id#3"
        str doc_id FK ""
        int index "position dans le doc"
        str section "Caractéristiques | Étapes"
        str texte "en-tête contextuelle + contenu → embeddé"
        str texte_brut "contenu seul → affiché"
        int n_tokens "≤ 500"
        bool est_version_courante "issu du manifeste, dénormalisé ici"
    }
    VECTEUR {
        str chunk_id PK ""
        float embedding "1024 dims"
        json metadata "réf, version, type, courante → filtres Chroma"
    }
    POSTING {
        str chunk_id PK ""
        json termes "tokens + fréquences BM25"
    }
```

**Héritage des métadonnées** : elles vivent au niveau `DOCUMENT` mais sont **recopiées sur
chaque chunk** dans Chroma — un filtre Chroma ne peut pas faire de jointure. Dénormalisation
assumée.

**En-tête contextuelle** — la différence entre `texte` et `texte_brut` :

```
texte        = "[Fiche technique REF-1024 v2.1 — Disjoncteur différentiel
                tétrapolaire — section « Caractéristiques »]
                Calibre 40 A | Sensibilité 30 mA | Tension 400 V triphasé"
texte_brut   = "Calibre 40 A | Sensibilité 30 mA | Tension 400 V triphasé"
```

On embedde `texte` (retrouvable), on affiche `texte_brut` (lisible).

---

### 3. Tools MCP liés au RAG

```mermaid
flowchart LR
    subgraph CLIENTS["CLIENTS"]
        SLACK["Bot Slack<br/>support"]
        IDE["IDE dev"]
        COM["Poste<br/>commercial"]
    end

    subgraph TOOLS["CATALOGUE MCP — briques RAG"]
        AQ["<b>answer_question</b><br/>question → réponse rédigée<br/>+ sources[] + statut"]
        SD["<b>search_docs</b><br/>requête → extraits classés<br/>+ scores + métadonnées"]
        GD["<b>get_document</b><br/>doc_id | réf+version<br/>→ document complet"]
        LS["<b>list_sources</b><br/>filtres → inventaire<br/>du corpus indexé"]
    end

    subgraph PIPE["PIPELINE"]
        RET["retrieval<br/>hybride + rerank"]
        GENE["génération<br/>ancrée"]
        STORE[("Chroma + BM25")]
        FS[("documents<br/>canoniques")]
    end

    SLACK --> AQ
    IDE --> SD
    IDE --> GD
    COM --> AQ
    COM --> SD

    AQ --> RET --> GENE
    SD --> RET
    GD --> FS
    LS --> STORE
    RET --> STORE

    style AQ fill:#e8f0fe,stroke:#1a56db
    style GENE fill:#fef3c7,stroke:#b45309
```

`answer_question` = `search_docs` + génération. C'est **le même retrieval**, exposé à deux
niveaux : le tool de haut niveau pour qui veut une réponse, les briques pour qui veut les
extraits bruts. Un IDE ne veut pas de prose de LLM.

| Tool | Entrées | Sorties | Garanties |
|---|---|---|---|
| `answer_question` | `question`, `collections?`, `inclure_versions_anciennes?` | `statut`, `reponse`, `sources[]` | Cite toujours (E1) · refuse sous le seuil, sans appeler le LLM |
| `search_docs` | `requete`, `k?`, `reference?`, `type_document?`, `inclure_versions_anciennes?` | `resultats[]` : `texte_brut`, `score`, métadonnées | Hybride + rerank · réf exacte en tête (E2) · pas de génération |
| `get_document` | `doc_id` \| (`reference` + `version?`) | `titre`, `texte`, métadonnées, `versions_disponibles[]` | Version courante par défaut · aucune inférence |
| `list_sources` | `type_document?`, `reference?` | `documents[]`, `total`, `collections[]` | Périmètre exact de l'index, pas du disque |

**Statuts de retour** — un client doit distinguer les trois :

| `statut` | Sens | Réaction attendue du client |
|---|---|---|
| `ok` | réponse ancrée, sources présentes | afficher |
| `hors_corpus` | le corpus ne couvre pas | dire « je ne sais pas », **ne pas** présenter comme une réponse |
| `erreur` | panne technique | remonter l'incident |

---

## Chantier Text-to-SQL

### 1. Le flux Text-to-SQL

```mermaid
flowchart TB
    Q(["question + profil"])
    SENS{"intention sensible ?<br/>marge · prix d'achat"}
    REFUS1["statut: non_autorise<br/><b>aucun appel LLM</b>"]

    subgraph CTX["CONTEXTE DE GÉNÉRATION"]
        direction LR
        SCH["schéma commenté<br/><b>filtré par profil</b>"]
        VAL["valeurs types<br/>livree · LILLE · PME"]
        EX["exemples question → SQL"]
        REG["règles de sortie<br/>1 instruction, SELECT"]
    end

    GEN["génération LLM"]
    SQL(["SQL candidat"])

    subgraph VALID["VALIDATION"]
        direction TB
        V1{"1 seule instruction<br/>SELECT ou WITH ?"}
        V2{"mots-clés d'écriture<br/>absents ?"}
        V3{"tables connues ?"}
        V4{"colonnes ⊆ profil ?"}
        V1 --> V2 --> V3 --> V4
    end

    LIM["injection LIMIT 200<br/>si absent"]
    EXEC[("exécution<br/>connexion mode=ro<br/>sous timeout")]
    OK(["statut: ok<br/>sql + colonnes + lignes"])

    RE["statut: refuse_ecriture"]
    RH["statut: hors_schema<br/>+ tables disponibles"]
    RN["statut: non_autorise<br/>+ colonne refusée"]
    JOURNAL[/"journal : profil, tool,<br/>question, sql, statut, n_lignes"/]

    Q --> SENS
    SENS -->|oui| REFUS1
    SENS -->|non| CTX --> GEN --> SQL --> VALID
    V1 -->|non| RE
    V2 -->|non| RE
    V3 -->|non| RH
    V4 -->|non| RN
    V4 -->|oui| LIM --> EXEC --> OK

    REFUS1 -.-> JOURNAL
    RE -.-> JOURNAL
    RH -.-> JOURNAL
    RN -.-> JOURNAL
    OK -.-> JOURNAL

    style REFUS1 fill:#fde8e8,stroke:#c53030
    style RE fill:#fde8e8,stroke:#c53030
    style RH fill:#fef3c7,stroke:#b45309
    style RN fill:#fde8e8,stroke:#c53030
    style EXEC fill:#e8f0fe,stroke:#1a56db
    style JOURNAL fill:#f3f4f6,stroke:#6b7280
```

**Tout chemin se termine dans le journal**, succès comme refus (E5). Le SQL généré
accompagne la réponse dans les deux cas : voir la requête rejetée est ce qui rend le refus
compréhensible.

---

### 2. Les quatre barrières de lecture seule

```mermaid
flowchart LR
    SQL(["SQL généré"])
    B1["<b>1. Connexion ro</b><br/>file:sorabel.db?mode=ro<br/><i>appliquée par SQLite</i>"]
    B2["<b>2. Validation</b><br/>1 instruction · SELECT/WITH<br/>mots-clés · périmètre"]
    B3["<b>3. LIMIT par défaut</b><br/>200 lignes"]
    B4["<b>4. Timeout</b><br/>garde-fou d'exécution"]
    R(["résultat"])

    SQL --> B2 --> B3 --> B1 --> B4 --> R

    N1["arrête : DROP, UPDATE, ATTACH,<br/>PRAGMA, 2e instruction après ;<br/>table hors profil"]
    N2["arrête : 993 lignes dans<br/>la réponse MCP"]
    N3["arrête : TOUTE écriture,<br/>même si le reste est contourné"]
    N4["arrête : produit cartésien<br/>qui verrouille la base"]

    B2 -.-> N1
    B3 -.-> N2
    B1 -.-> N3
    B4 -.-> N4

    style B1 fill:#dcfce7,stroke:#15803d
    style N3 fill:#dcfce7,stroke:#15803d
```

La barrière 1 est la seule **infranchissable** : elle est appliquée par le moteur, pas par
notre code. Les trois autres couvrent ce qu'elle laisse passer — une lecture parfaitement
légale mais hors périmètre, massive, ou bloquante.

---

### 3. Les quatre issues d'un appel

```mermaid
flowchart TB
    A(["ask_database"])
    A --> OK["<b>ok</b><br/>résultat + SQL exécuté"]
    A --> AM["<b>ambigu</b><br/>interprétations proposées"]
    A --> HS["<b>hors_schema</b><br/>+ liste des tables réelles"]
    A --> NA["<b>non_autorise</b><br/>+ colonne refusée"]

    OK --> U1["afficher"]
    AM --> U2["relancer avec le critère<br/>choisi par l'utilisateur"]
    HS --> U3["dire que la donnée<br/>n'existe pas en base"]
    NA --> U4["dire que le profil<br/>n'y a pas droit"]

    style OK fill:#dcfce7,stroke:#15803d
    style AM fill:#fef3c7,stroke:#b45309
    style HS fill:#fef3c7,stroke:#b45309
    style NA fill:#fde8e8,stroke:#c53030
```

Les quatre statuts sont des **retours normaux**, jamais des exceptions. Un client doit
pouvoir les distinguer d'une panne — et distinguer « la donnée n'existe pas » de « vous n'y
avez pas droit », qui appellent des réactions différentes.

---

### 4. Modèle de données et périmètre par profil

```mermaid
erDiagram
    CLIENTS ||--o{ COMMANDES : passe
    COMMANDES ||--|{ VENTES : contient
    PRODUITS ||--o{ VENTES : "porte sur"
    PRODUITS ||--|{ STOCKS : "stocké en"

    PRODUITS {
        TEXT ref PK "REF-1024 — PIVOT vers le corpus (120/120)"
        TEXT nom ""
        TEXT categorie "9 valeurs"
        TEXT fabricant ""
        TEXT unite ""
        REAL prix_vente_ht "public"
        REAL prix_achat_ht "SENSIBLE — jamais pour support"
        REAL marge_pct "SENSIBLE — jamais pour support"
        INTEGER actif "vaut 1 sur les 120 lignes"
    }
    STOCKS {
        INTEGER id PK ""
        TEXT ref FK ""
        TEXT entrepot "LILLE | LYON | NANTES"
        INTEGER quantite ""
        INTEGER seuil_reappro ""
    }
    CLIENTS {
        TEXT id PK "CLI-1000"
        TEXT raison_sociale ""
        TEXT segment "PME | artisan | collectivité | grand compte"
        TEXT ville ""
        TEXT email "donnée personnelle"
    }
    COMMANDES {
        TEXT id PK "CMD-2025-0004"
        TEXT client_id FK ""
        TEXT date_commande "TEXT ISO — strftime() applicable"
        TEXT statut "annulee|en_attente|expediee|livree|preparee"
        REAL montant_ht ""
    }
    VENTES {
        INTEGER id PK ""
        TEXT commande_id FK ""
        TEXT ref FK ""
        INTEGER quantite ""
        REAL prix_unitaire_ht ""
        REAL remise_pct ""
        REAL marge_ht "SENSIBLE — jamais pour support"
    }
```

`produits.ref` porte la même valeur que la métadonnée `reference` des chunks du corpus :
c'est le seul point de contact entre les deux mondes de la Gateway, et il est complet
(120 références en base, 120 fiches, aucun orphelin).

---

## Chantier MCP et matrice d'accès

### 1. Le flux complet de la Gateway

```mermaid
flowchart TB
    CLIENT["<b>scripts/mcp_client.py</b><br/>client MCP unique<br/>—<br/>lancé avec --profil support | commercial | dev | admin"]

    subgraph GATEWAY["SERVEUR MCP — Sorabel Data Gateway"]
        direction TB
        ENTREE{{"<b>1. intercepteur d'entrée</b><br/>ce profil a-t-il droit à CE TOOL ?"}}
        CATAL["<b>tools/list</b><br/>catalogue filtré par profil"]
        PERIM["<b>2. Périmètre</b><br/>construit une fois par appel<br/>collections · tables · colonnes"]

        subgraph RAGT["TOOLS RAG"]
            direction TB
            AQ["<b>answer_question</b><br/>question → réponse rédigée + sources<br/><i>refuse sous le seuil (E1)</i>"]
            SD["<b>search_docs</b><br/>requête → extraits + scores<br/><i>aucune génération</i>"]
            GD["<b>get_document</b><br/>doc_id → document complet"]
            LS["<b>list_sources</b><br/>filtres → inventaire + versions"]
        end

        subgraph SQLT["TOOLS DONNÉES"]
            direction TB
            AD["<b>ask_database</b><br/>question → SQL + résultat<br/><i>génératif, 4 barrières</i>"]
            GS["<b>get_schema</b><br/>schéma commenté du profil"]
            CS["<b>check_stock</b><br/>ref → stock par entrepôt<br/><i>figé, zéro LLM</i>"]
            OS["<b>order_status</b><br/>order_id → statut<br/><i>figé, zéro LLM</i>"]
        end

        RET["retrieval hybride<br/>RRF + rerank + seuil"]
        SQLP["génération SQL<br/>+ validation + LIMIT + ro"]
    end

    subgraph PREP["PRÉPARATION (hors ligne)"]
        ING["ingestion → 400 canoniques<br/>+ manifeste + rapport qualité"]
        CHK["chunking → 400 chunks<br/>+ en-tête contextuelle"]
        IDX[("Chroma 768d<br/>+ BM25")]
        ING --> CHK --> IDX
    end

    CORPUS[("corpus<br/>400 documents")]
    DB[("sorabel.db<br/>5 tables · lecture seule")]
    JOURNAL[/"<b>logs/appels.jsonl</b><br/>tout appel, autorisé ou refusé"/]
    REFUS["<b>statut: non_autorise</b><br/>code + motif + alternative"]

    CLIENT -->|"profil + tool + arguments"| ENTREE
    ENTREE -.->|"le client ne voit que<br/>ses tools autorisés"| CATAL
    CATAL -.-> CLIENT
    ENTREE -->|refusé| REFUS
    ENTREE -->|autorisé| PERIM
    PERIM --> RAGT
    PERIM --> SQLT

    AQ --> RET
    SD --> RET
    LS --> RET
    GD --> IDX
    AD --> SQLP
    CS --> DB
    OS --> DB
    GS -.->|schéma du profil| DB

    CORPUS --> ING
    IDX --> RET
    SQLP --> DB

    ENTREE -.-> JOURNAL
    RAGT -.-> JOURNAL
    SQLT -.-> JOURNAL
    REFUS -.-> JOURNAL

    style CLIENT fill:#e8f0fe,stroke:#1a56db
    style ENTREE fill:#e8f0fe,stroke:#1a56db
    style PERIM fill:#dcfce7,stroke:#15803d
    style REFUS fill:#fde8e8,stroke:#c53030
    style JOURNAL fill:#f3f4f6,stroke:#6b7280
    style AQ fill:#fef3c7,stroke:#b45309
    style AD fill:#fef3c7,stroke:#b45309
```

**Un seul client, quatre profils.** `scripts/mcp_client.py` prend le profil en argument. Ce
n'est pas une simplification de démonstration : c'est ce qui rend le contraste **prouvable**.
La même séquence d'appels, le même code client, le même serveur — seul le profil change, et
les réponses diffèrent. Quatre clients distincts n'auraient rien démontré : on n'aurait pas
pu écarter l'hypothèse que la différence vient du client.

Les deux tools en jaune (`answer_question`, `ask_database`) sont **les seuls qui appellent un
LLM**. Les six autres sont déterministes — ce qui explique pourquoi un IDE préfère
`search_docs` et pourquoi le support préfère `check_stock` à `ask_database` pour une question
de stock.

Le **Périmètre** (vert) est construit une fois par appel et propagé jusqu'au retrieval et au
SQL. C'est ce qui évite de dupliquer la matrice dans les huit tools tout en gardant le
contrôle au plus près de la donnée.

---

### 2. La double application de la matrice

```mermaid
flowchart TB
    APPEL(["appel client<br/>profil + tool + arguments"])
    N1{{"<b>NIVEAU 1 — entrée du serveur</b><br/>ce profil a-t-il droit à CE TOOL ?"}}
    N2{{"<b>NIVEAU 2 — dans le tool</b><br/>collections · tables · colonnes"}}
    OK(["résultat"])
    R1["non_autorise<br/>PROFIL_TOOL_INTERDIT"]
    R2["non_autorise<br/>COLLECTION_INTERDITE<br/>COLONNE_INTERDITE"]

    APPEL --> N1
    N1 -->|non| R1
    N1 -->|oui| N2
    N2 -->|non| R2
    N2 -->|oui| OK

    INTERNE(["<b>appel interne</b><br/>answer_question → retrieval"])
    INTERNE -.->|"ne repasse JAMAIS<br/>par le niveau 1"| N2

    style N1 fill:#e8f0fe,stroke:#1a56db
    style N2 fill:#dcfce7,stroke:#15803d
    style INTERNE fill:#fef3c7,stroke:#b45309
    style R1 fill:#fde8e8,stroke:#c53030
    style R2 fill:#fde8e8,stroke:#c53030
```

**L'angle mort que le niveau 2 comble** : `answer_question` appelle le retrieval en interne.
Si seul le niveau 1 filtrait, un profil `support` obtiendrait une réponse rédigée à partir
d'une note confidentielle — et **aucun appel non autorisé n'apparaîtrait au journal**.

---

### 3. La matrice d'accès

```mermaid
flowchart LR
    subgraph P["PROFILS"]
        SUP["<b>support</b><br/>bot Slack"]
        COM["<b>commercial</b><br/>poste"]
        DEV["<b>dev</b><br/>IDE"]
        ADM["<b>admin</b><br/>exploitation"]
    end

    subgraph T["TOOLS"]
        RAGH["answer_question"]
        RAGB["search_docs<br/>get_document<br/>list_sources"]
        SQLG["ask_database"]
        SQLF["get_schema<br/>check_stock<br/>order_status"]
    end

    subgraph COL["COLLECTIONS"]
        PUB["fiches · notices · sav"]
        NOP["notes_operationnelles<br/>48 documents"]
        NCF["notes_confidentielles<br/>32 documents<br/><i>« Diffusion restreinte »</i>"]
    end

    subgraph TAB["TABLES / COLONNES"]
        TOUT["5 tables<br/>toutes colonnes"]
        SANS["5 tables<br/><b>sans</b> prix_achat_ht<br/>marge_pct · marge_ht"]
        SCHEMA["schéma seul<br/>aucune donnée"]
    end

    SUP --> RAGH & RAGB & SQLG & SQLF
    COM --> RAGH & RAGB & SQLG & SQLF
    DEV --> RAGB & SQLF
    ADM --> RAGH & RAGB & SQLG & SQLF

    SUP --> PUB & NOP
    COM --> PUB & NOP & NCF
    DEV --> PUB
    ADM --> PUB & NOP & NCF

    SUP --> SANS
    COM --> TOUT
    DEV --> SCHEMA
    ADM --> TOUT

    style NCF fill:#fde8e8,stroke:#c53030
    style SANS fill:#fef3c7,stroke:#b45309
    style SCHEMA fill:#f3f4f6,stroke:#6b7280
```

Deux refus volontaires, qui ne sont pas des oublis :

- **`dev` n'a pas `answer_question`** — un IDE veut chercher sans générer, c'est le cas
  d'usage cité par le brief.
- **`dev` n'a aucun accès aux données réelles** — `get_schema` lui donne la forme, pas le
  contenu. Un environnement de développement n'a pas à contenir les commandes des clients.

Et un accès volontairement **maintenu** : `support` conserve `ask_database`. Le refus doit
se produire *dans* le tool, sur les colonnes — sans quoi le test d'acceptance « profil
support, question sur les marges → refusée » ne pourrait pas s'exécuter.

---

### 4. Les statuts de retour

```mermaid
flowchart TB
    A(["appel MCP"])
    A --> NORM["<b>retours normaux</b><br/>un champ statut"]
    A --> ERR["<b>erreur MCP</b><br/>panne technique réelle"]

    NORM --> OK["ok"]
    NORM --> HC["hors_corpus<br/><i>RAG : sous le seuil</i>"]
    NORM --> HS["hors_schema<br/><i>SQL : table inexistante</i>"]
    NORM --> AM["ambigu<br/><i>SQL : plusieurs lectures</i>"]
    NORM --> NA["non_autorise<br/><i>matrice d'accès</i>"]
    NORM --> RE["refuse_ecriture<br/><i>tentative d'écriture</i>"]

    ERR --> EX["base injoignable<br/>index corrompu"]

    style NORM fill:#dcfce7,stroke:#15803d
    style ERR fill:#fde8e8,stroke:#c53030
    style OK fill:#dcfce7,stroke:#15803d
    style NA fill:#fde8e8,stroke:#c53030
    style RE fill:#fde8e8,stroke:#c53030
```

**Un refus n'est jamais une exception de protocole.** C'est la règle qui permet à un client
de distinguer « je n'ai pas la réponse » de « le serveur est en panne » — et de ne pas
présenter un refus comme une réponse.

`hors_schema` et `non_autorise` doivent rester distincts : « la donnée n'existe pas » et
« vous n'y avez pas droit » appellent des actions opposées de la part de l'utilisateur.

