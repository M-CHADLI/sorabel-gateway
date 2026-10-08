# Calibrage du refus hors corpus (E1) — enseigne Kiabi

Mesure du 2026-10-08 sur le code de `f19e105`. **Décision : `seuil_refus = 0.75` pour Kiabi**
(`[rag]` de `enseignes/kiabi/enseigne.toml`) ; Sorabel garde `SEUIL_REFUS = 0.3`, inchangé.

## Protocole

- Index Kiabi construit par `make donnees ENSEIGNE=kiabi` : 175 documents, 175 chunks.
- Profil `commercial` (les cinq collections), `rechercher(question, k=30,
  config="hybride_rerank", collections_autorisees=...)`, comme `answer_question`.
- Score relevé : `resultats[0].score`, la note brute du reranker que compare
  `generation.repondre`. Sur toutes les mesures, elle vaut aussi la meilleure note des 30
  candidats.
- Le reranker LLM n'est pas déterministe : 31 questions mesurées deux fois (passes 1 et 2) ;
  la passe 3 ajoute 14 questions (couvertes plus indirectes, hors corpus proches du domaine)
  et remesure H05 et H12. Les notes observées sont toutes 0, 0.5 ou 1, les trois niveaux du
  barème.

## Résultat

| | Questions | Mesures | Note 0.5 | Note 1.0 | Note 0.0 |
|---|---|---|---|---|---|
| Couvertes | 24 | 40 | 0 | 38 | 2 (C04) |
| Hors corpus | 21 | 38 | 3 (H05, H12, N01) | 1 (H12) | 34 |

**0.3 ne sépare pas les deux groupes.** La note 0.5 (« sujet proche ») ne tombe que sur des
questions hors corpus proches du domaine, jamais sur le meilleur document d'une question
couverte. À 0.3, 4 mesures hors corpus sur 38 partent en génération ; à 0.75, une seule.
Les questions couvertes refusées restent les mêmes aux deux seuils (C04, voir plus bas).

Le barème n'ayant que trois niveaux, il n'y a que deux seuils distincts : entre 0 et 0.5, ou
entre 0.5 et 1. On prend le milieu du second intervalle, par la même logique que le 0.3 de
Sorabel. Le prix : sur Kiabi, une question dont le meilleur document n'obtient que 0.5 est
refusée sans génération. Ce cas n'est pas apparu, y compris sur les questions indirectes
(D01–D08 : agrégats, documents contradictoires).

## Ce qu'aucun seuil ne corrige

- **H12 noté 1.0 une fois** (la fiche « Robe à volants » jugée répondre à « vendez-vous des
  robes de mariée ? »). C'est la barrière de génération qui tient alors. Observée sur la
  même question notée 0.5 : « Les extraits fournis ne permettent pas de confirmer que nous
  vendons des robes de mariée », avec un statut `ok` et des citations.
- **C04 « guide d'entretien REF-3213 » refusée** 3 fois sur 5 alors que le guide existe.
  L'en-tête des chunks présente les notices Kiabi comme « Notice d'installation »
  (`LIBELLES_TYPE`, `sorabel_rag/chunking.py`, vocabulaire Sorabel). Même question, mêmes
  candidats, seul l'en-tête passé au reranker remplacé par « Guide d'entretien » : notice
  notée 1.0 à 3 essais sur 3, contre 1 sur 5 avec l'en-tête actuel. La correction (libellé
  par enseigne, puis réindexation de Kiabi) sort du périmètre de ce calibrage.

## Mesures

Score : passe 1 / passe 2 / passe 3 (« — » : non mesurée). Décision : ce que fait
`answer_question` à chaque seuil, avec le nombre de mesures concernées.

