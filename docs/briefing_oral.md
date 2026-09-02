# Sorabel Data Gateway — dossier de briefing complet

> **À quoi sert ce fichier.** Il est autoportant : il contient tout le contexte, tous les
> chiffres mesurés, toutes les décisions et leurs justifications, sans supposer d'accès au
> dépôt. Il est destiné à être discuté à l'oral. Les schémas sont décrits en prose, pas en
> diagrammes, pour cette raison.
>
> **Statut du projet au 1er septembre 2026** : conception terminée sur les trois chantiers ;
> le chantier RAG est implémenté et fonctionne ; les chantiers Text-to-SQL et MCP ne sont pas
> codés. Aucun commit git à ce jour.

---

# PARTIE I — LE PROJET

## 1. Le contexte

Sorabel est un distributeur B2B de matériel électrique et d'outillage professionnel. Son
savoir vit dans deux mondes séparés :

- un **corpus documentaire** : fiches techniques, notices d'installation, procédures SAV,
  notes internes ;
- une **base SQL** : produits, stocks, clients, commandes, ventes.

Depuis un an, chaque équipe s'est bricolé son outil. Le support a un bot qui cherche mal dans
les PDF. Les commerciaux ont un script qui tape des requêtes SQL à la main — l'une d'elles a
verrouillé la base un vendredi soir. Les réponses divergent d'une équipe à l'autre.

La DSI gèle les bricolages et impose un point d'accès unique et gouverné : la **Sorabel Data
Gateway**, un serveur MCP que tous les outils internes consommeront.

## 2. Les six exigences imposées

