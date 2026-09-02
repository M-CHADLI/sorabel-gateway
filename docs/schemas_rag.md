# Schémas — Chantier RAG avancé

## 1. Schéma du RAG avancé

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

### Le regroupement, en clair

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

## 2. Modèle des chunks et métadonnées

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

## 3. Tools MCP liés au RAG

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