| # | Question | Attendu | Score | À 0.3 | À 0.75 |
|---|---|---|---|---|---|
| C01 | REF-1024 | couverte | 1 / 1 / — | répond | répond |
| C02 | REF-6677 | couverte | 1 / 1 / — | répond | répond |
| C03 | fiche technique REF-5812 | couverte | 1 / 1 / — | répond | répond |
| C04 | guide d'entretien REF-3213 | couverte | 0 / 0 / — | **refuse** | **refuse** |
| C05 | à quelle température laver un jean slim brut ? | couverte | 1 / 1 / — | répond | répond |
| C06 | peut-on passer un pull col camionneur au sèche-linge ? | couverte | 1 / 1 / — | répond | répond |
| C07 | comment faire sécher une doudoune légère sans manches ? | couverte | 1 / 1 / — | répond | répond |
| C08 | un client veut échanger un article contre une autre taille : quelle est la procédure ? | couverte | 1 / 1 / — | répond | répond |
| C09 | que faire quand un colis commandé sur le site arrive endommagé ? | couverte | 1 / 1 / — | répond | répond |
| C10 | un vêtement a rétréci au lavage, comment traiter la réclamation du client ? | couverte | 1 / 1 / — | répond | répond |
| C11 | un magasin a reçu des articles qui ne correspondent pas à son réassort, que faire ? | couverte | 1 / 1 / — | répond | répond |
| C12 | comment rembourser un client sur carte cadeau ? | couverte | 1 / 1 / — | répond | répond |
| C13 | quel défaut qualité a été signalé sur le top en dentelle ? | couverte | 1 / 1 / — | répond | répond |
| C14 | depuis quel entrepôt est expédié le réassort du jogging molleton ? | couverte | 1 / 1 / — | répond | répond |
| C15 | la chemise oxford taille-t-elle petit selon les magasins ? | couverte | 1 / 1 / — | répond | répond |
| C16 | quelle est la composition de la veste softshell ? | couverte | 1 / 1 / — | répond | répond |
| D01 | le t-shirt imprimé dinosaure est-il en coton bio ? | couverte | — / — / 1 | répond | répond |
| D02 | sous combien de jours un client est-il remboursé ? | couverte | — / — / 1 | répond | répond |
| D03 | combien de temps un client a-t-il pour demander un échange ? | couverte | — / — / 1 | répond | répond |
| D04 | quelle est la marge cible de la catégorie Homme ? | couverte | — / — / 1 | répond | répond |
| D05 | le jean slim brut a-t-il un problème qualité connu ? | couverte | — / — / 1 | répond | répond |
| D06 | avec quels produits associer le jean slim brut ? | couverte | — / — / 1 | répond | répond |
| D07 | quels articles bébé sont fabriqués en Inde ? | couverte | — / — / 1 | répond | répond |
| D08 | quelles références sont en tension sur le réassort ? | couverte | — / — / 1 | répond | répond |
| H01 | quelle est la capitale de l'Australie ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H02 | qui a écrit Les Misérables ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H03 | comment réussir une pâte à crêpes ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H04 | quels sont les horaires d'ouverture du magasin Kiabi de Lille ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H05 | quel est le prix d'un costume trois pièces en laine ? | hors corpus | 0.5 / 0 / 0 | **génère 1/3** | refuse |
| H06 | quelle est la politique de télétravail chez Kiabi ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H07 | quelles sont les grilles de salaires des conseillers de vente ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H08 | comment postuler à un poste de vendeur en magasin ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H09 | quel est le chiffre d'affaires de Kiabi en 2025 ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H10 | à partir de quel montant la livraison est-elle gratuite sur le site ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H11 | comment fonctionne le programme de fidélité ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H12 | vendez-vous des robes de mariée ? | hors corpus | 0 / 0.5 / 1 | **génère 2/3** | **génère 1/3** |
| H13 | comment configurer le VPN interne ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H14 | quels moyens de paiement sont acceptés en caisse ? | hors corpus | 0 / 0 / — | refuse | refuse |
| H15 | combien de pièces de REF-1024 reste-t-il en stock à l'entrepôt de Lauwin ? | hors corpus | 0 / 0 / — | refuse | refuse |
| N01 | quand commencent les soldes d'hiver 2026 ? | hors corpus | — / — / 0.5 | **génère 1/1** | refuse |
| N02 | combien de magasins compte le réseau Kiabi ? | hors corpus | — / — / 0 | refuse | refuse |
| N03 | quelle est la date du prochain comité de collection ? | hors corpus | — / — / 0 | refuse | refuse |
| N04 | vendez-vous des maillots de bain pour bébé ? | hors corpus | — / — / 0 | refuse | refuse |
| N05 | quelle est la composition du manteau en laine bouillie ? | hors corpus | — / — / 0 | refuse | refuse |
| N06 | qui est le responsable du magasin de Lyon ? | hors corpus | — / — / 0 | refuse | refuse |

Les questions de `eval/questions_rag_kiabi.jsonl` reprennent une partie de celles-ci : ce
jeu sert l'évaluation du retrieval (E6), il ne valide pas le seuil de façon indépendante.