| Code | Exigence |
|---|---|
| **E1** | Toute réponse documentaire cite ses sources (titre + référence + date) ; si le corpus ne couvre pas, l'outil le dit au lieu d'inventer. |
| **E2** | La recherche trouve aussi bien par référence exacte (« REF-8842 ») que par question en langage naturel (« quel disjoncteur pour du triphasé ? »). |
| **E3** | Tout SQL exécuté est en lecture seule, restreint aux tables autorisées du profil ; la requête générée est tracée avec son résultat. |
| **E4** | Un même serveur MCP sert tous les clients internes ; chacun n'accède qu'aux tools, collections et tables prévus par la matrice d'accès. |
| **E5** | Tout appel (autorisé ou refusé) est journalisé ; les colonnes sensibles (prix d'achat, marges) ne sortent jamais pour le profil support. |
| **E6** | Le gain de la recherche avancée sur la recherche simple est mesuré et documenté. |

## 3. Les tests d'acceptance à faire passer

**RAG** — une question couverte donne une réponse avec sources citées ; une question hors
corpus n'est pas inventée et le signale ; la recherche « REF-8842 » fait remonter la fiche
technique **en tête** ; le gain de l'hybride sur le dense est mesuré et documenté.

**Text-to-SQL** — « combien de commandes en avril ? » donne le bon résultat **avec la requête
SQL générée** ; « supprime les commandes de test » est refusé et journalisé ; le profil
support est refusé sur les marges et prix d'achat ; une question hors schéma est refusée au
lieu de produire du SQL halluciné.

**MCP** — un client n'accède qu'à ce que la matrice prévoit ; un appel non autorisé est
refusé avec un message clair et journalisé ; `search_docs` puis `get_document` fonctionnent
séparément ; le journal contient tous les appels de la démonstration.

---

# PARTIE II — LES DONNÉES, MESURÉES

> Tous les chiffres de cette partie proviennent de lectures de fichiers ou de requêtes SQL
> réellement exécutées, jamais d'estimation.

## 4. Le corpus documentaire — 400 documents

| Dossier | Volume | Format | Taille médiane | ≈ tokens |
|---|---|---|---|---|
| `fiches/` | 150 | PDF | 435 caractères | ~130 |
| `notices/` | 80 | PDF | 651 caractères | ~190 |
| `notes/` | 80 | Markdown | 309 caractères | ~90 |
| `sav/` | 90 | HTML | 851 caractères | ~250 |

**Le corpus est minuscule.** Le plus gros document fait environ 250 tokens. Aucun PDF ne
dépasse une page. C'est le fait le plus structurant du chantier RAG.

### Où se trouvent les métadonnées

| Type | Titre | Référence | Version | Date |
|---|---|---|---|---|
| Fiche | 1ʳᵉ ligne, après `FICHE TECHNIQUE - ` | **nom de fichier** | **nom de fichier** | ligne `Date :` |
| Notice | 1ʳᵉ ligne, après `NOTICE D'INSTALLATION - ` | **nom de fichier** | **nom de fichier** | ligne `Date :` |
| Note | front-matter YAML | regex sur le corps | front-matter | front-matter |
| SAV | balise `<title>` | regex sur le corps | balise `<meta>` | balise `<meta>` |

Les noms de fichiers suivent des motifs stricts : `REF-1024-v2.1.pdf`,
`notice-REF-1459-v1.0.pdf`, `proc-casse-transport-01-v2.0.html`.

### La découverte majeure : le corpus est massivement redondant

Mesure faite sur tous les fichiers, référence neutralisée :

- **les 80 notices ont un corps identique au mot près.** Toutes disent « 1. Consignes de
  sécurité / 2. Installation / 3. Mise en service / 4. Entretien » avec exactement le même
  texte. Seuls le titre et la référence les distinguent ;
- **les 150 fiches n'ont que 6 blocs de caractéristiques distincts.**

Trois conséquences qui gouvernent tout le chantier :

1. **Une recherche dense ne peut pas les départager.** « Comment installer ce produit ? »
   produit 80 vecteurs quasi identiques ; le classement entre eux est du bruit. Le corpus a
   été construit pour rendre l'hybride indispensable.
2. **L'en-tête contextuelle devient le seul discriminant réel** (voir §9).
3. **Dédoublonner par hachage du corps seul supprimerait 79 notices sur 80.** L'empreinte
   d'identité doit inclure titre, référence et date.

### Les versions multiples

Le corpus contient volontairement plusieurs versions d'un même document :
`REF-1024-v1.0.pdf` **et** `REF-1024-v2.1.pdf`, `proc-casse-transport-01-v1.0.html` **et**
`-v2.0.html`.

Décompte : 270 fichiers en v1.0, 10 en v1.1, 10 en v2.0, 30 en v2.1. Sur 350 groupes de
versions au total, **50 groupes ont plusieurs versions**.

### Les notes internes : cinq sous-types, dont deux confidentiels

Les 80 notes se répartissent en cinq sous-types de 16 notes chacun. Mesure du marqueur
« Diffusion restreinte » présent dans le corps :

| Sous-type | Volume | Mention « Diffusion restreinte » |
|---|---|---|
| `politique_tarifaire` | 16 | **16 sur 16** |
| `reunion_achat` | 16 | 0 sur 16 |
| `retour_terrain` | 16 | 0 sur 16 |
| `logistique` | 16 | 0 sur 16 |
| `alerte_qualite` | 16 | 0 sur 16 |

Exemple de note de politique tarifaire, texte intégral : *« Revue des prix de vente de la
catégorie Outillage à main. La marge cible reste fixée par la direction commerciale ; la
référence REF-4590 passe en revue au prochain comité. Diffusion restreinte. »*

Exemple de compte rendu de réunion achats : *« Négociation en cours avec Fixor : conditions
de remise sur volumes revues pour Visserie. Prochaine échéance contractuelle au trimestre
prochain. »*

**Point de vigilance décisif** : le sous-type n'apparaît **que dans le nom de fichier**. Le
front-matter YAML déclare `type: note_interne` pour les 80 notes indistinctement.

### Autres faits mesurés sur le corpus

- **Les fiches citent d'autres références.** Toutes se terminent par une ligne du type
  `Accessoires et produits associés : REF-6058, REF-5719`. Vérifié sur l'échantillon inspecté :
  20 fiches sur 20.
- **16 notes sur 80 ne citent aucune référence produit.** Le cas « référence absente » est
  structurel, pas marginal.
- **Les 90 procédures SAV citent toutes une référence, mais en exemple.** Elles disent
  « Applicable à tout le catalogue, exemple traité sur la référence REF-9196 ». Vérifié :
  90 sur 90 emploient cette formulation.
- **Chaque procédure SAV a exactement trois sections `<h2>`** : Conditions, Étapes, Cas hors
  périmètre. Il existe 10 familles de procédures (casse transport, duplicata de facture,
  diagnostic différentiel, disjoncteur qui déclenche, échange mauvaise référence, erreur de
  livraison, mise à jour d'adresse, panne de batterie, remplacement de charbons, retour
  produit défectueux).

## 5. La base SQL — 5 tables

Fichier `sorabel.db`, SQLite. Inspecté par connexion directe.

| Table | Lignes | Clé primaire | Clés étrangères |
|---|---|---|---|
| `produits` | 120 | `ref` TEXT (`REF-1024`) | — |
| `stocks` | 312 | `id` INTEGER | `ref` → `produits.ref` |
| `clients` | 60 | `id` TEXT (`CLI-1000`) | — |
| `commandes` | 340 | `id` TEXT (`CMD-2025-0004`) | `client_id` → `clients.id` |
| `ventes` | 993 | `id` INTEGER | `commande_id` → `commandes.id`, `ref` → `produits.ref` |

Colonnes de `produits` : `ref`, `nom`, `categorie`, `fabricant`, `unite`, `prix_vente_ht`,
`prix_achat_ht`, `marge_pct`, `actif`.
Colonnes de `ventes` : `id`, `commande_id`, `ref`, `quantite`, `prix_unitaire_ht`,
`remise_pct`, `marge_ht`.

### Le pivot entre les deux mondes est parfait

`SELECT ref FROM produits` donne 120 références. Les noms de fichiers de `corpus/fiches/`
donnent 120 références. **L'intersection vaut 120.** Zéro référence en base sans fiche
technique, zéro fiche sans produit en base.

C'est ce qui rend la Gateway cohérente : un tool qui croise fiche technique et stock réel est
fiable par construction.

### Les valeurs d'énumération réelles

| Colonne | Valeurs et effectifs |
|---|---|
| `commandes.statut` | `livree` (144), `annulee` (58), `expediee` (58), `en_attente` (44), `preparee` (36) |
| `clients.segment` | `grand compte` (21), `PME` (20), `artisan` (10), `collectivité` (9) |
| `stocks.entrepot` | `LYON` (108), `LILLE` (104), `NANTES` (100) |
| `produits.categorie` | 9 valeurs : Protection électrique, EPI, Câblage, Outillage électroportatif, Visserie, Outillage à main, Distribution, Éclairage, Mesure |

**Ces valeurs sont critiques.** Un modèle non informé génère `WHERE statut = 'livrée'` —
accentué, au féminin — et renvoie **zéro ligne sans lever d'erreur**. C'est le pire cas
possible : une réponse fausse qui ressemble à une réponse juste.

### Autres faits mesurés

- **Plage de dates** : du `2025-09-04` au `2026-08-19`. Un seul mois d'avril tombe dans la
  plage, donc « combien de commandes en avril ? » a une réponse unique : **27**. L'ambiguïté
  est apparente, pas réelle.
- `date_commande` est stockée en TEXT au format ISO, donc `strftime('%m', date_commande)`
  fonctionne directement.
- **`produits.actif` vaut 1 pour les 120 lignes.** Un filtre dessus ne change rien, mais un
  LLM l'ajoutera spontanément.
- **`sqlite_sequence` existe** — table interne de SQLite, à ne jamais exposer.

### Les colonnes sensibles de E5

`produits.prix_achat_ht`, `produits.marge_pct`, `ventes.marge_ht`. Exactement ces trois-là.

`produits.prix_vente_ht` n'est pas sensible : c'est un prix public, imprimé en clair sur les
fiches techniques (`Prix public HT : 15.75 EUR / pièce`).

---

# PARTIE III — CHANTIER 1 : LE RAG AVANCÉ

## 6. Le pipeline d'ingestion

Le flux, décrit de bout en bout : les fichiers sources de quatre formats passent par un
**extracteur dédié à chaque format**, qui produit un **document canonique** — un fichier JSON
unique par fichier source. Les canoniques alimentent ensuite un **manifeste global**, puis le
**chunking**, puis les deux index.

### Le document canonique

C'est le motif central du chantier. Quand N formats d'entrée doivent subir le même
traitement, on ne branche pas N pipelines : on les convertit tous vers une représentation
unique, et tout ce qui suit ne connaît que celle-là.

Un canonique contient : `doc_id`, `titre`, `type_document`, `reference`,
`references_citees`, `version`, `date`, `cle_groupe`, `source_path`, `hash_source`,
`hash_texte`, `extrait_le`, `schema_version`, `attributs`, `sections[]`, `qualite`.

Quatre bénéfices :

1. **Complexité confinée.** La connaissance des formats vit dans quatre extracteurs. Ajouter
   du DOCX demain, c'est un extracteur de plus et zéro changement ailleurs.
2. **Testabilité.** Chaque extracteur a le même contrat de sortie, testable isolément.
3. **Rejouabilité.** Changer la règle de chunking ou le modèle d'embedding ne relance pas
   l'extraction des 230 PDF.
4. **Débogage.** Quand une recherche donne un mauvais résultat, on lit le canonique et on
   sait immédiatement si le problème vient de l'extraction ou du retrieval. Sans cet état
   intermédiaire, on débogue à l'aveugle.

### La règle d'or : un canonique est une fonction pure de son fichier source

Rien dans un canonique ne doit dépendre des **autres** documents du corpus. Sinon l'arrivée
d'un nouveau fichier oblige à réécrire des canoniques dont la source n'a pas bougé, et le
cache devient impossible.

C'est pourquoi **`est_version_courante` n'est pas dans le canonique** : savoir si `v2.1` est
la version courante suppose de connaître toutes les autres versions de `REF-1024`. C'est une
propriété du corpus, pas du document.

### Le manifeste global

Les propriétés qui dépendent de l'ensemble du corpus vivent dans un fichier séparé,
`_manifeste.json`, recalculé à chaque ingestion. Pour chaque groupe de versions il donne :
la liste des versions, la version courante, le `doc_id` courant.

Le chunking lit canonique **plus** manifeste et écrit `est_version_courante` sur le chunk, là
où le filtre de recherche en a besoin. La donnée est dénormalisée à l'indexation, jamais à
l'extraction.

### Le cache à deux conditions

Un canonique est réutilisé tel quel si **les deux** conditions sont vraies :

- `hash_source` correspond au SHA-256 du fichier sur disque ;
- `schema_version` correspond à la version courante du code d'extraction.

Le second garde-fou est indispensable : sans lui, changer une règle d'extraction laisserait
des canoniques périmés en place, et on déboguerait sur des données obsolètes sans le voir.
Ce mécanisme a été prouvé en pratique — passer `SCHEMA_VERSION` de 1 à 2 a invalidé et
ré-extrait les 400 canoniques automatiquement.

### Deux hashs, deux rôles distincts

- `hash_source` : SHA-256 des **octets du fichier** → pilote le cache d'extraction.
- `hash_texte` : SHA-256 du **texte normalisé plus titre, référence et date** → détecte les
  vrais doublons.

Le second inclut les champs d'identité pour une raison mesurée, dans les deux sens : les
80 notices ont un corps identique et ne doivent pas être dédoublonnées ; deux notes d'alerte
qualité au même corps mais à deux dates différentes sont deux incidents distincts, pas un
doublon.

### Le rapport de qualité d'extraction

Sur 400 fichiers, certains s'extraient mal. **Sans détection, ils disparaissent
silencieusement de l'index** et personne ne s'en aperçoit avant la soutenance.

Cinq règles d'alerte : `texte_vide` (bloquant), `texte_court`, `aucune_section`,
`reference_absente` (bloquant), `date_absente`. L'ingestion produit un rapport lu **avant**
d'indexer. Un document `texte_vide` n'est pas indexé du tout.

**Résultat réel** : 400 documents traités, 400 indexables, zéro alerte, zéro doublon.

## 7. La gestion des versions

**Décision : on indexe toutes les versions, et on marque la plus récente.** Pas de
dédoublonnage destructif.

### Ce que « regroupement » veut dire exactement

Le corpus contient plusieurs fichiers qui sont **le même document à des versions
différentes**. Le regroupement sert uniquement à les rassembler pour savoir **laquelle est la
plus récente**. Il ne fusionne rien et ne supprime rien : chaque version reste un document
indexé à part entière.

Le groupe `fiche_technique:REF-1024` contient deux fichiers : `REF-1024-v1.0.pdf` (marqué
`est_version_courante = false`) et `REF-1024-v2.1.pdf` (marqué `true`). Les deux sont dans
l'index ; seul le second remonte par défaut.

**La clé de regroupement dépend du type**, parce que l'identité d'un document n'est pas
portée par le même champ partout :

| Type | Clé | Exemple |
|---|---|---|
| Fiche technique | `(référence, type)` | `fiche_technique:REF-1024` |
| Notice | `(référence, type)` | `notice:REF-1459` |
| Procédure SAV | `(**famille**, type)` | `procedure_sav:proc-casse-transport-01` |
| Note interne | aucune — pas de versions multiples | — |

Une procédure SAV n'a pas de référence produit : son identité est sa **famille**, extraite du
nom de fichier. Le piège serait de grouper sur le nom de fichier complet
(`proc-casse-transport-01-v2.0`) : chaque version formerait alors un groupe d'un seul membre,
donc **chaque version se croirait courante** et le filtre par défaut laisserait passer les
deux.

Le regroupement ne produit qu'une chose : le **manifeste**, qui dit pour chaque groupe quelles
versions existent et laquelle est courante. Le chunking lit ensuite ce manifeste pour écrire
`est_version_courante` sur chaque chunk, là où le filtre de recherche en a besoin.

**Mesuré** : 350 groupes au total, dont **50 contiennent plusieurs versions**. Les 300 autres
n'ont qu'un fichier, courant d'office.

La tentation est de supprimer la v1.0. C'est une erreur : la question « qu'est-ce qui a
changé entre les versions ? » est légitime, et une procédure SAV archivée peut devoir être
consultée pour un dossier ancien.

- Clé de regroupement : `(référence, type_document)` — ou `(famille, type)` pour le SAV, où
  `proc-casse-transport-01` est la famille, **pas** le nom de fichier complet.
- La recherche filtre sur `est_version_courante = true` **par défaut**.

Le problème du cadrage — « confond les versions d'une même notice » — n'est pas un problème
de stockage, c'est un problème de **filtre par défaut à la lecture**.

**On masque, mais on signale.** Chaque résultat porte `versions_anterieures: ["1.0"]`. Sans
ce signalement, l'utilisateur qui cherche une ancienne procédure ne trouve rien et ne
comprend pas pourquoi.

L'alternative — tout remonter trié par version — a été écartée : deux versions du même
document dans le top-3 envoyé au LLM seraient traitées comme deux sources indépendantes, et
leurs contenus contradictoires mélangés dans la réponse.

## 8. `reference` et `references_citees` : deux champs, pas un

Les fiches citent leurs accessoires. Avec un seul champ `reference`, chercher `REF-6058`
remonterait la fiche de `REF-1024` où cette référence n'apparaît qu'en accessoire — et le
test d'acceptance échouerait de façon aléatoire.

| Champ | Contenu | Usage |
|---|---|---|
| `reference` | la référence **sujet** du document | filtre strict |
| `references_citees` | les autres références mentionnées | boost, jamais filtre |

**Cas particulier des procédures SAV** : leur référence citée est toujours un exemple
(« Applicable à tout le catalogue, exemple traité sur REF-9196 »). Une procédure SAV n'a donc
**pas de référence sujet** : `reference` vaut `null` et tout part dans `references_citees`.
Sans cette distinction, chercher `REF-9196` remonterait une procédure générique de casse
transport comme si elle portait sur ce produit.

Chroma ne filtrant pas sur des listes, `references_citees` est stocké en chaîne
`"REF-6058|REF-5719"` et interrogé par `contains`.

## 9. Le chunking

### La règle générale

1. Découper sur les **frontières structurelles** — les sections du canonique.
2. Si une section dépasse **500 tokens**, la redécouper par paragraphes.
3. Si le résultat fait moins de **100 tokens**, le fusionner.

**Pourquoi 500** : le modèle e5 accepte 512 tokens en entrée. Au-delà, le texte est **tronqué
silencieusement** — la fin du chunk n'existe tout simplement pas dans le vecteur, sans
qu'aucune erreur ne soit levée. 500 laisse la place à l'en-tête contextuelle sous le plafond.

**Nuance importante sur la fusion** : c'est un **remplissage glouton jusqu'à 500 tokens**,
pas un simple recollage des sections sous 100. La différence est décisive : s'arrêter à 100
couperait une notice de 208 tokens en deux chunks de 100, alors que rien ne l'impose. Le
seuil qui contraint est le plafond du modèle, pas le plancher. Le plancher ne sert qu'à
garantir qu'aucun fragment isolé ne reste trop pauvre pour porter un vecteur discriminant.

### Ce que la règle donne sur ce corpus

Le document le plus long fait ~250 tokens. La règle de redécoupe ne se déclenche jamais, la
fusion s'applique partout. **Résultat : 400 documents donnent 400 chunks.** Longueur mesurée :
minimum 54 tokens, médiane 125, maximum 233.

Ce n'est pas un raccourci, c'est la règle appliquée à des données mesurées. Découper
davantage produirait des fragments trop pauvres. La règle générale reste écrite et
implémentée : elle se déclenchera le jour où un document plus long entrera dans le corpus.

### L'en-tête contextuelle

Chaque chunk est préfixé, **avant embedding**, par une en-tête fabriquée à partir des
métadonnées. Elle n'existe pas dans le document d'origine.

Exemple réel :

```
[Notice d'installation REF-1459 v1.0 — Projecteur led 30 W rechargeable]
Identification
Référence produit : REF-1459    Version : 1.0    Date : 2023-07-14
Consignes de sécurité
Couper l'alimentation générale avant toute intervention.
...
```

Sans elle, le corps d'une notice ne contient ni le nom du produit, ni la référence : il est
**identique** à celui des 79 autres notices. L'en-tête est le seul discriminant.

Le champ `texte` (avec en-tête) part à l'embedding et à l'index lexical ; `texte_brut` (sans)
est ce qu'on affiche à l'utilisateur et ce qu'on cite.

## 10. La chaîne de retrieval

### Les composants

- **Dense** : Chroma, modèle `intfloat/multilingual-e5-base`, 768 dimensions, similarité
  cosinus. Le modèle exige les préfixes `query: ` pour les questions et `passage: ` pour les
  chunks — il a été entraîné ainsi, les omettre dégrade nettement les scores.
- **Lexical** : BM25 en mémoire (`rank_bm25`), sur les mêmes chunks.
- **Fusion** : Reciprocal Rank Fusion, k = 60.
- **Rerank** : cross-encoder `BAAI/bge-reranker-v2-m3`.

### Le déroulé

La question passe d'abord par une regex `REF-\d{4}`. Si elle contient une référence, c'est
une information certaine — l'utilisateur l'a nommée, inutile de la deviner.

Ensuite, deux recherches en parallèle rendent chacune leurs 30 meilleurs candidats. Les deux
listes sont fusionnées par RRF. Le bonus de référence est appliqué. Les 30 candidats fusionnés
passent au cross-encoder, qui rend les 3 meilleurs. Si le score du meilleur est sous le seuil,
on refuse sans appeler le LLM.

### Pourquoi 30 et pas 3

C'est un entonnoir en deux temps. Le premier étage est bête mais rapide : il ratisse large
pour garantir que la bonne réponse est *quelque part* dans les 30. Le second est intelligent
mais lent : on ne peut pas le faire tourner sur 400 chunks à chaque question.

Si on prend 3 dès le départ, il n'y a plus rien à reranker — et si le bon chunk était 7ᵉ, il
est perdu définitivement. **Le rerank ne peut que réordonner ce qu'on lui donne, jamais
repêcher.**

### RRF expliqué

Formule : le score d'un document est la somme, sur chaque moteur, de `1 / (60 + rang)`.

Exemple concret. Un chunk A classé 5ᵉ par le dense et 1ᵉʳ par BM25 obtient
`1/65 + 1/61 = 0,0318`. Un chunk B classé 1ᵉʳ par le dense mais absent de BM25 obtient
`1/61 = 0,0164`. **A gagne** : deux moteurs le soutiennent, un seul soutient B.

**Pourquoi pas une somme pondérée des scores** : BM25 est non borné (0, 4, 27…), le cosinus
est borné. `0,5 × cosinus + 0,5 × bm25` n'a aucun sens — les échelles sont incomparables, et
il faudrait recalibrer à chaque changement de corpus ou de modèle. Les **rangs** sont toujours
1, 2, 3 : comparables par construction.

**À quoi sert le 60** : il amortit l'écart entre les premières places. Sans lui, le rang 1
vaut 1,0 et le rang 2 vaut 0,5 — 50 % d'écart entre deux voisins, ce qui donne un poids
démesuré au premier de chaque liste. Avec 60, on passe de 1/61 à 1/62, soit 1,6 % d'écart. Le
classement devient robuste au bruit. C'est la valeur de l'article d'origine (Cormack et al.,
2009), rarement retouchée.

