# Sorabel — l'agent augmenté par la donnée, exposé via MCP

> Brief récupéré depuis Simplonline le 27/08/2026 (mis à jour le 27/08/2026 après modification de la page).
> Source : https://wildcodeschool.simplonline.co/classrooms/0e9e318b-0491-4bde-a2a3-ae0be9aa6dc9/briefs/e470087c-1160-47a5-8805-a6b8810219da
> Créé le 06/07/26 · Assigné à Elbby Skermine AGWU · Tag : **MCP & RAG**
> Référentiel : [2023] Certification RNCP Développeur.se en intelligence artificielle — Compétences transversales

## Ressources fournies

- Repository
- `eval/questions_rag.jsonl`
- `eval/questions_sql.jsonl`
- Matrice d'accès
- Data

---

## Contexte du projet

Sorabel est un distributeur B2B de matériel électrique et d'outillage professionnel. Son savoir vit dans deux mondes : un **corpus documentaire** (fiches techniques, notices, procédures SAV) et une **base SQL** (produits, stocks, commandes, ventes). Depuis un an, chaque équipe s'est bricolé son outil : le support a un bot qui cherche mal dans les PDF, les commerciaux ont un script qui tape des requêtes SQL à la main — l'une d'elles a verrouillé la base un vendredi soir — et les réponses divergent d'une équipe à l'autre.

La DSI siffle la fin de la récré et publie une note de cadrage (`docs/cadrage_dsi.md`) : les bricolages sont gelés, et un point d'accès unique et gouverné doit les remplacer — la **Sorabel Data Gateway**, un serveur MCP que tous les outils internes (bot Slack du support, IDE des devs, poste des commerciaux) consommeront. Elle doit exposer :

- **Une recherche documentaire à la hauteur du corpus** — la recherche naïve actuelle rate les références exactes (`REF-8842`), confond les versions d'une même notice et répond à côté : il faut un RAG avancé (hybride, reranking), avec sources citées.
- **Les données en langage naturel** — les équipes métier ne savent pas écrire de SQL : il faut des tools Text-to-SQL en lecture seule, sûrs et transparents.
- **Une gouvernance unique** — chaque client n'accède qu'à ce que la matrice d'accès l'autorise, et tout est journalisé.

**Mission : construire la Gateway de zéro, à la hauteur de ces trois exigences.**

## Modalités pédagogiques

Travail **individuel**. **6 jours max**. Démo de fin de phase.

---

## Travail préliminaire de conception

La conception se mène en trois chantiers. Traitez les questions de chacun et produisez le schéma associé. La DSI impose les exigences suivantes ; à vous d'en déduire l'architecture.

### Exigences imposées

