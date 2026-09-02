# Schémas — Chantier Text-to-SQL

## 1. Le flux Text-to-SQL

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

## 2. Les quatre barrières de lecture seule

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

## 3. Les quatre issues d'un appel

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

## 4. Modèle de données et périmètre par profil

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
