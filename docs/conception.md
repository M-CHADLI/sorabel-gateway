# Dossier de conception

Les décisions, leurs raisons et les alternatives écartées, chantier par chantier. Pour l'état du code et les contrats entre paquets, voir `DOSSIER_TECHNIQUE.md`.

---

- [Chantier RAG avancé](#chantier-rag-avancé)
- [Chantier Text-to-SQL](#chantier-text-to-sql)
- [Chantier MCP et matrice d'accès](#chantier-mcp-et-matrice-daccès)

---

## Chantier RAG avancé

> Sorabel Data Gateway. Périmètre de ce document : la recherche documentaire uniquement
> (exigences E1, E2, E6). Text-to-SQL et exposition MCP traités séparément.

### 0. État du corpus (constaté, non supposé)

| Dossier | Volume | Format | Métadonnées disponibles |
|---|---|---|---|
| `corpus/fiches` | 150 | PDF | nom de fichier `REF-XXXX-vM.m.pdf` |
| `corpus/notices` | 80 | PDF | nom de fichier `notice-REF-XXXX-vM.m.pdf` |
| `corpus/notes` | 80 | Markdown | front-matter YAML (`titre`, `date`, `auteur`, `type`, `version`) |
| `corpus/sav` | 90 | HTML | `<title>` + balises `<meta>` version / date / type |

**Total : 400 documents.** Mesures faites sur l'intégralité du corpus (`pypdf`, `bs4`) :

| Type | Volume | Taille médiane | ≈ tokens | Structure |
|---|---|---|---|---|
| fiches | 150 | 435 car. | ~130 | 1 page, champs étiquetés |
| notices | 80 | 651 car. | ~190 | 1 page, sections numérotées `1.` `2.` |
| notes | 80 | 309 car. | ~90 | front-matter + 1 paragraphe |
| SAV | 90 | 851 car. | ~250 | exactement 3 `<h2>` |

Quatre faits déterminants, tous vérifiés :

1. **La référence et la version sont dans le nom de fichier** pour les 230 PDF.
   Aucune extraction de contenu n'est nécessaire pour les obtenir.
2. **Le corpus est très court.** Le plus gros document fait ~250 tokens. Aucun PDF ne
   dépasse une page. Conséquence directe sur le chunking (§2).
3. **Les fiches citent d'autres références** (`Accessoires et produits associés : REF-6058,
   REF-5719`) — vérifié sur l'intégralité de l'échantillon inspecté. Cela impose de
   distinguer la référence *sujet* du document de celles simplement *citées* (§1).
4. **16 notes sur 80 ne citent aucune référence produit.** Le cas `reference = null` est
   structurel, pas marginal.

#### Le corpus est massivement redondant — et c'est le fait le plus important

Mesure faite sur l'intégralité des fichiers, référence neutralisée :

| Mesure | Résultat |
|---|---|
| Corps distincts parmi les **80 notices** | **1** |
| Blocs de caractéristiques distincts parmi les **150 fiches** | **6** |

Les 80 notices sont identiques **au mot près** : « 1. Consignes de sécurité / 2. Installation
/ 3. Mise en service / 4. Entretien » avec exactement le même texte. Seuls le **titre** et la
**référence** les distinguent.

Trois conséquences majeures, qui orientent toute la suite du chantier :

1. **La recherche dense est structurellement incapable de les départager.** Une question
   « comment installer ce produit ? » produit 80 vecteurs quasi identiques ; le classement
   entre eux est du bruit. Aucun choix de modèle d'embedding n'y change rien. Le corpus a
   manifestement été construit pour rendre l'hybride indispensable — c'est E2 mis en scène.
2. **L'en-tête contextuelle n'est plus un raffinement, c'est le seul discriminant.** Sans
   titre ni référence injectés dans le texte embeddé, les 80 notices sont littéralement
   indistinguables. Cette décision (§2) devient critique.
3. **Le dédoublonnage par hachage du corps seul supprimerait 79 notices sur 80.** L'empreinte
   doit inclure titre, référence et date — ce sont eux qui portent l'identité du document,
   pas le corps.

Attendu chiffré pour l'éval (§5) : sur les questions en langage naturel visant une notice, la
baseline dense devrait être proche du hasard, et le gain de l'hybride spectaculaire.

### 1. Normalisation et gestion des versions

#### Le document canonique : un état intermédiaire persisté

L'ingestion ne va pas des fichiers sources aux chunks en une passe. Elle produit d'abord,
pour **chaque fichier source, un document canonique** — un fichier unique, de format unique,
écrit sur disque :

```
corpus/fiches/REF-1024-v2.1.pdf   ─┐
corpus/notes/note-2024-01-11-.md  ─┼─> normalisation ─> canonique/{doc_id}.json ─> chunking
corpus/sav/proc-casse-01-v1.0.html─┘
```

Un document canonique contient **le texte en Markdown + les métadonnées résolues**, et rien
d'autre. À partir de là, le reste du pipeline ne connaît plus ni PDF, ni HTML, ni YAML : un
seul format à traiter.

```json
{
  "schema_version": 1,
  "doc_id": "fiche_technique:REF-1024:v2.1",
  "titre": "Disjoncteur différentiel tétrapolaire 40 A",
  "reference": "REF-1024",
  "version": "2.1",
  "type_document": "fiche_technique",
  "date": "2024-03-12",
  "source_path": "data/data/corpus/fiches/REF-1024-v2.1.pdf",
  "hash_source": "9f2b...",
  "extrait_le": "2026-08-28T10:14:00",
  "qualite": { "statut": "ok", "alertes": [] },
  "sections": [
    { "titre": "Identification", "contenu": "..." },
    { "titre": "Caractéristiques", "contenu": "| Calibre | 40 A |\n| ... |" }
  ]
}
```

Trois raisons de le persister plutôt que de le garder en mémoire :

1. **Inspectable.** Quand une recherche donne un mauvais résultat, on lit le canonique et on
   sait immédiatement si le problème vient de l'extraction ou du retrieval. Sans cet état,
   on débogue à l'aveugle.
2. **Rejouable sans re-parser.** Changer la règle de chunking ou le modèle d'embedding ne
   doit pas relancer l'extraction des 230 PDF. On repart des canoniques.
3. **Frontière de responsabilité nette.** Un extracteur par format, avec un contrat de sortie
   identique. Chacun se teste isolément.

`get_document` sert d'ailleurs directement le canonique — pas le PDF d'origine.

##### Règle d'or : un canonique est une fonction pure de son fichier source

Rien dans un canonique ne doit dépendre des **autres** documents du corpus. Sinon l'arrivée
d'un nouveau fichier oblige à réécrire des canoniques dont la source n'a pas bougé, et le
cache devient impossible.

C'est pourquoi **`est_version_courante` n'est pas dans le canonique** : savoir si `v2.1` est
la version courante suppose de connaître toutes les autres versions de `REF-1024`. Cette
information est une propriété du corpus, pas du document.

##### Le manifeste global

Les propriétés qui dépendent de l'ensemble du corpus vivent dans un fichier à part,
`canonique/_manifeste.json`, recalculé à chaque ingestion :

```json
{
  "schema_version": 1,
  "genere_le": "2026-08-28T10:14:00",
  "groupes": {
    "fiche_technique:REF-1024": {
      "reference": "REF-1024",
      "versions": ["1.0", "2.1"],
      "version_courante": "2.1",
      "doc_id_courant": "fiche_technique:REF-1024:v2.1"
    },
    "procedure_sav:proc-casse-transport-01": {
      "famille": "proc-casse-transport-01",
      "versions": ["1.0", "2.0"],
      "version_courante": "2.0",
      "doc_id_courant": "procedure_sav:proc-casse-transport-01:v2.0"
    }
  }
}
```

Le chunking lit canonique + manifeste et **écrit `est_version_courante` sur le chunk**, où le
filtre Chroma en a besoin. La donnée est dénormalisée à l'indexation, jamais à l'extraction.

##### Cache : ne ré-extraire que ce qui a changé

Un canonique est réutilisé tel quel si **les deux** conditions sont vraies :

- `hash_source` correspond au SHA-256 du fichier sur disque — la source n'a pas bougé ;
- `schema_version` correspond à la version courante du code d'extraction.

Le second garde-fou est indispensable : sans lui, changer une règle d'extraction laisserait
des canoniques périmés en place et tu déboguerais sur des données obsolètes sans le voir.
On incrémente `schema_version` à chaque changement de règle, ce qui invalide tout le cache.

En pratique : première ingestion complète sur 400 fichiers, puis quasi instantanée.

##### Rapport de qualité d'extraction

Sur 400 fichiers, quelques-uns s'extrairont mal — PDF scanné sans couche texte, tableau
illisible, structure inattendue. **Sans détection, ils disparaissent silencieusement de
l'index** : la recherche ne les remonte jamais et personne ne s'en aperçoit avant la
soutenance.

Chaque canonique porte donc un bloc `qualite`, alimenté par des règles simples :

| Alerte | Déclencheur | Gravité |
|---|---|---|
| `texte_vide` | aucun texte extrait | bloquant |
| `texte_court` | < 200 caractères pour une fiche ou une notice | à vérifier |
| `aucune_section` | aucune frontière structurelle détectée | à vérifier |
| `reference_absente` | attendue (PDF) mais introuvable | bloquant |
| `date_absente` | aucune date exploitable | mineur |

L'ingestion produit `canonique/_rapport.md` : compteurs par type, liste des documents en
alerte, taux d'extraction réussie. **On le lit avant d'indexer.** Un document `texte_vide`
n'est pas indexé — un chunk vide pollue l'index sans jamais rien apporter.

#### Traitement par type de document

| | Fiche technique (150 PDF) | Notice (80 PDF) | Note interne (80 MD) | Procédure SAV (90 HTML) |
|---|---|---|---|---|
| **Source du titre** | 1re ligne, après `FICHE TECHNIQUE - ` | 1re ligne, après `NOTICE D'INSTALLATION - ` | front-matter `titre` | `<title>` |
| **Référence** | nom de fichier `REF-XXXX` | nom de fichier | **regex sur le corps** | regex sur le corps |
| **Version** | nom de fichier `vM.m` | nom de fichier | front-matter `version` | `<meta name="version">` |
| **Date** | ligne `Date : AAAA-MM-JJ` | idem | front-matter `date` | `<meta name="date">` |
| **Champs propres** | `Fabricant`, `Catégorie`, `Prix public HT` | — | `auteur`, `type` | — |
| **Clé de groupement** | `fiche_technique:REF-XXXX` | `notice:REF-XXXX` | aucune — pas de versions | `procedure_sav:proc-<famille>-<NN>` |
| **Sections détectées** | champs étiquetés (`Caractéristiques :`, liste à tirets) | titres numérotés `1.` `2.` `3.` `4.` | titres `##`, le plus souvent aucun | 3 `<h2>` : Conditions / Étapes / Cas hors périmètre |
| **Chunks produits** | **1** | **1** | **1** | **1** (cf. §2) |
| **Point de vigilance** | cite ses accessoires en `REF-XXXX` → `references_citees` | — | 16/80 sans aucune référence → `reference = null` | famille ≠ fichier : le groupement se fait sur `proc-casse-transport-01`, pas sur le nom complet |

##### `reference` et `references_citees` : deux champs, pas un

Toutes les fiches inspectées se terminent par une ligne du type :

```
Accessoires et produits associés : REF-6058, REF-5719
```

Avec un seul champ `reference`, chercher `REF-6058` remonterait la fiche de `REF-1024`, où
cette référence n'apparaît qu'en accessoire. Le test d'acceptance « la fiche technique
correspondante remonte en tête » échouerait de façon aléatoire.

| Champ | Contenu | Source | Usage |
|---|---|---|---|
| `reference` | la référence **sujet** du document | nom de fichier (PDF), regex du corps (notes/SAV) | filtre strict |
| `references_citees` | les autres références mentionnées | regex sur le corps, moins `reference` | boost, jamais filtre |

**Décision : filtre sur `reference`, boost sur `references_citees`.** La fiche dont
`REF-6058` est le sujet remonte en tête ; celles qui la citent en accessoire restent
accessibles, classées derrière. On garde ainsi la question « avec quoi ce produit est-il
compatible ? », qui est une vraie question du support, sans compromettre le test.

Chroma ne filtrant pas sur des listes, `references_citees` est stocké en chaîne
`"REF-6058|REF-5719"` et interrogé par `contains`.

##### Cas particuliers

- **Note sans référence.** 16 notes sur 80 n'en citent aucune (politique tarifaire,
  logistique). Elles sont indexées avec `reference = null` et restent retrouvables par le
  sémantique. On ne les jette pas, et on ne leur invente pas de référence.
- **Document dont la référence attendue est introuvable.** Pour un PDF, la référence vient du
  nom de fichier : son absence signale un fichier mal nommé → alerte `reference_absente`.

#### Versions multiples : ne pas dédoublonner, hiérarchiser

Le corpus contient volontairement `REF-1024-v1.0.pdf` **et** `REF-1024-v2.1.pdf`.
La tentation est de supprimer la v1.0. C'est une erreur : la question « qu'est-ce qui a
changé entre les versions ? » est légitime, et une procédure SAV archivée peut devoir être
consultée pour un dossier ancien.

**Décision : on indexe toutes les versions, et on marque la plus récente.**

- Clé de regroupement : `(référence, type_document)` — ou `(famille_procédure, type)` pour
  le SAV, où `proc-casse-transport-01` est la famille.
- Chaque chunk porte `version` (ex. `2.1`) et `est_version_courante` (booléen), calculé
  par tri sémantique de version sur le groupe.
- **Par défaut, la recherche filtre sur `est_version_courante = true`.** Un paramètre
  explicite permet de lever le filtre.

C'est ce qui répond au « confond les versions d'une même notice » du cadrage : le problème
n'est pas le stockage, c'est le **filtre par défaut à la lecture**.

Les vrais doublons (même contenu sous deux chemins) sont écartés par hash SHA-256 du **texte
normalisé** — à ne pas confondre avec `hash_source`, qui porte sur les octets du fichier
d'origine et sert au cache d'extraction. Deux hashs, deux usages distincts.

### 2. Granularité de chunk et métadonnées

#### Granularité retenue : un document = un chunk

Un chunking à taille fixe (512 tokens, overlap 50) est le réflexe par défaut, et il est
**mauvais ici** : il couperait une fiche technique au milieu de ses caractéristiques et
découperait en trois morceaux une note de quatre lignes qui est une unité de sens
indivisible.

Règle générale retenue :

1. Découper sur les **frontières structurelles** — les `sections[]` du document canonique.
2. Si une section dépasse **500 tokens**, la redécouper par paragraphes avec overlap.
3. Si une section fait moins de **100 tokens**, la fusionner avec la suivante.

**Pourquoi 500.** Le modèle e5 accepte 512 tokens en entrée : au-delà, le texte est **tronqué
silencieusement** — la fin du chunk n'existe tout simplement pas dans le vecteur, sans
qu'aucune erreur ne soit levée. 500 laisse la place à l'en-tête contextuelle sous le plafond.

##### Ce que cette règle donne sur ce corpus précis

Les mesures du §0 sont sans appel : le document **le plus long** du corpus fait ~250 tokens.
La règle 2 ne se déclenche jamais. La règle 3 fusionne systématiquement — les trois `<h2>`
d'une procédure SAV font ~85 tokens chacun, tous sous le seuil.

**Résultat : 400 documents → 400 chunks.**

Ce n'est pas un raccourci, c'est la règle appliquée à des données mesurées. Le corpus est
plus court que la granularité cible ; découper davantage produirait des fragments trop
pauvres pour porter un vecteur discriminant. La règle générale reste écrite et implémentée :
elle se déclenchera le jour où un document plus long entrera dans le corpus.

**Conséquence pratique** : le modèle chunk et le modèle document se confondent ici, et
l'en-tête contextuelle (§ suivant) devient d'autant plus importante — c'est le seul endroit
où le titre et la référence entrent dans le vecteur d'une section « Étapes ».

#### Enrichissement de chunk (contextualisation)

Chaque chunk est préfixé, **avant embedding**, par une en-tête générée :

```
[Fiche technique REF-1024 v2.1 — Disjoncteur différentiel tétrapolaire — section « Caractéristiques »]
<texte du chunk>
```

Sans cela, le chunk « Étapes » d'une procédure ne contient nulle part le mot « SAV » ni la
référence, et devient irretrouvable dès qu'on s'éloigne de ses termes exacts.

#### Modèle de chunk

| Champ | Type | Rôle |
|---|---|---|
| `chunk_id` | str | `{doc_id}#{index}`, stable entre deux ingestions |
| `doc_id` | str | `{type}:{référence}:v{version}` |
| `texte` | str | contenu indexé, en-tête contextuelle incluse |
| `texte_brut` | str | contenu sans en-tête, pour l'affichage et la citation |
| **`reference`** | str \| null | `REF-8842`, la référence **sujet** — **le champ décisif, cf. §3** |
| `references_citees` | str | `"REF-6058\|REF-5719"` — accessoires, **boost seulement** |
| `version` | str | `2.1` |
| `est_version_courante` | bool | filtre par défaut de la recherche |
| `type_document` | str | `fiche_technique` / `notice` / `note_interne` / `procedure_sav` |
| `titre` | str | pour la citation E1 |
| `date` | date | pour la citation E1, et pour départager deux versions |
| `section` | str | `Étapes`, `Caractéristiques`… |
| `source_path` | str | chemin fichier, pour `get_document` |
| `url` | str | lien consultable (E1) |
| `hash` | str | SHA-256, dédoublonnage |

#### Pourquoi `reference` est le champ décisif

Trois usages qu'aucun autre champ ne couvre :

1. **Filtre exact.** Une question contenant `REF-8842` devient une recherche par métadonnée,
   pas une recherche sémantique. C'est déterministe, à 100 % de précision.
2. **Regroupement des versions.** Sans elle, impossible de savoir que `v1.0` et `v2.1`
   parlent du même produit.
3. **Jointure future avec le SQL.** C'est la clé qui permettra de croiser la fiche technique
   et le stock réel. La référence est le pivot entre les deux mondes du projet.

### 3. Pourquoi ni le dense ni le lexical ne suffisent seuls

> Cette section a été **réécrite après mesure**. La rédaction initiale annonçait que la
> recherche dense échouerait à retrouver `REF-8842`. Le test sur l'index réel montre que ce
> n'est pas le cas sur ce corpus, pour une raison qui tient à nos propres choix de
> conception. Le raisonnement corrigé ci-dessous est plus solide que la version théorique,
> parce qu'il est adossé à des chiffres.

#### Le mécanisme théorique de l'échec dense

Un modèle d'embedding projette le texte dans un espace sémantique. Il est entraîné à
rapprocher les *sens* proches. Or `REF-8842` n'a **pas de sens** : c'est un identifiant
arbitraire. Trois défaillances sont attendues :

- **Tokenisation destructrice.** `REF-8842` est découpé en sous-tokens (`REF`, `-`, `88`,
  `42`). Le vecteur est dominé par le motif « ceci est une référence produit », pas par
  *laquelle*.
- **Voisinage écrasé.** `REF-8842` et `REF-8843` sont quasi colinéaires : sémantiquement,
  ils veulent dire la même chose.
- **Dilution.** Si le chunk contient plusieurs centaines de mots, la référence n'est qu'un
  token parmi d'autres et sa contribution au vecteur agrégé est marginale.

#### Ce que la mesure montre réellement

Recherche `REF-8842` sur l'index Chroma (400 chunks, `multilingual-e5-base`) :

| Rang | Dense (cosinus) | BM25 |
|---|---|---|
| 1 | **0,837** fiche REF-8842 | **6,74** note « Point politique tarifaire » (REF-8842) |
| 2 | 0,832 fiche REF-8842 (v1.0) | 6,21 notice REF-8842 |
| 3 | 0,828 notice REF-8842 | 5,36 fiche REF-8842 |
| 4 | 0,823 note REF-8842 | 5,36 fiche REF-8842 (v1.0) |
| 5 | 0,817 fiche **REF-8264** ✗ | 4,62 procédure SAV (aucune réf.) |

**Le dense trouve.** La troisième défaillance — la dilution — ne se produit pas ici : nos
chunks font ~125 tokens et l'en-tête contextuelle place la référence en tête. C'est une
**conséquence directe de nos décisions de conception** (§2), pas une propriété du modèle. Sur
un corpus de documents longs, l'échec théorique se produirait.

**Mais aucun des deux ne classe correctement.** Deux échecs distincts, tous deux
disqualifiants :

- **Le dense n'a pas de marge.** 0,837 contre 0,817 entre la bonne fiche et une référence
  *fausse* : 2 % d'écart. Ce n'est pas un classement, c'est du bruit ordonné. Aucun seuil de
  refus ne peut être calibré sur des scores aussi tassés — ce qui condamnerait E1.
- **BM25 met la mauvaise chose en tête.** Le premier résultat est une *note interne*, pas la
  fiche technique. BM25 normalise par la longueur du document : la note est plus courte et
  mentionne la référence, donc elle bat la fiche. Le test d'acceptance exige la **fiche
  technique** en tête — BM25 seul échoue.

#### Là où chacun est réellement supérieur

Recherche « quel disjoncteur pour du triphasé ? » :

| | Résultat |
|---|---|
| Dense | 5 fiches de disjoncteurs pertinentes ✓ |
| BM25 | 5 procédures SAV « disjoncteur qui déclenche », toutes au même score 3,75 ✗ |

BM25 s'effondre : il n'a aucun moyen de rapprocher « triphasé » de « tétrapolaire 400 V », et
il renvoie cinq documents au corps identique qu'il est incapable de départager.

#### Conclusion : l'hybride, mais pour la bonne raison

L'argument n'est pas « le dense ne trouve pas ». Il est plus précis :

> **Chaque moteur a un mode de défaillance que l'autre n'a pas, et aucun des deux ne produit
> seul un classement exploitable sur les deux familles de questions exigées par E2.**

Le dense apporte le rappel sémantique et une couverture correcte des références ; le lexical
apporte la séparation nette des scores sur les identifiants. La fusion (§ suivant) et le
rerank exploitent cette complémentarité. C'est ce que l'évaluation (§5) doit chiffrer.

#### Fusion : RRF plutôt que somme pondérée

Les scores BM25 (non bornés) et cosinus (bornés) ne sont pas comparables ; les normaliser
demande de recalibrer à chaque changement de corpus. On utilise **Reciprocal Rank Fusion**,
qui ne travaille que sur les rangs :

```
score_RRF(d) = somme sur i de  1 / (k + rang_i(d)),  i ∈ {dense, bm25},  k = 60
```

Un document bien classé par l'un des deux moteurs remonte, même si l'autre l'ignore.
Aucun paramètre à calibrer, robuste au changement de modèle.

#### Ce que le reranking ajoute par-dessus

L'hybride optimise le **rappel** : les ~30 bons candidats sont dans le lot. Il n'optimise pas
la **précision du top-3** — et c'est le top-3 qui part dans le prompt de génération.

Un **cross-encoder** lit `(question, chunk)` **ensemble** et produit un score de pertinence.
Il est bien plus juste qu'une comparaison de deux vecteurs calculés indépendamment, parce
qu'il voit les interactions terme à terme. Il est aussi bien plus lent — d'où l'ordre :
**hybride sur tout le corpus → 30 candidats → rerank de ces 30 → top-3.**

Bénéfice secondaire décisif : le score du reranker est **calibré et interprétable**, ce qui
en fait le bon seuil de refus pour E1 (§4).

#### Chaîne complète

#### Que déclenche exactement la détection de référence

La regex `REF-\d{4}` sur la question donne une information certaine. Elle est exploitée en
deux temps, et **pas comme un filtre unique** :

1. **Filtre strict sur `reference`** — les documents dont la référence est le sujet.
   Déterministe, 100 % de précision, garantit le test d'acceptance.
2. **Boost sur `references_citees`** — les documents qui la mentionnent en accessoire
   remontent dans le classement sans être filtrés, donc restent derrière les premiers.
3. **La recherche sémantique reste lancée sur tout le corpus** en parallèle. Une note
   générale qui répond à la question sans citer la référence n'est pas perdue.

C'est ce troisième point qui évite le piège du filtre pur : « REF-8842 est-il compatible avec
du triphasé ? » peut trouver sa réponse dans un document qui ne nomme jamais `REF-8842`.

```
question
  │
  ├─ détection de référence (regex REF-\d{4}) ──> filtre sur reference (strict)
  │                                           └─> boost sur references_citees
  │
  ├─ dense (Chroma, top 30) ────┐
  │                             ├──> RRF ──> 30 candidats ──> cross-encoder ──> top 3
  └─ BM25 (top 30) ─────────────┘                                                │
                                                                                 │
                       score_max < seuil ? ──oui──> REFUS motivé (E1)            │
                                            non──> génération + citations <──────┘
```

### 4. Garantir E1 : citations systématiques et refus

#### Citations

La citation n'est pas demandée au LLM, elle est **construite par le code** à partir des
métadonnées des chunks effectivement passés au prompt. Un LLM à qui on demande de citer
invente des références ; un code qui lit `chunk.titre`, `chunk.reference`, `chunk.date` ne
peut pas.

Format imposé par E1 — **titre + référence + date** :

> Fiche technique — Disjoncteur différentiel tétrapolaire (REF-1024, v2.1, 2024-03-12)

Chaque affirmation de la réponse renvoie à un marqueur `[1]`, `[2]` mappé sur la liste des
sources. La réponse structurée renvoyée par le tool contient toujours les deux champs
`reponse` et `sources[]`, jamais l'un sans l'autre.

#### Refus hors corpus

Deux barrières, dans cet ordre :

1. **Barrière de retrieval (déterministe).** Si le score du meilleur chunk après reranking
   est sous le seuil, on ne génère pas du tout. Aucun appel LLM, donc aucun risque
   d'hallucination. Le seuil est **calibré empiriquement** sur `questions_rag.jsonl` : on
   trace la distribution des scores des questions couvertes contre celles des questions non
   couvertes, et on place le seuil dans la séparation. Ce n'est pas une constante magique,
   c'est une mesure.
2. **Barrière de génération.** Le prompt impose : « Réponds uniquement à partir des extraits
   fournis. Si les extraits ne permettent pas de répondre, dis-le explicitement. » Filet de
   sécurité pour le cas où des chunks passent le seuil sans contenir la réponse.

Le refus est un **retour normal, pas une erreur** :
`{ "statut": "hors_corpus", "message": "...", "sources": [] }`.
Un client MCP doit pouvoir le distinguer d'une panne.

### 5. Mesurer le gain (E6)

#### Protocole

Trois configurations évaluées sur le **même jeu de questions**, avec le même corpus indexé :

| Config | Description |
|---|---|
| **A — baseline** | dense seul (Chroma, cosinus) |
| **B — hybride** | dense + BM25, fusion RRF |
| **C — hybride + rerank** | B suivi d'un cross-encoder |

#### Découpage du jeu de questions

`questions_rag.jsonl` est scindé en deux sous-ensembles, **rapportés séparément** :

- **Questions par référence exacte** (« REF-8842 ») — c'est là que le gain de l'hybride doit
  être spectaculaire. C'est le sous-ensemble qui prouve E2.
- **Questions en langage naturel** — c'est là qu'il faut vérifier qu'on ne **dégrade pas** le
  dense en ajoutant le lexical.

Une moyenne globale masquerait exactement ce qu'on cherche à démontrer. Le tableau final doit
avoir ces deux colonnes.

#### Métriques

- **Recall@5** : le bon document est-il dans les 5 premiers ? Mesure la capacité à trouver.
- **MRR** (rang réciproque moyen) : à quelle position ? Mesure la qualité du classement —
  c'est la métrique sensible au reranking, qui ne change pas le rappel mais le rang.
- **Hit@1** : sur les questions par référence, seule position acceptable. Le test
  d'acceptance dit « remonte **en tête** des résultats », pas « dans les résultats ».

#### Livrable

`eval/rapport_eval.md` : tableau 3 configs × 3 métriques × 2 sous-ensembles, plus l'analyse
des cas où l'hybride perd — il y en aura, il faut les nommer, pas les cacher. Le script
`eval/run_eval.py` doit être rejouable en une commande pour la soutenance.

### 6. Tools MCP issus de ce chantier

| Tool | Entrée | Sortie | Garantie |
|---|---|---|---|
| `answer_question` | `question`, `collections?` | `reponse`, `sources[]`, `statut` | Cite toujours ses sources ; refuse hors corpus (E1) |
| `search_docs` | `requete`, `k?`, `filtres?` | `resultats[]` : chunk + score + métadonnées | Hybride + rerank ; classe la réf exacte en tête (E2) |
| `get_document` | `doc_id`, ou `reference` + `version?` | document complet + métadonnées | Sert la version courante par défaut |
| `list_sources` | `type_document?`, `reference?` | inventaire filtrable des documents indexés | Reflète l'index, pas le disque |

**`list_sources` — les usages qui le justifient.** Le tool ne se contente pas de lister ; il
répond à trois besoins réels, sans quoi il n'aurait pas sa place au catalogue.

1. **Vérifier la couverture avant de chercher.** « Avez-vous une notice pour REF-8842 ? » est
   une question d'inventaire, pas de recherche sémantique. Y répondre par un `search_docs`
   qui renvoie des documents peu pertinents est pire que de répondre « non ».
2. **Explorer une catégorie.** « Quelles procédures SAV existent ? » — les 10 familles, sans
   passer par une requête en langage naturel.
3. **Démontrer le périmètre par profil** (chantier MCP) : le même appel renvoie un inventaire
   différent selon la matrice d'accès. C'est la façon la plus lisible de prouver E4.

Il renvoie aussi, par groupe, les `versions` disponibles — la source du signalement décrit
ci-dessous.

#### Signalement des versions antérieures

La recherche filtre sur `est_version_courante = true` par défaut. Masquer sans le dire
produit une impasse : l'utilisateur qui cherche une ancienne procédure ne trouve rien et ne
comprend pas pourquoi.

**Décision : on masque, mais on signale.** Chaque résultat porte
`versions_anterieures: ["1.0"]`, lu dans `_manifeste.json`. Le client sait qu'il peut
appeler `get_document(reference, version="1.0")` ou relancer la recherche avec
`inclure_versions_anciennes: true`.

L'alternative — tout remonter trié par version décroissante — a été écartée : deux versions
du même document dans le top-3 envoyé au LLM seraient traitées comme deux sources
indépendantes, et leurs contenus contradictoires mélangés dans la réponse.

`answer_question` sert les clients qui veulent une réponse rédigée (bot Slack du support).
`search_docs` + `get_document` servent les clients qui veulent **chercher sans générer** — un
IDE de développeur veut les extraits bruts, pas une prose de LLM. C'est le test d'acceptance
MCP « les briques du RAG fonctionnent séparément ».

### 7. Décisions techniques

| Choix | Décision | Justification |
|---|---|---|
| Vector store | **Chroma** | Imposé par le brief ; filtrage par métadonnées natif, indispensable au filtre `est_version_courante` et au filtre par référence |
| Embeddings | multilingue local (`multilingual-e5` ou `BGE-m3`) | Corpus 100 % français ; local = reproductible en soutenance, sans clé API |
| Lexical | BM25 en mémoire | 400 documents : aucun besoin d'un moteur externe |
| Reranker | cross-encoder multilingue local | Appliqué à 30 candidats seulement, coût maîtrisé |
| Fusion | RRF, k = 60 | Pas de calibration de scores hétérogènes |

### Points ouverts

- **Seuil de refus** : à calibrer une fois `eval/questions_rag.jsonl` disponible. Seul point
  bloquant restant, et il ne bloque que l'étape E1/E6, pas l'ingestion.
- **Profondeur du premier étage (top 30)** : valeur de départ. À régler sur le Recall@30
  mesuré par l'éval — si le rappel plafonne, aucun rerank ne rattrapera les candidats perdus.

Résolus depuis la rédaction initiale : structure des PDF (mesurée, §0), granularité de chunk
(§2), traitement des références citées (§1), signalement des versions (§6).

---

## Chantier Text-to-SQL

> Sorabel Data Gateway. Périmètre : l'accès aux données relationnelles en langage naturel
> (exigences E3, E5). Le RAG est traité dans `conception_rag.md`, l'exposition MCP et la
> matrice d'accès dans `conception_mcp.md`.

### 0. État de la base (constaté, non supposé)

`data/data/sorabel.db` — SQLite, 5 tables métier.

| Table | Lignes | Clé | Liens |
|---|---|---|---|
| `produits` | 120 | `ref` TEXT | ← `stocks.ref`, `ventes.ref` |
| `stocks` | 312 | `id` INTEGER | → `produits.ref` |
| `clients` | 60 | `id` TEXT (`CLI-1000`) | ← `commandes.client_id` |
| `commandes` | 340 | `id` TEXT (`CMD-2025-0004`) | → `clients.id` |
| `ventes` | 993 | `id` INTEGER | → `commandes.id`, → `produits.ref` |

#### Faits mesurés qui changent la conception

**1. Le pivot `produits.ref` est une bijection parfaite avec le corpus.** 120 références en
base, 120 fiches techniques, **intersection = 120**, zéro orphelin dans les deux sens. Un
tool qui croise fiche technique et stock réel est fiable par construction, pas par chance.
C'est ce qui rend la Gateway cohérente : les deux mondes parlent le même langage.

**2. Les valeurs d'énumération sont peu nombreuses et connues.** Elles doivent entrer telles
quelles dans le prompt — c'est ce que le brief appelle « valeurs types » :

| Colonne | Valeurs réelles |
|---|---|
| `commandes.statut` | `annulee`, `en_attente`, `expediee`, `livree`, `preparee` |
| `clients.segment` | `PME`, `artisan`, `collectivité`, `grand compte` |
| `stocks.entrepot` | `LILLE`, `LYON`, `NANTES` |
| `produits.categorie` | 9 valeurs (`Protection électrique`, `EPI`, `Câblage`…) |

Sans elles, un modèle génère spontanément `WHERE statut = 'livrée'` — accentué, au féminin —
et renvoie **zéro ligne sans erreur**. C'est le pire cas possible : une réponse fausse qui
ressemble à une réponse juste. Les valeurs sont le garde-fou le moins cher du chantier.

**3. Les dates couvrent `2025-09-04` → `2026-08-19`.** Un seul mois d'avril tombe dans la
plage. Le test d'acceptance « combien de commandes en avril ? » a donc **une seule réponse
possible : 27**. L'ambiguïté est apparente, pas réelle — inutile de demander une précision.
`date_commande` est stockée en TEXT ISO, donc `strftime('%m', date_commande) = '04'`
fonctionne directement.

**4. `produits.actif` vaut 1 pour les 120 lignes.** Un filtre dessus ne change rien, mais un
LLM l'ajoutera spontanément par prudence. Sans conséquence ici — à savoir pour ne pas
s'inquiéter en lisant les requêtes générées.

**5. `sqlite_sequence` existe.** Table interne de SQLite. Elle ne doit jamais apparaître dans
le schéma exposé au modèle ni dans `get_schema` : c'est du bruit qui invite à l'erreur.

#### Colonnes sensibles (E5)

| Colonne | Nature |
|---|---|
| `produits.prix_achat_ht` | prix d'achat fournisseur |
| `produits.marge_pct` | taux de marge |
| `ventes.marge_ht` | marge en valeur |

Elles ne sortent **jamais** pour le profil support. Le corpus documentaire contient
`Prix public HT` sur les fiches — c'est un prix de vente, public par nature : il n'est pas
sensible et n'a pas à être filtré.

### 1. De la question à la requête : ce qu'on donne au modèle

Un modèle ne peut pas deviner un schéma. La qualité de génération se joue entièrement dans
le contexte fourni, en quatre couches.

#### a. Le schéma commenté, filtré par profil

Pas un `CREATE TABLE` brut : un schéma annoté en français, où chaque colonne dit ce qu'elle
signifie et non seulement son type.

```sql
-- produits : catalogue. `ref` est la référence commerciale (REF-XXXX),
--            elle sert aussi de clé vers le corpus documentaire.
CREATE TABLE produits (
  ref            TEXT PRIMARY KEY,  -- 'REF-1024'
  nom            TEXT,              -- libellé commercial
  categorie      TEXT,              -- Protection électrique | EPI | Câblage | …
  fabricant      TEXT,
  unite          TEXT,              -- pièce | conditionnement
  prix_vente_ht  REAL,              -- prix public HT
  actif          INTEGER            -- 1 = au catalogue (vaut 1 partout aujourd'hui)
);
```

**Le schéma est construit à partir de la matrice d'accès, pas tronqué après coup.** Pour le
profil support, `prix_achat_ht` et `marge_pct` n'existent tout simplement pas dans le texte
envoyé au modèle. On ne peut pas générer du SQL sur une colonne qu'on ignore — c'est la
première des barrières E5, et la moins coûteuse.

#### b. Les valeurs types

Les énumérations du §0, injectées littéralement. C'est ce qui évite `'livrée'` au lieu de
`livree`.

#### c. Des exemples de requêtes (few-shot)

Trois à cinq paires question → SQL couvrant les formes attendues : agrégat simple, filtre
temporel, jointure, group by.

```
Q : combien de commandes en avril ?
S : SELECT COUNT(*) FROM commandes WHERE strftime('%m', date_commande) = '04';

Q : quel est le stock de REF-1024 ?
S : SELECT entrepot, quantite FROM stocks WHERE ref = 'REF-1024';
```

Leur rôle principal n'est pas d'apprendre le SQL au modèle — il le connaît — mais de fixer
**les conventions maison** : le traitement des dates en TEXT, la casse des valeurs, la forme
attendue du résultat.

#### d. Les règles de sortie

Une seule requête, `SELECT` uniquement, pas de point-virgule multiple, pas de commentaire.
Si la question ne peut pas être traduite, le modèle doit répondre par un marqueur explicite
plutôt que par du SQL approximatif — cf. §4.

### 2. Lecture seule : quatre barrières (E3)

**Une seule barrière ne suffit pas**, et la question du brief est rhétorique. Chaque barrière
a un mode de défaillance que les autres couvrent.

| # | Barrière | Ce qu'elle arrête | Ce qu'elle **ne** peut **pas** arrêter |
|---|---|---|---|
| 1 | **Connexion en lecture seule** — `sqlite3.connect("file:sorabel.db?mode=ro", uri=True)` | toute écriture, même si tout le reste est contourné | une lecture légitime mais hors périmètre, ou un produit cartésien |
| 2 | **Validation de la requête générée** — une seule instruction, doit commencer par `SELECT`/`WITH`, mots-clés d'écriture interdits, tables et colonnes vérifiées contre le périmètre du profil | `DROP`, `UPDATE`, `ATTACH`, `PRAGMA`, l'accès à une table interdite, l'injection d'un second ordre après `;` | une requête `SELECT` valide et autorisée qui ramène 993 lignes |
| 3 | **`LIMIT` par défaut** — injecté si absent (200 lignes) | la réponse MCP qui explose, la fuite de masse | une requête lente |
| 4 | **Timeout d'exécution** | le produit cartésien qui bloque la base | — |

La barrière 1 est la seule vraiment infranchissable : elle est appliquée par SQLite
lui-même, pas par notre code. Les autres protègent contre ce qu'elle laisse passer.

La barrière 4 n'est pas décorative : c'est exactement l'incident raconté dans le contexte du
brief — « l'une d'elles a verrouillé la base un vendredi soir ».

#### Validation : liste de mots interdits ou analyse ?

Une liste noire (`DROP`, `DELETE`, `INSERT`…) est insuffisante seule — `SELECT` peut cacher
`pragma_table_info()`, et une chaîne peut contenir le mot `delete` sans que ce soit un ordre.
On combine :

1. **normalisation** : suppression des commentaires SQL, réduction des espaces ;
2. **instruction unique** : refus si plus d'une instruction après découpage sur `;` ;
3. **liste blanche de démarrage** : la requête doit commencer par `SELECT` ou `WITH` ;
4. **liste noire de mots-clés** en position d'instruction ;
5. **extraction des identifiants de tables** et vérification contre le périmètre du profil.

La liste blanche (4 formes autorisées) est plus sûre que la liste noire (n formes
interdites, dont celles qu'on n'a pas prévues).

### 3. Restreindre tables et colonnes par profil (E5)

La restriction s'applique **trois fois**, à trois moments différents.

| Moment | Mécanisme | Rôle |
|---|---|---|
| Avant génération | le schéma envoyé au modèle est déjà filtré | le modèle ignore l'existence de la colonne |
| Avant génération | **détection d'intention sensible** dans la question | refus explicite sans appel LLM |
| Après génération | le validateur vérifie tables et colonnes citées | rattrape ce que le modèle aurait inventé |

#### Le refus explicite avant génération

Décision actée : profil support, question « quelle est la marge sur REF-1024 ? » →
**refus avant toute génération**.

```json
{
  "statut": "non_autorise",
  "message": "Le profil support n'a pas accès aux marges ni aux prix d'achat.",
  "colonnes_refusees": ["produits.marge_pct"],
  "sql": null
}
```

Trois raisons de refuser tôt plutôt que de laisser générer puis bloquer :

1. **Le message est exploitable.** « Le profil support n'a pas accès aux marges » est
   actionnable ; « la requête générée a été rejetée » ne l'est pas.
2. **Aucun appel LLM inutile.**
3. **Le test d'acceptance dit « refusée selon la matrice d'accès »** — c'est littéralement
   un refus au titre du profil, pas un rejet de requête.

La détection s'appuie sur un lexique par colonne sensible (`marge`, `marges`, `taux de
marge`, `prix d'achat`, `coût d'achat`, `rentabilité`…). Elle est volontairement **large** :
un faux positif produit un refus clair et récupérable, un faux négatif laisse fuiter une
donnée sensible. L'asymétrie des conséquences dicte le réglage.

La troisième barrière reste indispensable : elle rattrape le cas où le modèle référence une
colonne malgré son absence du schéma — ça arrive, les modèles connaissent les schémas
plausibles.

### 4. Questions ambiguës ou hors schéma

Trois issues distinctes, que le client doit pouvoir différencier. **Aucune n'est une
exception** : ce sont des retours normaux avec un `statut`.

| Cas | Exemple | `statut` | Contenu |
|---|---|---|---|
| Traduisible | « combien de commandes en avril ? » | `ok` | résultat + SQL exécuté |
| **Ambigu** | « quel est le meilleur client ? » | `ambigu` | interprétations proposées |
| **Hors schéma** | « quel est le taux de satisfaction ? » | `hors_schema` | ce que la base contient |
| Interdit | « quelle marge sur REF-1024 ? » (support) | `non_autorise` | colonne refusée |

#### L'ambiguïté : demander, en proposant les options

Décision actée. « Meilleur client » a au moins trois lectures légitimes, et les trois sont
calculables :

```json
{
  "statut": "ambigu",
  "message": "« Meilleur » peut vouloir dire plusieurs choses. Précisez le critère.",
  "interpretations": [
    "chiffre d'affaires total (SUM(commandes.montant_ht))",
    "nombre de commandes (COUNT(commandes.id))",
    "marge dégagée (SUM(ventes.marge_ht)) — profil commercial uniquement"
  ]
}
```

Renvoyer les options plutôt qu'un simple « précisez » est ce qui rend le refus utile : le
client relance immédiatement sans deviner le vocabulaire attendu. Et proposer une
interprétation réservée au profil commercial rappelle la matrice sans la contourner.

Choisir à la place du métier aurait été plus fluide et plus faux : sur « meilleur client »,
un commercial et un directeur financier n'attendent pas la même colonne.

#### Le hors schéma : refuser en disant ce qui existe

Un modèle à qui on demande le taux de satisfaction **inventera** une table `avis` — c'est le
mode de défaillance le plus dangereux, parce que la requête générée est plausible et
l'erreur SQLite arrive trop tard, après avoir laissé croire que la donnée existait.

La détection est faite **après génération** : si le validateur rencontre une table ou une
colonne absente du schéma réel, on ne tente pas d'exécuter. Le message nomme les 5 tables
disponibles.

### 5. Tools figés ou SQL généré ?

Les deux, pour des raisons différentes. Ce n'est pas une redondance.

| | Tool figé (`check_stock`, `order_status`) | Tool génératif (`ask_database`) |
|---|---|---|
| Requête | écrite à la main, paramétrée | produite par le LLM |
| Couverture | 1 besoin précis | tout le schéma |
| Fiabilité | **totale** — testable unitairement | dépend du modèle |
| Latence / coût | quelques ms, zéro appel LLM | un appel LLM |
| Sécurité | **aucune surface d'injection** : le paramètre est lié, pas concaténé | 4 barrières nécessaires |
| Défaillance | aucune | requête fausse mais plausible |

**Ce qui justifie un tool figé** : un besoin récurrent, à forme fixe, où une erreur coûte
cher. « Quel est le stock de REF-1024 ? » est posée cent fois par jour par le support ; la
faire passer par un LLM, c'est payer un appel et accepter un risque pour une requête qu'on
sait écrire.

**Ce qui justifie le génératif** : la longue traîne. On ne peut pas anticiper « quelle
catégorie a le meilleur taux de rupture à Lyon ? ». Sans `ask_database`, ces questions
retournent au tableur — c'est-à-dire au bricolage que la DSI vient de geler.

#### Tools figés retenus

| Tool | Entrée | Requête | Garantie |
|---|---|---|---|
| `check_stock` | `ref` (`REF-\d{4}`) | `SELECT entrepot, quantite, seuil_reappro FROM stocks WHERE ref = ?` | paramètre lié · les 3 entrepôts · signale `quantite < seuil_reappro` |
| `order_status` | `order_id` (`CMD-\d{4}-\d{4}`) | `SELECT statut, date_commande, montant_ht FROM commandes WHERE id = ?` | paramètre lié · `montant_ht` selon profil |

Le format des identifiants étant strict et vérifié (`CMD-2025-0004`, `REF-1024`), l'entrée
est validée par regex **avant** d'atteindre la base : une entrée malformée est refusée sans
requête.

#### `get_schema`

Ni figé ni génératif : un tool d'aide. Il renvoie le schéma commenté **tel que le profil le
voit** — mêmes tables, mêmes colonnes, mêmes valeurs types que ce qui est envoyé au modèle.

Deux usages : un client (ou son LLM) prépare une question pertinente ; et un développeur
vérifie ce que son profil expose réellement. C'est aussi la démonstration la plus directe
de E5 — le même appel renvoie un schéma différent selon le profil.

### 6. Le chemin complet

```
question + profil
   │
   ├─(1) intention sensible ? ──oui──> statut: non_autorise          [aucun appel LLM]
   │
   ├─(2) schéma commenté FILTRÉ par profil + valeurs types + exemples
   │        │
   │        └──> génération LLM ──> SQL candidat
   │                                   │
   ├─(3) validation : 1 seule instruction · SELECT/WITH · mots-clés interdits
   │                  · tables et colonnes ⊆ périmètre du profil
   │        │
   │        ├── table inconnue ────> statut: hors_schema
   │        ├── colonne interdite ─> statut: non_autorise
   │        └── écriture détectée ─> statut: refuse_ecriture           [journalisé]
   │
   ├─(4) injection du LIMIT si absent
   │
   ├─(5) exécution sur connexion mode=ro, sous timeout
   │
   └──> { statut: ok, sql, colonnes, lignes, n_lignes, tronque }
```

**Le SQL exécuté est toujours renvoyé avec le résultat** (E3, transparence) — y compris en
cas de refus après génération, où voir la requête rejetée est précisément ce qui permet de
comprendre le refus.

### 7. Tools issus de ce chantier

| Tool | Entrées | Sorties | Garanties |
|---|---|---|---|
| `ask_database` | `question`, `profil` | `statut`, `sql`, `colonnes`, `lignes`, `n_lignes` | Lecture seule (4 barrières) · SQL renvoyé · périmètre du profil (E3, E5) |
| `get_schema` | `profil` | tables, colonnes commentées, valeurs types | Reflète exactement le périmètre du profil |
| `check_stock` | `ref` | stock par entrepôt, alerte réappro | Requête figée, paramètre lié, zéro LLM |
| `order_status` | `order_id` | statut, date, montant | Requête figée, paramètre lié, zéro LLM |

### Points ouverts

- **Modèle de génération SQL** : non tranché. Le RAG tourne en local ; un appel API pour la
  génération SQL est un choix distinct, à arbitrer (qualité contre reproductibilité en
  soutenance).
- **Valeur du `LIMIT` par défaut** : 200 est un ordre de grandeur. `ventes` comptant 993
  lignes, c'est la table qui dimensionne le choix.
- **Lexique des intentions sensibles** : à compléter au fil des questions réelles ; sa
  couverture est mesurable sur `eval/questions_sql.jsonl`, encore absent du dépôt.

---

## Chantier MCP et matrice d'accès

> Sorabel Data Gateway. Périmètre : le catalogue de tools, la gouvernance des accès et la
> journalisation (exigences E4, E5). Les chantiers 1 et 2 sont traités dans
> `conception_rag.md` et `conception_sql.md`.

### 0. Ce que la Gateway expose, et à qui

Un serveur MCP unique remplace les bricolages gelés par la DSI.

#### Un seul client, quatre profils

`scripts/mcp_client.py` est un **client unique** qui prend le profil en argument
(`--profil support`). **Il n'y a pas quatre clients** : il y a un client et quatre jeux de
droits.

Ce n'est pas une commodité de démonstration, c'est ce qui rend le contraste **prouvable** :
même code client, même serveur, même séquence d'appels — seul le profil change. Avec quatre
clients différents, on ne pourrait pas écarter l'hypothèse que la différence de réponse vient
du client plutôt que de la matrice.

Corollaire assumé : **le profil est déclaré par l'appelant**, ce qui n'est pas une
authentification. Voir les points ouverts.

#### Les quatre profils

Un profil est un **jeu de droits**, pas un logiciel. La colonne « métier modélisé » rappelle
seulement quelle situation de travail chaque jeu de droits reproduit — ce sont les usages
internes cités par le brief, pas des applications à développer.

| Profil | Métier modélisé | Besoin |
|---|---|---|
| `support` | technicien du support client | répondre à un client : documentation, stock, statut de commande |
| `commercial` | commercial en clientèle | analyse chiffrée, marges, négociation |
| `dev` | développeur intégrant la Gateway | comprendre le corpus et l'API, **sans lire les données de production** |
| `admin` | exploitation | accès total, diagnostic, démonstration du contraste |

### 1. Le catalogue : huit tools, deux niveaux

#### Pourquoi le RAG est exposé à deux niveaux

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

#### Catalogue complet

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

#### Décrire les tools pour que le LLM du client choisisse le bon

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

### 2. La matrice d'accès

#### Les collections ne sont pas les quatre dossiers

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

#### Matrice profil × tool

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

#### Matrice profil × collections

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

#### Matrice profil × tables et colonnes

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

#### Forme de la matrice : base de données + Pydantic + `Perimetre`

La matrice n'est pas une suite de `if profil == "support"` dispersés dans huit tools. Elle est
**stockée en base**, **validée par Pydantic au démarrage**, et **exposée aux tools par un seul
objet** : le `Perimetre`.

Trois couches, trois responsabilités.

##### Couche 1 — le stockage : `gouvernance.db`

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

##### Couche 2 — la validation : Pydantic au démarrage

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

##### Couche 3 — l'usage : l'objet `Perimetre`

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

#### Authentification et autorisation : deux étapes, dans cet ordre

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

### 3. Où la matrice est appliquée

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

#### Catalogue filtré

`tools/list` ne renvoie que les tools autorisés pour le profil. Le LLM du client ne peut donc
pas choisir un tool interdit — on évite un échec inutile et une description trompeuse.

Cela ne remplace pas le contrôle à l'appel : un client peut appeler un tool dont il n'a
jamais vu la description. Le catalogue filtré est une **commodité**, la vérification à
l'appel est la **sécurité**.

### 4. Ce que renvoie un appel refusé

#### Un refus n'est pas une panne

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

#### Forme d'un refus

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

### 5. Journalisation (E5)

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

### 6. Démontrer deux profils (livrable)

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

### Points ouverts

- **Transport et identification du profil** : le profil vient-il d'un en-tête de session, du
  jeton du client, d'un paramètre de tool ? Un profil déclaré par l'appelant lui-même n'est
  pas une authentification — acceptable pour la démonstration pédagogique, à nommer
  explicitement comme une limite.
- **`sous_type` et `diffusion_restreinte`** ne sont pas encore produits par l'extracteur de
  notes (chantier 1). Sans eux, les collections `notes_operationnelles` et
  `notes_confidentielles` ne sont pas séparables.
- **Rotation du journal** : hors périmètre à 6 jours, à mentionner en soutenance.