### La détection de référence : filtre déguisé en bonus

Quand une référence est détectée, trois choses se produisent :

1. **Bonus fort (1,0) sur `reference`** — les documents dont c'est le sujet. Les scores RRF
   valant environ 0,016, un bonus mille fois supérieur agit **comme un filtre** : ils passent
   devant tout le reste.
2. **Bonus faible (0,1) sur `references_citees`** — les documents qui la citent en accessoire
   remontent sans passer devant.
3. **La recherche sémantique reste lancée sur tout le corpus.** Une note générale qui répond
   à la question sans citer la référence n'est pas perdue.

Ce troisième point évite le piège du filtre pur : « REF-8842 est-il compatible avec du
triphasé ? » peut trouver sa réponse dans un document qui ne nomme jamais REF-8842.

**Préférence de type sur référence seule** : si la question ne contient *rien d'autre* qu'une
référence, on privilégie la fiche technique puis la notice. Justification : une recherche
réduite à un identifiant vise le document principal du produit, pas une note qui le mentionne
en passant.

### Le pliage d'accents, côté lexical uniquement

Le corpus est intégralement accentué, les utilisateurs ne le seront pas toujours.
« endommagé » et « endommage » doivent produire le même token BM25. Le pliage s'applique des
deux côtés — index et requête — donc ne dégrade rien.

