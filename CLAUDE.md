# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## État actuel du dépôt

**Aucun code n'est encore écrit.** Le dépôt ne contient que les données fournies, le brief et
le début du dossier de conception. Il n'y a aucun commit (`git log` est vide sur `master`),
aucun `pyproject.toml`/`requirements.txt`, aucun test, aucun script.

Toute commande de build / lint / test reste **à créer** — ne pas supposer qu'un outillage
existe. Python 3.12 est disponible sur la machine.

## Objectif du projet

Construire la **Sorabel Data Gateway** : un serveur MCP unique exposant à des clients internes
(bot support, poste commercial, IDE) deux capacités sur les données d'un distributeur B2B de
matériel électrique :

1. un **RAG avancé** (hybride dense + BM25, fusion RRF, reranking cross-encoder) sur un corpus
   documentaire hétérogène ;
2. un **Text-to-SQL en lecture seule** sur une base SQLite ;

le tout gouverné par une **matrice d'accès** (profil × tool × collections × tables/colonnes) et
journalisé intégralement.

Le cahier des charges complet — exigences E1 à E6, tests d'acceptance à faire passer, livrables
attendus — est dans `BRIEF.md`. **Le lire avant toute décision d'architecture** : les tests
d'acceptance sont la spécification de référence.

## Documents de conception

- `BRIEF.md` — le brief pédagogique intégral (exigences, tests d'acceptance, livrables).
- `docs/conception_rag.md` — chantier 1 (RAG) déjà rédigé et argumenté. **Il fait autorité pour
  toute implémentation du RAG** : modèle de chunk, stratégie de versions, chaîne de retrieval,
  protocole d'évaluation, catalogue des 4 tools RAG. Les chantiers 2 (Text-to-SQL) et 3
  (exposition MCP + matrice d'accès) n'ont pas encore de document équivalent.
- `ebauche schema elbby.png`, `evalquestions_rag.png`, `evalquestions_sql.png` — croquis et
  captures de travail.

Fichiers cités par le brief mais **absents du dépôt** : `docs/cadrage_dsi.md`,
`eval/questions_rag.jsonl`, `eval/questions_sql.jsonl`, `eval/run_eval.py`,
`scripts/mcp_client.py`, `mcp_server/`. Ils sont à produire ou à récupérer.

## Données fournies

### Corpus documentaire — `data/data/corpus/`

Attention au **double niveau `data/data/`** : le chemin réel est bien `data/data/corpus/…`.

| Dossier | Volume | Format | Où sont les métadonnées |
|---|---|---|---|
| `fiches/` | 150 | PDF | nom de fichier : `REF-XXXX-vM.m.pdf` |
| `notices/` | 80 | PDF | nom de fichier : `notice-REF-XXXX-vM.m.pdf` |
| `notes/` | 80 | Markdown | front-matter YAML (`titre`, `date`, `auteur`, `type`, `version`) ; la référence produit n'est que dans le corps du texte |
| `sav/` | 90 | HTML | `<title>` + `<meta name="version"|"date"|"type">` ; sections en `<h2>` (Conditions / Étapes / Cas hors périmètre) |

Points structurants :

- **La référence et la version sont dans le nom de fichier** pour les 230 PDF — les extraire
  par regex, pas par lecture du contenu.
- Le corpus contient **volontairement plusieurs versions** d'un même document
  (`REF-1024-v1.0.pdf` et `REF-1024-v2.1.pdf`, `proc-casse-transport-01-v1.0.html` et
  `-v2.0.html`). La décision actée est de **tout indexer** et de marquer la version courante
  (`est_version_courante`), la recherche filtrant dessus par défaut — pas de dédoublonnage
  destructif. Pour le SAV, la clé de regroupement est la famille de procédure
  (`proc-casse-transport-01`), pas le fichier.
- Les documents sont **courts** : chunking par section structurelle avec fusion des sections
  courtes, pas de découpe à taille fixe.

### Base SQL — `data/data/sorabel.db` (SQLite)

```
produits(ref PK, nom, categorie, fabricant, unite,
         prix_vente_ht, prix_achat_ht, marge_pct, actif)      120 lignes
stocks(id PK, ref FK→produits, entrepot, quantite, seuil_reappro)  312
clients(id PK, raison_sociale, segment, ville, email)               60
commandes(id PK, client_id FK→clients, date_commande, statut, montant_ht)  340
ventes(id PK, commande_id FK→commandes, ref FK→produits,
       quantite, prix_unitaire_ht, remise_pct, marge_ht)           993
```

`produits.ref` est le **pivot entre les deux mondes** : c'est la même référence `REF-XXXX` que
celle portée par les chunks du corpus.

**Colonnes sensibles** (E5) — `produits.prix_achat_ht`, `produits.marge_pct`, `ventes.marge_ht`
ne doivent jamais sortir pour le profil support.

`date_commande` est stockée en TEXT : les agrégations temporelles (« combien de commandes en
avril ? ») passent par des fonctions de date SQLite sur du texte ISO.

## Catalogue de tools MCP visé

`answer_question`, `search_docs`, `get_document`, `list_sources` (RAG) — `ask_database`,
`get_schema`, `check_stock`, `order_status` (données). Le tool de haut niveau et les briques
doivent fonctionner **séparément** : un client doit pouvoir chercher sans générer.

## Contraintes d'implémentation non négociables

Elles viennent des exigences DSI et des tests d'acceptance ; les enfreindre invalide le projet.

- **Vector store : Chroma** (imposé par le brief).
- **Citations construites par le code**, jamais demandées au LLM : elles sont dérivées des
  métadonnées des chunks réellement passés au prompt (titre + référence + date).
- **Refus hors corpus déterministe** : si le meilleur score après rerank est sous le seuil
  calibré, on ne génère pas du tout. Le refus est un retour normal
  (`{"statut": "hors_corpus", …}`), pas une exception — un client doit le distinguer d'une panne.
- **SQL en lecture seule à barrières multiples** : connexion en read-only *et* validation de la
  requête générée *et* `LIMIT` par défaut. Une seule barrière ne suffit pas.
- **Matrice d'accès appliquée à l'entrée du serveur et dans chaque tool** ; tout appel, autorisé
  comme refusé, est journalisé.
- **Le gain de l'hybride doit être mesuré** (E6) sur `questions_rag.jsonl`, avec les questions
  par référence exacte et les questions en langage naturel **rapportées séparément** — une
  moyenne globale masque précisément ce qu'on cherche à démontrer. Métriques : Recall@5, MRR,
  Hit@1.

## Langue

Le corpus, le brief, la conception et les échanges sont en **français** : code de domaine,
noms de champs, messages d'erreur et documentation suivent cette convention (`reference`,
`est_version_courante`, `statut`, `sources`).
