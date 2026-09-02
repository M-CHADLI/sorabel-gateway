# Dossier de conception — Chantier 2 : Text-to-SQL

> Sorabel Data Gateway. Périmètre : l'accès aux données relationnelles en langage naturel
> (exigences E3, E5). Le RAG est traité dans `conception_rag.md`, l'exposition MCP et la
> matrice d'accès dans `conception_mcp.md`.

## 0. État de la base (constaté, non supposé)

`data/data/sorabel.db` — SQLite, 5 tables métier.

| Table | Lignes | Clé | Liens |
|---|---|---|---|
| `produits` | 120 | `ref` TEXT | ← `stocks.ref`, `ventes.ref` |
| `stocks` | 312 | `id` INTEGER | → `produits.ref` |
| `clients` | 60 | `id` TEXT (`CLI-1000`) | ← `commandes.client_id` |
| `commandes` | 340 | `id` TEXT (`CMD-2025-0004`) | → `clients.id` |
| `ventes` | 993 | `id` INTEGER | → `commandes.id`, → `produits.ref` |

### Faits mesurés qui changent la conception

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

### Colonnes sensibles (E5)

| Colonne | Nature |
|---|---|
| `produits.prix_achat_ht` | prix d'achat fournisseur |
| `produits.marge_pct` | taux de marge |
| `ventes.marge_ht` | marge en valeur |

Elles ne sortent **jamais** pour le profil support. Le corpus documentaire contient
`Prix public HT` sur les fiches — c'est un prix de vente, public par nature : il n'est pas
sensible et n'a pas à être filtré.

## 1. De la question à la requête : ce qu'on donne au modèle

Un modèle ne peut pas deviner un schéma. La qualité de génération se joue entièrement dans
le contexte fourni, en quatre couches.

### a. Le schéma commenté, filtré par profil

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

### b. Les valeurs types

Les énumérations du §0, injectées littéralement. C'est ce qui évite `'livrée'` au lieu de
`livree`.

### c. Des exemples de requêtes (few-shot)

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

### d. Les règles de sortie

Une seule requête, `SELECT` uniquement, pas de point-virgule multiple, pas de commentaire.
Si la question ne peut pas être traduite, le modèle doit répondre par un marqueur explicite
plutôt que par du SQL approximatif — cf. §4.

## 2. Lecture seule : quatre barrières (E3)

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

### Validation : liste de mots interdits ou analyse ?

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

## 3. Restreindre tables et colonnes par profil (E5)

La restriction s'applique **trois fois**, à trois moments différents.

| Moment | Mécanisme | Rôle |
|---|---|---|
| Avant génération | le schéma envoyé au modèle est déjà filtré | le modèle ignore l'existence de la colonne |
| Avant génération | **détection d'intention sensible** dans la question | refus explicite sans appel LLM |
| Après génération | le validateur vérifie tables et colonnes citées | rattrape ce que le modèle aurait inventé |

### Le refus explicite avant génération

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

## 4. Questions ambiguës ou hors schéma

Trois issues distinctes, que le client doit pouvoir différencier. **Aucune n'est une
exception** : ce sont des retours normaux avec un `statut`.

| Cas | Exemple | `statut` | Contenu |
|---|---|---|---|
| Traduisible | « combien de commandes en avril ? » | `ok` | résultat + SQL exécuté |
| **Ambigu** | « quel est le meilleur client ? » | `ambigu` | interprétations proposées |
| **Hors schéma** | « quel est le taux de satisfaction ? » | `hors_schema` | ce que la base contient |
| Interdit | « quelle marge sur REF-1024 ? » (support) | `non_autorise` | colonne refusée |

### L'ambiguïté : demander, en proposant les options

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

### Le hors schéma : refuser en disant ce qui existe

Un modèle à qui on demande le taux de satisfaction **inventera** une table `avis` — c'est le
mode de défaillance le plus dangereux, parce que la requête générée est plausible et
l'erreur SQLite arrive trop tard, après avoir laissé croire que la donnée existait.

La détection est faite **après génération** : si le validateur rencontre une table ou une
colonne absente du schéma réel, on ne tente pas d'exécuter. Le message nomme les 5 tables
disponibles.

## 5. Tools figés ou SQL généré ?

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

### Tools figés retenus

| Tool | Entrée | Requête | Garantie |
|---|---|---|---|
| `check_stock` | `ref` (`REF-\d{4}`) | `SELECT entrepot, quantite, seuil_reappro FROM stocks WHERE ref = ?` | paramètre lié · les 3 entrepôts · signale `quantite < seuil_reappro` |
| `order_status` | `order_id` (`CMD-\d{4}-\d{4}`) | `SELECT statut, date_commande, montant_ht FROM commandes WHERE id = ?` | paramètre lié · `montant_ht` selon profil |

Le format des identifiants étant strict et vérifié (`CMD-2025-0004`, `REF-1024`), l'entrée
est validée par regex **avant** d'atteindre la base : une entrée malformée est refusée sans
requête.

### `get_schema`

Ni figé ni génératif : un tool d'aide. Il renvoie le schéma commenté **tel que le profil le
voit** — mêmes tables, mêmes colonnes, mêmes valeurs types que ce qui est envoyé au modèle.

Deux usages : un client (ou son LLM) prépare une question pertinente ; et un développeur
vérifie ce que son profil expose réellement. C'est aussi la démonstration la plus directe
de E5 — le même appel renvoie un schéma différent selon le profil.

## 6. Le chemin complet

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

## 7. Tools issus de ce chantier

| Tool | Entrées | Sorties | Garanties |
|---|---|---|---|
| `ask_database` | `question`, `profil` | `statut`, `sql`, `colonnes`, `lignes`, `n_lignes` | Lecture seule (4 barrières) · SQL renvoyé · périmètre du profil (E3, E5) |
| `get_schema` | `profil` | tables, colonnes commentées, valeurs types | Reflète exactement le périmètre du profil |
| `check_stock` | `ref` | stock par entrepôt, alerte réappro | Requête figée, paramètre lié, zéro LLM |
| `order_status` | `order_id` | statut, date, montant | Requête figée, paramètre lié, zéro LLM |

## Points ouverts

- **Modèle de génération SQL** : non tranché. Le RAG tourne en local ; un appel API pour la
  génération SQL est un choix distinct, à arbitrer (qualité contre reproductibilité en
  soutenance).
- **Valeur du `LIMIT` par défaut** : 200 est un ordre de grandeur. `ventes` comptant 993
  lignes, c'est la table qui dimensionne le choix.
- **Lexique des intentions sensibles** : à compléter au fil des questions réelles ; sa
  couverture est mesurable sur `eval/questions_sql.jsonl`, encore absent du dépôt.