Il ne concerne **que** BM25 : côté dense, plier les accents du corpus appauvrirait le texte
embeddé, et e5 gère lui-même les variantes.

Détail de tokenisation important : `ref-8842` doit rester **un seul token**. Un découpage
naïf sur les caractères non alphanumériques le casserait en « ref » plus « 8842 », et ferait
perdre à BM25 exactement la précision qui justifie sa présence.

## 11. Ce que les mesures ont montré — et corrigé

> Cette section est celle qui donne le plus de matière à discussion : la conception initiale
> a été **contredite par la mesure** sur un point important.

### La thèse initiale, et pourquoi elle était trop absolue

La conception annonçait que le dense échouerait sur « REF-8842 », pour trois raisons :
tokenisation destructrice (`REF-8842` découpé en sous-tokens), voisinage écrasé (`REF-8842`
et `REF-8843` quasi colinéaires), et dilution (la référence noyée dans des centaines de mots).

**Le test sur l'index réel montre que le dense trouve.** Il place quatre documents REF-8842
dans son top-5.

**Pourquoi** : la dilution ne se produit pas ici. Les chunks font ~125 tokens et l'en-tête
contextuelle place la référence en tête. C'est une conséquence directe de nos propres
décisions de conception, pas une propriété du modèle. Sur un corpus de documents longs,
l'échec théorique se produirait.

### Ce que la mesure montre vraiment : les deux moteurs échouent différemment

Recherche « REF-8842 » :

| Rang | Dense (cosinus) | BM25 |
|---|---|---|
| 1 | 0,837 fiche REF-8842 | 6,74 **note « Point politique tarifaire »** |
| 2 | 0,832 fiche REF-8842 (v1.0) | 6,21 notice REF-8842 |
| 3 | 0,828 notice REF-8842 | 5,36 fiche REF-8842 |
| 4 | 0,823 note REF-8842 | 5,36 fiche REF-8842 (v1.0) |
| 5 | 0,817 fiche **REF-8264** (mauvaise référence) | 4,62 procédure SAV sans référence |

Deux échecs distincts, tous deux disqualifiants :

- **Le dense n'a pas de marge.** 0,837 contre 0,817 entre la bonne fiche et une référence
  *fausse* : 2 % d'écart. Ce n'est pas un classement, c'est du bruit ordonné. Aucun seuil de
  refus ne peut être calibré sur des scores aussi tassés — ce qui condamnerait E1.
- **BM25 met la mauvaise chose en tête.** Le premier résultat est une note interne, pas la
  fiche technique. BM25 normalise par la longueur : la note est plus courte et mentionne la
  référence, donc elle bat la fiche. Le test d'acceptance exige la **fiche technique** en
  tête — BM25 seul échoue.

Recherche « quel disjoncteur pour du triphasé ? » : le dense rend cinq fiches de disjoncteurs
pertinentes ; BM25 rend cinq procédures SAV au **même score exact de 3,75**, parce que leurs
corps sont identiques et qu'il est incapable de les départager.

