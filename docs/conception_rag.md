# Dossier de conception — Chantier 1 : RAG avancé

> Sorabel Data Gateway. Périmètre de ce document : la recherche documentaire uniquement
> (exigences E1, E2, E6). Text-to-SQL et exposition MCP traités séparément.

## 0. État du corpus (constaté, non supposé)

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

### Le corpus est massivement redondant — et c'est le fait le plus important

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

## 1. Normalisation et gestion des versions

### Le document canonique : un état intermédiaire persisté

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

#### Règle d'or : un canonique est une fonction pure de son fichier source

Rien dans un canonique ne doit dépendre des **autres** documents du corpus. Sinon l'arrivée
d'un nouveau fichier oblige à réécrire des canoniques dont la source n'a pas bougé, et le
cache devient impossible.

C'est pourquoi **`est_version_courante` n'est pas dans le canonique** : savoir si `v2.1` est
la version courante suppose de connaître toutes les autres versions de `REF-1024`. Cette
information est une propriété du corpus, pas du document.

#### Le manifeste global

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

#### Cache : ne ré-extraire que ce qui a changé

Un canonique est réutilisé tel quel si **les deux** conditions sont vraies :

- `hash_source` correspond au SHA-256 du fichier sur disque — la source n'a pas bougé ;
- `schema_version` correspond à la version courante du code d'extraction.

Le second garde-fou est indispensable : sans lui, changer une règle d'extraction laisserait
des canoniques périmés en place et tu déboguerais sur des données obsolètes sans le voir.
On incrémente `schema_version` à chaque changement de règle, ce qui invalide tout le cache.

En pratique : première ingestion complète sur 400 fichiers, puis quasi instantanée.

#### Rapport de qualité d'extraction

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

### Traitement par type de document

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

#### `reference` et `references_citees` : deux champs, pas un

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

#### Cas particuliers

- **Note sans référence.** 16 notes sur 80 n'en citent aucune (politique tarifaire,
  logistique). Elles sont indexées avec `reference = null` et restent retrouvables par le
  sémantique. On ne les jette pas, et on ne leur invente pas de référence.
- **Document dont la référence attendue est introuvable.** Pour un PDF, la référence vient du
  nom de fichier : son absence signale un fichier mal nommé → alerte `reference_absente`.

### Versions multiples : ne pas dédoublonner, hiérarchiser

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

## 2. Granularité de chunk et métadonnées

### Granularité retenue : un document = un chunk

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

#### Ce que cette règle donne sur ce corpus précis

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

### Enrichissement de chunk (contextualisation)

Chaque chunk est préfixé, **avant embedding**, par une en-tête générée :

```
[Fiche technique REF-1024 v2.1 — Disjoncteur différentiel tétrapolaire — section « Caractéristiques »]
<texte du chunk>
```

Sans cela, le chunk « Étapes » d'une procédure ne contient nulle part le mot « SAV » ni la
référence, et devient irretrouvable dès qu'on s'éloigne de ses termes exacts.

### Modèle de chunk

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

### Pourquoi `reference` est le champ décisif

Trois usages qu'aucun autre champ ne couvre :

1. **Filtre exact.** Une question contenant `REF-8842` devient une recherche par métadonnée,
   pas une recherche sémantique. C'est déterministe, à 100 % de précision.
2. **Regroupement des versions.** Sans elle, impossible de savoir que `v1.0` et `v2.1`
   parlent du même produit.
3. **Jointure future avec le SQL.** C'est la clé qui permettra de croiser la fiche technique
   et le stock réel. La référence est le pivot entre les deux mondes du projet.

## 3. Pourquoi ni le dense ni le lexical ne suffisent seuls

> Cette section a été **réécrite après mesure**. La rédaction initiale annonçait que la
> recherche dense échouerait à retrouver `REF-8842`. Le test sur l'index réel montre que ce
> n'est pas le cas sur ce corpus, pour une raison qui tient à nos propres choix de
> conception. Le raisonnement corrigé ci-dessous est plus solide que la version théorique,
> parce qu'il est adossé à des chiffres.

### Le mécanisme théorique de l'échec dense

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

### Ce que la mesure montre réellement

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

### Là où chacun est réellement supérieur

Recherche « quel disjoncteur pour du triphasé ? » :

| | Résultat |
|---|---|
| Dense | 5 fiches de disjoncteurs pertinentes ✓ |
| BM25 | 5 procédures SAV « disjoncteur qui déclenche », toutes au même score 3,75 ✗ |

BM25 s'effondre : il n'a aucun moyen de rapprocher « triphasé » de « tétrapolaire 400 V », et
il renvoie cinq documents au corps identique qu'il est incapable de départager.

### Conclusion : l'hybride, mais pour la bonne raison

L'argument n'est pas « le dense ne trouve pas ». Il est plus précis :

> **Chaque moteur a un mode de défaillance que l'autre n'a pas, et aucun des deux ne produit
> seul un classement exploitable sur les deux familles de questions exigées par E2.**

Le dense apporte le rappel sémantique et une couverture correcte des références ; le lexical
apporte la séparation nette des scores sur les identifiants. La fusion (§ suivant) et le
rerank exploitent cette complémentarité. C'est ce que l'évaluation (§5) doit chiffrer.

### Fusion : RRF plutôt que somme pondérée

