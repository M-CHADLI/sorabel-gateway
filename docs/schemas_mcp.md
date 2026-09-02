# Schémas — Chantier MCP et matrice d'accès

## 1. Le flux complet de la Gateway

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

## 2. La double application de la matrice

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

## 3. La matrice d'accès

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

## 4. Les statuts de retour

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