### La conclusion révisée

L'argument n'est pas « le dense ne trouve pas ». Il est plus précis, et plus solide :

> **Chaque moteur a un mode de défaillance que l'autre n'a pas, et aucun des deux ne produit
> seul un classement exploitable sur les deux familles de questions exigées par E2.**

### Le bug du reranker — l'anecdote la plus instructive du projet

Premier reranker essayé : `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`. Résultat :

| Question | Score du meilleur résultat |
|---|---|
| « quel disjoncteur pour du triphasé ? » (couverte) | −6,02 |
| « comment traiter un colis endommagé ? » (couverte) | −6,03 |
| « quelle est la capitale de l'Australie ? » (**hors corpus**) | **−4,49** |

La question hors corpus scorait **plus haut** que les questions couvertes. Un seuil de refus
posé là-dessus aurait refusé les bonnes questions et accepté les mauvaises. Ce modèle a été
écarté : ses scores ne sont pas comparables d'une question à l'autre.

Passage à `BAAI/bge-reranker-v2-m3`. Les scores se sont mis à séparer correctement, mais le
classement restait faux sur certaines questions : « comment traiter un colis reçu
endommagé ? » remontait une note « Alerte qualité fournisseur » au lieu de la procédure SAV
correspondante — alors que l'hybride, **avant** rerank, plaçait les bonnes procédures aux
rangs 1 à 5. **Le reranker dégradait un classement parfait.**

**Cause** : Chroma stocke `texte_brut` dans son champ `documents`, c'est-à-dire le corps
**sans l'en-tête contextuelle**. Le reranker recevait donc le corps nu des procédures SAV —
du texte générique quasi identique d'une procédure à l'autre. Il lui manquait exactement le
titre qui les distingue.

L'en-tête avait été correctement injectée à l'embedding et dans BM25, et oubliée au troisième
endroit.

**Correction** : reconstruire l'en-tête à partir des métadonnées au moment du rerank, plutôt
que de dupliquer le texte complet dans l'index.

**Effet mesuré, mêmes questions** :

| Question | Avant | Après |
|---|---|---|
| « colis reçu endommagé ? » | 0,0011 → note « Alerte qualité » (faux) | **0,839 → Procédure SAV Colis endommagé** |
| « duplicata de facture » | 0,0048 → Procédure Diagnostic disjoncteur (faux) | **0,924 → Procédure Duplicata de facture** |

**Leçon générale** : l'en-tête contextuelle doit être présente **partout où un modèle lit le
chunk** — embedding, index lexical, et reranker. Sur un corpus dont les corps sont quasi
identiques, un modèle privé de l'en-tête juge des textes indiscernables.

### Le refus hors corpus fonctionne

État actuel, sur dix questions de contrôle :

| Type | Scores observés |
|---|---|
| 7 questions couvertes | de 0,274 à 0,996 — **7 sur 7 rendent le bon document en tête** |
| 3 questions hors corpus | 0,000018, 0,000020, 0,000078 |

Trois ordres de grandeur de séparation. Le seuil provisoire est fixé à 1e-4.

**Réserve honnête** : c'est un ordre de grandeur tiré de dix questions, pas une calibration.
La vraie calibration demande de tracer les deux distributions sur le jeu d'évaluation, encore
absent du dépôt.

## 12. Comment E1 est garantie

### Les citations

**Elles sont construites par le code, jamais demandées au LLM.** Un LLM à qui on demande de
citer invente des références ; un code qui lit `chunk.titre`, `chunk.reference`, `chunk.date`
ne peut pas.

Format imposé par E1 — titre, référence, date :
« Fiche technique — Disjoncteur différentiel tétrapolaire (REF-1024, v2.1, 2024-03-12) ».

La réponse structurée contient toujours `reponse` **et** `sources[]`, jamais l'un sans
l'autre.

### Le refus, en deux barrières

1. **Barrière de retrieval, déterministe.** Si le score du meilleur chunk après reranking est
   sous le seuil, on ne génère pas du tout. **Aucun appel LLM**, donc aucun risque
   d'hallucination.
2. **Barrière de génération.** Le prompt impose de répondre uniquement à partir des extraits
   fournis. Filet de sécurité si des chunks passent le seuil sans contenir la réponse.

Le refus est un **retour normal, pas une exception** : `{"statut": "hors_corpus", ...}`. Un
client doit pouvoir le distinguer d'une panne.

## 13. Le protocole d'évaluation (E6) — conçu, pas encore exécuté

Trois configurations sur le même index et les mêmes questions :

| Config | Description |
|---|---|
| **A — baseline** | dense seul |
| **B — hybride** | dense + BM25, fusion RRF |
| **C — hybride + rerank** | B suivi du cross-encoder |

**Le jeu de questions est scindé en deux, rapportés séparément** :

- questions par **référence exacte** — c'est là que le gain doit être spectaculaire, c'est ce
  qui prouve E2 ;
- questions en **langage naturel** — c'est là qu'il faut vérifier qu'on ne **dégrade pas** le
  dense en ajoutant le lexical.

Une moyenne globale masquerait exactement ce qu'on cherche à démontrer.

**Métriques** : Recall@5 (capacité à trouver), MRR (qualité du classement — la métrique
sensible au rerank, qui ne change pas le rappel mais le rang), Hit@1 (seule position
acceptable sur les questions par référence : le test dit « en tête », pas « dans les
résultats »).

Le livrable doit aussi analyser **les cas où l'hybride perd** — il y en aura, il faut les
nommer, pas les cacher.

**Attendu chiffré, compte tenu de la redondance du corpus** : sur les questions en langage
naturel visant une notice, la baseline dense devrait être proche du hasard.

---

# PARTIE IV — CHANTIER 2 : LE TEXT-TO-SQL

## 14. Ce qu'on donne au modèle

Un modèle ne peut pas deviner un schéma. La qualité de génération se joue entièrement dans le
contexte fourni, en quatre couches.

**a. Le schéma commenté, filtré par profil.** Pas un `CREATE TABLE` brut : un schéma annoté en
français où chaque colonne dit ce qu'elle signifie. Point clé : **le schéma est construit à
partir de la matrice d'accès, pas tronqué après coup.** Pour le profil support,
`prix_achat_ht` et `marge_pct` n'existent tout simplement pas dans le texte envoyé au modèle.
On ne peut pas générer du SQL sur une colonne qu'on ignore.

**b. Les valeurs types.** Les énumérations mesurées au §5, injectées littéralement. C'est le
garde-fou le moins cher du chantier.

**c. Des exemples question → SQL.** Trois à cinq paires. Leur rôle n'est pas d'apprendre le
SQL au modèle — il le connaît — mais de fixer les **conventions maison** : traitement des
dates en TEXT, casse des valeurs, forme attendue du résultat.

**d. Les règles de sortie.** Une seule requête, `SELECT` uniquement, pas de commentaire. Si la
question ne peut pas être traduite, le modèle doit répondre par un marqueur explicite plutôt
que par du SQL approximatif.

## 15. Les quatre barrières de lecture seule (E3)

Le brief demande « une seule barrière suffit-elle ? ». La réponse est non, et chaque barrière
a un mode de défaillance que les autres couvrent.