Les scores BM25 (non bornés) et cosinus (bornés) ne sont pas comparables ; les normaliser
demande de recalibrer à chaque changement de corpus. On utilise **Reciprocal Rank Fusion**,
qui ne travaille que sur les rangs :

```
score_RRF(d) = somme sur i de  1 / (k + rang_i(d)),  i ∈ {dense, bm25},  k = 60
```

Un document bien classé par l'un des deux moteurs remonte, même si l'autre l'ignore.
Aucun paramètre à calibrer, robuste au changement de modèle.

### Ce que le reranking ajoute par-dessus

L'hybride optimise le **rappel** : les ~30 bons candidats sont dans le lot. Il n'optimise pas
la **précision du top-3** — et c'est le top-3 qui part dans le prompt de génération.

Un **cross-encoder** lit `(question, chunk)` **ensemble** et produit un score de pertinence.
Il est bien plus juste qu'une comparaison de deux vecteurs calculés indépendamment, parce
qu'il voit les interactions terme à terme. Il est aussi bien plus lent — d'où l'ordre :
**hybride sur tout le corpus → 30 candidats → rerank de ces 30 → top-3.**

Bénéfice secondaire décisif : le score du reranker est **calibré et interprétable**, ce qui
en fait le bon seuil de refus pour E1 (§4).

### Chaîne complète

### Que déclenche exactement la détection de référence

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

## 4. Garantir E1 : citations systématiques et refus

### Citations

La citation n'est pas demandée au LLM, elle est **construite par le code** à partir des
métadonnées des chunks effectivement passés au prompt. Un LLM à qui on demande de citer
invente des références ; un code qui lit `chunk.titre`, `chunk.reference`, `chunk.date` ne
peut pas.

Format imposé par E1 — **titre + référence + date** :

> Fiche technique — Disjoncteur différentiel tétrapolaire (REF-1024, v2.1, 2024-03-12)

Chaque affirmation de la réponse renvoie à un marqueur `[1]`, `[2]` mappé sur la liste des
sources. La réponse structurée renvoyée par le tool contient toujours les deux champs
`reponse` et `sources[]`, jamais l'un sans l'autre.

### Refus hors corpus

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

## 5. Mesurer le gain (E6)

### Protocole

Trois configurations évaluées sur le **même jeu de questions**, avec le même corpus indexé :

| Config | Description |
|---|---|
| **A — baseline** | dense seul (Chroma, cosinus) |
| **B — hybride** | dense + BM25, fusion RRF |
| **C — hybride + rerank** | B suivi d'un cross-encoder |

### Découpage du jeu de questions

`questions_rag.jsonl` est scindé en deux sous-ensembles, **rapportés séparément** :

- **Questions par référence exacte** (« REF-8842 ») — c'est là que le gain de l'hybride doit
  être spectaculaire. C'est le sous-ensemble qui prouve E2.
- **Questions en langage naturel** — c'est là qu'il faut vérifier qu'on ne **dégrade pas** le
  dense en ajoutant le lexical.

Une moyenne globale masquerait exactement ce qu'on cherche à démontrer. Le tableau final doit
avoir ces deux colonnes.

### Métriques

- **Recall@5** : le bon document est-il dans les 5 premiers ? Mesure la capacité à trouver.
- **MRR** (rang réciproque moyen) : à quelle position ? Mesure la qualité du classement —
  c'est la métrique sensible au reranking, qui ne change pas le rappel mais le rang.
- **Hit@1** : sur les questions par référence, seule position acceptable. Le test
  d'acceptance dit « remonte **en tête** des résultats », pas « dans les résultats ».

### Livrable

`eval/rapport_eval.md` : tableau 3 configs × 3 métriques × 2 sous-ensembles, plus l'analyse
des cas où l'hybride perd — il y en aura, il faut les nommer, pas les cacher. Le script
`eval/run_eval.py` doit être rejouable en une commande pour la soutenance.

## 6. Tools MCP issus de ce chantier

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

### Signalement des versions antérieures

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

## 7. Décisions techniques

| Choix | Décision | Justification |
|---|---|---|
| Vector store | **Chroma** | Imposé par le brief ; filtrage par métadonnées natif, indispensable au filtre `est_version_courante` et au filtre par référence |
| Embeddings | multilingue local (`multilingual-e5` ou `BGE-m3`) | Corpus 100 % français ; local = reproductible en soutenance, sans clé API |
| Lexical | BM25 en mémoire | 400 documents : aucun besoin d'un moteur externe |
| Reranker | cross-encoder multilingue local | Appliqué à 30 candidats seulement, coût maîtrisé |
| Fusion | RRF, k = 60 | Pas de calibration de scores hétérogènes |

## Points ouverts

- **Seuil de refus** : à calibrer une fois `eval/questions_rag.jsonl` disponible. Seul point
  bloquant restant, et il ne bloque que l'étape E1/E6, pas l'ingestion.
- **Profondeur du premier étage (top 30)** : valeur de départ. À régler sur le Recall@30
  mesuré par l'éval — si le rappel plafonne, aucun rerank ne rattrapera les candidats perdus.

Résolus depuis la rédaction initiale : structure des PDF (mesurée, §0), granularité de chunk
(§2), traitement des références citées (§1), signalement des versions (§6).