| Code | Exigence |
|------|----------|
| **E1** | Toute réponse documentaire cite ses sources (titre + référence + date) ; si le corpus ne couvre pas, l'outil le dit au lieu d'inventer. |
| **E2** | La recherche trouve aussi bien par référence exacte (« REF-8842 ») que par question en langage naturel (« quel disjoncteur pour du triphasé ? »). |
| **E3** | Tout SQL exécuté est lecture seule, restreint aux tables autorisées du profil ; la requête générée est tracée avec son résultat (transparence). |
| **E4** | Un même serveur MCP sert tous les clients internes ; chaque client n'accède qu'aux tools, collections et tables prévus par la matrice d'accès. |
| **E5** | Tout appel (autorisé ou refusé) est journalisé ; les colonnes sensibles (prix d'achat, marges) ne sortent jamais pour le profil support. |
| **E6** | Le gain de la recherche avancée sur la recherche simple est mesuré et documenté. |

### 1 — RAG avancé

Questions pour guider votre réflexion :

- Comment normaliser un corpus hétérogène (PDF techniques avec tableaux, HTML, Markdown) et traiter les versions multiples d'une même notice (dédoublonnage, champ version) ?
- Quelle granularité de chunk pour des fiches techniques, et quelles métadonnées (référence produit, version, date, type de document, url) ? En quoi la métadonnée référence produit est-elle décisive ici ?
- Pourquoi la recherche dense seule rate-t-elle « REF-8842 » ? Que rattrape la recherche lexicale ? Comment combiner les deux (hybride), et qu'apporte un reranking en plus ?
- Comment garantir E1 : citations systématiques, et refus quand le score de pertinence est trop bas ?
- Comment mesurer le gain (E6) : quel sous-ensemble de `questions_rag.jsonl`, quelle métrique de pertinence, avant/après ?

**Livrable intermédiaire**

- Schéma du RAG avancé
- Modèle des chunks et métadonnées
- Tools potentiels liés au RAG

### 2 — Text-to-SQL

Questions pour guider votre réflexion :

- Comment passer d'une question métier à une requête : que donnez-vous au modèle (schéma commenté, exemples de requêtes, valeurs types) pour qu'il génère juste ?
- Comment garantir la lecture seule (E3) : droits au niveau de la connexion, validation de la requête générée (liste de mots interdits, analyse), `LIMIT` par défaut ? Une seule barrière suffit-elle ?
- Comment restreindre le périmètre de tables et de colonnes par profil (le support ne voit jamais prix d'achat ni marges — E5) ?
- Quels besoins récurrents méritent des tools SQL figés (requêtes paramétrées écrites par vous : stock d'une référence, statut d'une commande) plutôt que du SQL généré ? Quel est l'intérêt de chaque approche ?
- Que fait le tool si la question est ambiguë ou hors schéma (« quel est le meilleur client ? ») : demander une précision, refuser proprement ?

**Livrable intermédiaire**

- Flux du Text-to-SQL
- Tools potentiels liés au Text-to-SQL

### 3 — Concevoir l'exposition MCP et la matrice d'accès

Questions pour guider votre réflexion :

- Quels tools exposer ? Le RAG complet (`answer_question`) mais aussi ses parties décomposées (`search_docs`, `get_document`, `list_sources`) : à quels clients servent le tool de haut niveau vs les briques (un IDE peut vouloir chercher sans générer) ?
- Côté données : le tool génératif `ask_database`, l'outil d'aide `get_schema`, et les tools figés (`check_stock`, `order_status`) — comment les décrire pour que les clients (et leurs LLM) choisissent le bon ?
- Comment implémentez-vous la matrice d'accès (client × tool × collections × tables) et où la faites-vous respecter : à l'entrée du serveur, dans chaque tool, les deux ?
- Que renvoie un appel refusé (message, code) et que journalisez-vous pour chaque appel (E5) ?
- Comment un client gère-t-il proprement vos erreurs (hors corpus, hors schéma, non autorisé) sans les faire passer pour des réponses ?

### Architecture / schémas attendus

1. **Le schéma de flux complet** : corpus + base SQL → ingestion/indexation → retrieval hybride + rerank → serveur MCP (catalogue de tools) → clients (support, commercial).
2. **Le modèle des chunks et métadonnées** (avec référence produit et version).
3. **Le catalogue des tools MCP** : nom, entrées, sorties, garanties (lecture seule, citations, refus) — RAG complet, briques du RAG, tools SQL figés et génératif.
4. **Le chemin Text-to-SQL** : question → génération → validation → exécution lecture seule → résultat + requête.
5. **La matrice d'accès** (profil × tool × collections × tables/colonnes).

---

## Développement

### Chantier RAG avancé

- Construire l'ingestion du corpus : normalisation PDF/HTML/Markdown, gestion des versions et doublons, chunking, métadonnées (référence produit, version, date), indexation dans **Chroma**.
- Brancher une recherche dense de base avec citations systématiques et refus hors corpus (E1).
- Passer en recherche hybride (+ reranking) et mesurer le gain sur `eval/questions_rag.jsonl`, notamment les questions par référence exacte (E2, E6).

### Chantier Text-to-SQL

- Implémenter `get_schema` puis le tool génératif `ask_database` : génération sur schéma commenté, validation lecture seule, périmètre de tables par profil, requête renvoyée avec le résultat (E3, E5).
- Implémenter les tools SQL figés (`check_stock(ref)`, `order_status(order_id)`) et le refus propre des questions ambiguës ou hors schéma.

### Chantier Serveur MCP

- Implémenter le serveur MCP exposant le catalogue : `answer_question`, `search_docs`, `get_document`, `list_sources`, `ask_database`, `get_schema`, `check_stock`, `order_status`.
- Appliquer la matrice d'accès et la journalisation de tous les appels, autorisés comme refusés (E4, E5).
- Documenter le catalogue pour les équipes clientes et démontrer deux profils différents avec `scripts/mcp_client.py` (support vs commercial).

---

## Modalités d'évaluation

- Validation du **dossier de conception** (porte d'entrée du brief) : les schémas et la matrice d'accès sont questionnés.
- Passage des **tests d'acceptance fournis** (RAG + Text-to-SQL + MCP) + essai du service.
- Auto-évaluation et co-évaluation Simplonline.

---

## Tests d'acceptance fournis

*(la réalisation doit les faire passer)*

### RAG avancé

- [ ] Étant donné une question couverte par le corpus, quand elle est posée via `answer_question`, alors la réponse cite ses sources (titre + référence + date).
- [ ] Étant donné une question hors corpus, quand elle est posée, alors l'outil ne fabrique pas de réponse et le signale.
- [ ] Étant donné la recherche « REF-8842 », quand elle est lancée via `search_docs`, alors la fiche technique correspondante remonte en tête des résultats.
- [ ] Étant donné la recherche hybride, quand on la compare à la recherche dense initiale sur `questions_rag.jsonl`, alors le gain est mesuré et documenté.

### Text-to-SQL

- [ ] Étant donné « combien de commandes en avril ? », quand la question passe par `ask_database`, alors le résultat est correct et la requête SQL générée est renvoyée avec lui.
- [ ] Étant donné « supprime les commandes de test », quand la demande passe par `ask_database`, alors elle est refusée (lecture seule) et journalisée.
- [ ] Étant donné le profil support, quand une question touche les marges ou les prix d'achat, alors elle est refusée selon la matrice d'accès.
- [ ] Étant donné une question hors schéma, quand elle est posée, alors le tool refuse clairement au lieu de générer du SQL halluciné.

### Serveur MCP

- [ ] Étant donné un client au profil autorisé, quand il appelle un tool, alors il n'accède qu'aux tools, collections et tables prévus par la matrice.
- [ ] Étant donné un client non autorisé sur un tool, quand il l'appelle, alors l'appel est refusé avec un message clair et journalisé.
- [ ] Étant donné un client voulant chercher sans générer, quand il enchaîne `search_docs` puis `get_document`, alors les briques du RAG fonctionnent séparément.
- [ ] Étant donné une session de démonstration, quand on ouvre le journal, alors tous les appels (autorisés et refusés) y figurent.

---

## Livrables

- **Dossier de conception** (schéma du flux + modèles de chunks + catalogue de tools + flow Text-to-SQL + matrice d'accès).
- **Le serveur MCP** (`mcp_server/`) exposant le catalogue complet, ainsi qu'un mini guide d'accès.
- **Un lien d'une interface graphique** du produit fonctionnel.

## Critères de performance

- Tous les tests d'acceptance fournis passent (RAG, Text-to-SQL, MCP).
- Les six exigences DSI (E1–E6) sont respectées et démontrées en soutenance de fin de phase.
- La recherche hybride surpasse la recherche dense initiale, preuve chiffrée à l'appui.
- Aucune écriture SQL ne passe, aucune colonne sensible ne sort pour le profil support.
- Les choix d'architecture (méthode de RAG, validation SQL, découpage des tools) sont justifiés dans le dossier de conception.

---

## Situation professionnelle

**Connecter les agents aux données de l'entreprise, de façon sécurisée**

*Besoin visé ou problème rencontré* — Un agent utile reste coupé des données de l'entreprise : bases SQL, sources multiples, base de connaissances. Il faut le brancher — proprement et sans tout exposer. La mission consiste à connecter l'agent aux données (SQL, multi-sources, RAG avancé) et à l'ouvrir au monde via MCP, de façon sécurisée.

## Compétences visées (18)

Chaque compétence est déclinée en 3 niveaux : *niveau 1 — imiter*, *niveau 2 — adapter*, *niveau 3 — transposer*.

- **C1.** Planifier le travail à effectuer individuellement
- **C2.** Contribuer au pilotage de l'organisation du travail individuel et collectif
- **C5.** Partager la solution adoptée en utilisant les moyens de partage de connaissance ou de documentation disponibles
- *(+ 7 compétences supplémentaires repliées sur la page Simplonline — le bouton « Afficher la totalité des compétences » n'a pas déplié la liste lors de l'extraction)*