| # | Barrière | Ce qu'elle arrête | Son angle mort |
|---|---|---|---|
| 1 | **Connexion en lecture seule** — URI `file:sorabel.db?mode=ro` | toute écriture, même si tout le reste est contourné | une lecture légitime mais massive ou lente |
| 2 | **Validation de la requête générée** | `DROP`, `UPDATE`, `ATTACH`, `PRAGMA`, une 2ᵉ instruction après `;`, une table interdite | une requête valide qui ramène 993 lignes |
| 3 | **`LIMIT` par défaut** (200) | la réponse MCP qui explose, la fuite de masse | une requête lente |
| 4 | **Timeout d'exécution** | le produit cartésien qui verrouille la base | — |

**La barrière 1 est la seule vraiment infranchissable** : elle est appliquée par SQLite
lui-même, pas par notre code. Les autres protègent contre ce qu'elle laisse passer.

La barrière 4 n'est pas décorative : c'est exactement l'incident raconté dans le contexte du
brief, « l'une d'elles a verrouillé la base un vendredi soir ».

### La validation en détail

Liste noire seule est insuffisante — `SELECT` peut cacher `pragma_table_info()`, et une chaîne
peut contenir le mot `delete` sans que ce soit un ordre. On combine cinq contrôles :
normalisation (suppression des commentaires SQL), instruction unique, **liste blanche de
démarrage** (`SELECT` ou `WITH`), liste noire de mots-clés en position d'instruction, et
extraction des identifiants de tables vérifiés contre le périmètre.

**La liste blanche (2 formes autorisées) est plus sûre que la liste noire** (n formes
interdites, dont celles qu'on n'a pas prévues).

## 16. La restriction par profil, appliquée trois fois

| Moment | Mécanisme | Rôle |
|---|---|---|
| Avant génération | le schéma envoyé au modèle est déjà filtré | le modèle ignore l'existence de la colonne |
| Avant génération | **détection d'intention sensible** dans la question | refus explicite sans appel LLM |
| Après génération | le validateur vérifie tables et colonnes citées | rattrape ce que le modèle aurait inventé |

**Décision actée : refus explicite avant génération.** Profil support, question « quelle est
la marge sur REF-1024 ? » → refus immédiat, sans appel LLM.

Trois raisons de refuser tôt : le message est actionnable (« le profil support n'a pas accès
aux marges » plutôt que « la requête a été rejetée ») ; aucun appel LLM inutile ; et le test
d'acceptance dit « refusée selon la matrice d'accès », donc c'est littéralement un refus au
titre du profil.

La détection s'appuie sur un lexique par colonne sensible (marge, marges, taux de marge, prix
d'achat, coût d'achat, rentabilité…), volontairement **large** : un faux positif produit un
refus clair et récupérable, un faux négatif laisse fuiter une donnée sensible. **L'asymétrie
des conséquences dicte le réglage.**

La troisième barrière reste indispensable : les modèles connaissent les schémas plausibles et
peuvent référencer une colonne malgré son absence du schéma fourni.

## 17. Les quatre issues d'un appel

| Cas | Exemple | `statut` |
|---|---|---|
| Traduisible | « combien de commandes en avril ? » | `ok` + résultat + SQL |
| **Ambigu** | « quel est le meilleur client ? » | `ambigu` + interprétations |
| **Hors schéma** | « quel est le taux de satisfaction ? » | `hors_schema` + tables réelles |
| Interdit | « quelle marge sur REF-1024 ? » (support) | `non_autorise` + colonne |

**L'ambiguïté : demander, en proposant les options.** « Meilleur client » a au moins trois
lectures légitimes, toutes calculables : chiffre d'affaires total, nombre de commandes, marge
dégagée. Renvoyer les options plutôt qu'un simple « précisez » rend le refus utile — le client
relance sans deviner le vocabulaire attendu.

Choisir à la place du métier aurait été plus fluide et plus faux : sur « meilleur client », un
commercial et un directeur financier n'attendent pas la même colonne.

**Le hors schéma : refuser en disant ce qui existe.** Un modèle à qui on demande le taux de
satisfaction **inventera** une table `avis`. C'est le mode de défaillance le plus dangereux,
parce que la requête est plausible et l'erreur SQLite arrive trop tard, après avoir laissé
croire que la donnée existait. Le message nomme les cinq tables disponibles.

## 18. Tools figés ou SQL généré ? Les deux

| | Tool figé (`check_stock`, `order_status`) | Tool génératif (`ask_database`) |
|---|---|---|
| Requête | écrite à la main, paramétrée | produite par le LLM |
| Couverture | 1 besoin précis | tout le schéma |
| Fiabilité | **totale**, testable unitairement | dépend du modèle |
| Coût | quelques millisecondes, zéro LLM | un appel LLM |
| Sécurité | **aucune surface d'injection** : paramètre lié | 4 barrières nécessaires |

**Ce qui justifie un tool figé** : un besoin récurrent, à forme fixe, où une erreur coûte
cher. « Quel est le stock de REF-1024 ? » est posée cent fois par jour ; la faire passer par
un LLM, c'est payer un appel et accepter un risque pour une requête qu'on sait écrire.

**Ce qui justifie le génératif** : la longue traîne. On ne peut pas anticiper « quelle
catégorie a le meilleur taux de rupture à Lyon ? ». Sans `ask_database`, ces questions
retournent au tableur — c'est-à-dire au bricolage que la DSI vient de geler.

Le format strict des identifiants (`CMD-2025-0004`, `REF-1024`) permet de valider l'entrée
des tools figés **par regex avant d'atteindre la base**.

**`get_schema`** n'est ni figé ni génératif : c'est un tool d'aide qui renvoie le schéma tel
que le profil le voit. C'est aussi la démonstration la plus directe de E5 — le même appel
renvoie un schéma différent selon le profil.

---

# PARTIE V — CHANTIER 3 : MCP ET MATRICE D'ACCÈS

## 19. Les quatre profils

| Profil | Usage représenté | Besoin |
|---|---|---|
| `support` | bot Slack | répondre à un client : documentation, stock, statut de commande |
| `commercial` | poste commercial | analyse chiffrée, marges, négociation |
| `dev` | IDE des développeurs | comprendre le corpus et l'API, **sans lire les données de production** |
| `admin` | exploitation | accès total, diagnostic, démonstration du contraste |

**Un seul client sert les quatre profils.** `scripts/mcp_client.py` prend le profil en
argument (`--profil support`). Il n'y a pas quatre clients distincts.

Ce n'est pas une commodité de démonstration, c'est ce qui rend le contraste **prouvable** :
même code client, même serveur, même séquence d'appels — seul le profil change. Avec quatre
clients différents, on ne pourrait pas écarter l'hypothèse que la différence de réponse vient
du client plutôt que de la matrice.

Corollaire assumé : le profil étant déclaré par l'appelant, **ce n'est pas une
authentification**. C'est une limite à annoncer, pas à laisser découvrir.

## 20. Le catalogue : huit tools, deux niveaux

**RAG** : `answer_question` (réponse rédigée + sources), `search_docs` (extraits bruts +
scores), `get_document` (document complet), `list_sources` (inventaire).

**Données** : `ask_database` (génératif), `get_schema` (aide), `check_stock` (figé),
`order_status` (figé).

### Pourquoi exposer le RAG à deux niveaux

Ce n'est pas une redondance : ce sont deux contrats différents.

| | `answer_question` | `search_docs` + `get_document` |
|---|---|---|
| Rend | une réponse rédigée + sources | extraits bruts + scores + métadonnées |
| Coûte | un appel LLM | zéro appel LLM |
| Pour qui | bot Slack, poste commercial | **IDE** |
| Défaillance | le LLM reformule mal | aucune, le texte est celui du corpus |

Un développeur veut le passage exact d'une notice, pas une paraphrase. Le test d'acceptance
le formule : « les briques du RAG fonctionnent séparément ».

### Décrire les tools pour que le LLM du client choisisse le bon

Le client n'appelle pas nos tools : **son LLM les choisit** à partir de leur description. Une
description vague produit de mauvais choix, et le coupable est invisible côté serveur.

1. **Dire quand ne PAS l'utiliser.** « `search_docs` — recherche documentaire hybride.
   *N'utilisez pas ce tool pour obtenir une réponse rédigée : voyez `answer_question`.* »
2. **Distinguer les tools proches par leur déclencheur, pas leur mécanique.** `check_stock` :
   « quand la question porte sur une référence précise ». `ask_database` : « quand la question
   demande un calcul ou un agrégat ». Un LLM ne sait pas ce qu'est un « tool figé » ; il sait
   reconnaître une forme de question.
3. **Documenter les statuts de retour dans la description.** Un client qui sait que
   `hors_corpus` existe le gère ; un client qui l'apprend à l'exécution l'affiche comme une
   réponse.

## 21. Les collections ne sont pas les quatre dossiers

C'est le point le plus subtil du chantier. **E5 a une porte dérobée par le RAG.**

Le support n'a pas accès aux marges en SQL. Mais les 16 notes de politique tarifaire disent en
clair « la marge cible reste fixée par la direction commerciale » et portent toutes la mention
« Diffusion restreinte ». Sans restriction de collection, **le support lit en documentaire ce
qu'on lui refuse en relationnel**.

Les comptes rendus de réunion achats (« négociation en cours avec Fixor : conditions de remise
sur volumes ») ne portent pas le marqueur mais relèvent de la même sensibilité commerciale.
Leur classement est une **décision métier assumée**, pas une lecture des données.

D'où **cinq collections et non quatre** :

| Collection | Contenu | Volume |
|---|---|---|
| `fiches` | fiches techniques | 150 |
| `notices` | notices d'installation | 80 |
| `sav` | procédures SAV | 90 |
| `notes_operationnelles` | alerte qualité, logistique, retour terrain | 48 |
| `notes_confidentielles` | politique tarifaire, réunion achats | 32 |

**Dette identifiée sur le code déjà écrit** : l'extracteur de notes ne produit ni `sous_type`
(qui n'est que dans le nom de fichier) ni `diffusion_restreinte` (booléen tiré du corps). Sans
ces deux métadonnées, les collections ne sont pas séparables.

## 22. La matrice d'accès

### Profil × tool

| Tool | `support` | `commercial` | `dev` | `admin` |
|---|:---:|:---:|:---:|:---:|
| `answer_question` | oui | oui | **non** | oui |
| `search_docs` | oui | oui | oui | oui |
| `get_document` | oui | oui | oui | oui |
| `list_sources` | oui | oui | oui | oui |
| `ask_database` | oui *(restreint)* | oui | **non** | oui |
| `get_schema` | oui | oui | oui | oui |
| `check_stock` | oui | oui | non | oui |
| `order_status` | oui | oui | non | oui |

Deux refus à justifier, parce qu'ils ne sont pas des oublis :

- **`dev` n'a pas `answer_question`** : un IDE veut chercher sans générer, c'est le cas
  d'usage cité par le brief. Lui donner le tool génératif l'inciterait à payer un appel LLM
  pour un besoin qui n'en demande pas.
- **`dev` n'a aucun accès aux données réelles** : `get_schema` lui donne la forme, pas le
  contenu. Un environnement de développement n'a pas à contenir les commandes des clients.

Et un accès volontairement maintenu : **`support` conserve `ask_database`**. Sans lui, le test
d'acceptance « profil support, question sur les marges → refusée » ne pourrait pas s'exécuter.
Le refus doit se produire *dans* le tool, sur les colonnes.

### Profil × collections

| Collection | `support` | `commercial` | `dev` | `admin` |
|---|:---:|:---:|:---:|:---:|
| `fiches`, `notices`, `sav` | oui | oui | oui | oui |
| `notes_operationnelles` | oui | oui | non | oui |
| `notes_confidentielles` | **non** | oui | non | oui |

Le filtre s'applique **dans le retrieval**, comme une condition Chroma supplémentaire — pas en
post-traitement. Un document non autorisé ne doit jamais entrer dans le top-k, sans quoi il
occuperait la place d'un document légitime et dégraderait la réponse **tout en étant
invisible**.

### Profil × tables et colonnes

| | `support` | `commercial` | `dev` | `admin` |
|---|---|---|---|---|
| `produits` | oui **sauf** `prix_achat_ht`, `marge_pct` | oui | schéma seul | oui |
| `ventes` | oui **sauf** `marge_ht` | oui | schéma seul | oui |
| `stocks`, `clients`, `commandes` | oui | oui | schéma seul | oui |

### La forme de la matrice dans le code

Un fichier YAML déclaratif — pas des `if profil == "support"` dispersés. Trois bénéfices : la
matrice est **auditable sans lire le code** (la DSI peut la relire), un changement de droits
ne recompile rien, et le fichier lui-même est le livrable demandé.

## 23. Où la matrice est appliquée : les deux niveaux

| Niveau | Ce qu'il contrôle | Son angle mort |
|---|---|---|
| **Entrée du serveur** | le profil a-t-il droit à *ce tool* ? journalisation systématique | un tool appelé **en interne** ne repasse pas par l'entrée |
| **Dans chaque tool** | collections, tables, colonnes — le périmètre fin | aucun |

**L'angle mort du premier niveau est concret et c'est le meilleur argument du chantier** :
`answer_question` appelle le retrieval en interne. Si seul l'intercepteur d'entrée filtrait
les collections, un profil `support` obtiendrait une réponse rédigée **à partir d'une note
confidentielle, sans qu'aucun appel non autorisé n'apparaisse au journal**.

En pratique, la vérification fine est factorisée dans un objet `Perimetre` construit une fois
par appel et propagé au retrieval et au SQL. Les tools ne réimplémentent rien.

**Catalogue filtré** : `tools/list` ne renvoie que les tools autorisés. Le LLM du client ne
peut donc pas choisir un tool interdit. Cela ne remplace pas le contrôle à l'appel : le
catalogue filtré est une **commodité**, la vérification à l'appel est la **sécurité**.

## 24. Ce que renvoie un appel refusé

**Un refus n'est pas une panne.** Tous les refus sont des retours normaux portant un `statut`,
jamais des exceptions de protocole. Seules les défaillances techniques réelles (base
injoignable, index corrompu) remontent en erreur MCP.

| `statut` | Cause | Réaction attendue |
|---|---|---|
| `ok` | — | afficher |
| `hors_corpus` | score sous le seuil (E1) | « je ne sais pas », **pas** une réponse |
| `hors_schema` | table ou colonne inexistante | « cette donnée n'existe pas en base » |
| `ambigu` | plusieurs interprétations | relancer avec le critère choisi |
| `non_autorise` | matrice d'accès | « votre profil n'y a pas droit » |
| `refuse_ecriture` | tentative d'écriture SQL | incident de sécurité |
| `erreur` | panne technique | incident d'exploitation |

**Distinguer `hors_schema` de `non_autorise` est important et souvent négligé** : « la donnée
n'existe pas » et « vous n'y avez pas droit » appellent des actions opposées.

Un refus contient aussi un champ `alternative` (« `get_schema` donne la structure sans accéder
aux données »). Ce n'est pas de la politesse : ça évite que le LLM du client entre dans une
boucle de tentatives.

## 25. La journalisation (E5)

Une ligne JSON par appel, en ajout seul, dans `logs/appels.jsonl`.

Champs : `horodatage`, `profil`, `tool`, `autorise`, `statut`, `code`, `entrees`, `sql`,
`n_lignes`, `duree_ms`, `motif`.

| Champ | Pourquoi |
|---|---|
| `horodatage`, `profil`, `tool` | le minimum d'un audit |
| `autorise`, `statut`, `code` | distinguer refus de gouvernance et refus métier |
| `entrees` | rejouer l'appel à l'identique |
| `sql` | **E3** : transparence de la requête exécutée ou rejetée |
| `n_lignes`, `duree_ms` | détecter une fuite de masse ou une requête lente |
| `motif` | rendre le refus compréhensible sans relire le code |

**Le format JSONL est un choix.** Le test dit « quand on ouvre le journal » : un fichier
s'ouvre, se `grep`, se lit à l'œil en démonstration, et se charge en pandas. Une table SQLite
serait plus requêtable — mais écrire dans une base alors que tout le chantier 2 garantit la
lecture seule brouille le message.

**Ce qui n'est pas journalisé** : le contenu des résultats. On trace la question, la requête
et le volume, pas les lignes renvoyées — un journal ne doit pas devenir une copie de la base
sans les contrôles d'accès de la base.

## 26. La démonstration à deux profils

La même séquence rejouée sous `support` puis sous `commercial` :

| # | Appel | `support` | `commercial` |
|---|---|---|---|
| 1 | `search_docs("politique tarifaire")` | notes confidentielles **absentes** | présentes |
| 2 | `ask_database("quelle marge sur REF-1024 ?")` | `non_autorise` | `ok` + SQL + résultat |
| 3 | `ask_database("combien de commandes en avril ?")` | `ok` — 27 | `ok` — 27 |
| 4 | `ask_database("supprime les commandes de test")` | `refuse_ecriture` | `refuse_ecriture` |
| 5 | `get_schema()` | schéma **sans** `marge_pct` | schéma complet |
| 6 | `search_docs` puis `get_document` | briques séparées | briques séparées |

Puis on ouvre le journal : les douze appels y figurent.

**L'appel 4 est identique pour les deux profils** — aucun profil n'écrit, y compris `admin`.
La lecture seule n'est pas une restriction de profil, c'est une propriété de la Gateway.

---

# PARTIE VI — ÉTAT, DETTES, QUESTIONS OUVERTES

## 27. Ce qui est fait et ce qui ne l'est pas

| Brique | État |
|---|---|
| Conception des 3 chantiers | **terminée**, six documents |
| Ingestion → 400 canoniques | **fait** — 400/400 indexables, zéro alerte |
| Manifeste + rapport qualité | **fait** |
| Cache à deux conditions | **fait**, prouvé en pratique |
| Chunking + en-tête contextuelle | **fait** — 400 chunks |
| Index Chroma + BM25 | **fait** — 768 dimensions |
| Recherche dense / hybride / + rerank | **fait**, les 3 configs exécutables |
| Filtre de version, filtre + boost référence | **fait** |
| Seuil de refus | **fonctionne**, mais calibré sur 10 questions seulement |
| `answer_question` + citations | **pas commencé** |
| Évaluation E6 chiffrée | **bloquée** — jeu de questions absent |
| Text-to-SQL | **pas commencé** |
| Serveur MCP + matrice | **pas commencé** |
| Interface graphique (livrable) | **pas commencée** |
| Commits git | **aucun** |

## 28. Les dettes assumées

1. **`sous_type` et `diffusion_restreinte` ne sont pas produits** par l'extracteur de notes.
   Sans eux, les collections `notes_operationnelles` et `notes_confidentielles` ne sont pas
   séparables — donc la matrice n'a rien sur quoi filtrer.
2. **Le profil n'est pas authentifié.** Un profil déclaré par l'appelant lui-même n'est pas
   une authentification. Acceptable pour un exercice pédagogique, mais à **nommer comme
   limite** plutôt qu'à laisser découvrir.
3. **Le seuil de refus est un ordre de grandeur**, pas une calibration.
4. **Le gain de l'hybride n'est pas chiffré.** On a des exemples parlants, pas des métriques.
5. **Le modèle de génération SQL n'est pas choisi.** Le RAG tourne en local ; un appel API
   pour le SQL est un choix distinct à arbitrer (qualité contre reproductibilité en
   soutenance).
6. **Fichiers absents du dépôt** : `eval/questions_rag.jsonl`, `eval/questions_sql.jsonl`,
   `docs/cadrage_dsi.md`.

## 29. Les questions que le jury posera probablement

- **Pourquoi le dense rate-t-il « REF-8842 » ?** — Attention, piège : sur *ce* corpus, il ne
  le rate pas, et savoir pourquoi (en-tête contextuelle, chunks courts) vaut mieux que réciter
  la théorie. Le vrai argument est que ni le dense ni le lexical ne produisent seuls un
  classement exploitable.
- **Pourquoi RRF plutôt qu'une somme pondérée ?** — Les échelles de score sont incomparables ;
  les rangs ne le sont pas.
- **Une seule barrière de lecture seule suffit-elle ?** — Non, et chaque barrière a un angle
  mort nommé.
- **Où appliquez-vous la matrice, et pourquoi aux deux niveaux ?** — À cause des appels
  internes : `answer_question` → retrieval ne repasse pas par l'entrée.
- **Qu'est-ce qui garantit qu'un LLM n'invente pas une citation ?** — Les citations sont
  construites par le code depuis les métadonnées, jamais demandées au modèle.
- **Comment un client distingue-t-il un refus d'une panne ?** — Les refus sont des retours
  normaux avec un `statut` ; seules les pannes techniques lèvent une erreur de protocole.
- **Pourquoi indexer les vieilles versions ?** — Le problème n'est pas le stockage, c'est le
  filtre par défaut à la lecture. Et « qu'est-ce qui a changé entre v1 et v2 ? » est une
  question légitime.
- **Pourquoi 400 chunks pour 400 documents ?** — Parce que le corpus est plus court que la
  granularité cible. La règle générale est écrite et testée ; les données ne la déclenchent
  pas.

## 30. Les points sur lesquels une discussion serait utile

- Le **bonus de référence** (1,0 contre des scores RRF de 0,016) agit comme un filtre déguisé.
  Est-ce défendable, ou faudrait-il assumer un vrai filtre avec repêchage sémantique séparé ?
- La **préférence de type sur référence seule** (fiche technique privilégiée) est-elle une
  règle métier légitime, ou un ajustement pour faire passer un test d'acceptance ?
- Le **choix de `-base` plutôt que `-large`** pour l'embedding : 768 dimensions contre 1024.
  Sur un corpus où le lexical porte l'essentiel du signal, est-ce le bon arbitrage ?
- La **profondeur de 30 candidats** avant rerank n'est pas justifiée par une mesure. Elle
  devrait l'être par le Recall@30.
- Le **profil `dev` sans accès aux données** est-il réaliste, ou un développeur a-t-il besoin
  de données de test représentatives ?
- **Faut-il un cinquième profil** pour les questions transverses (un directeur commercial qui
  veut les marges *et* les notes confidentielles) ?
