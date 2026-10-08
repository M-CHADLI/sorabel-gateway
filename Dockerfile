# Étape 1 : construire les index, un par enseigne. Les corpus ne sont lus QU'ICI — ils ne
# partent pas en production.
FROM python:3.12-slim AS index

RUN pip install --no-cache-dir uv
# Même chemin que le WORKDIR de l'étape finale : `uv sync` fige le chemin absolu du
# venv dans le shebang des scripts console (ex. `streamlit`). Un venv construit dans
# /build puis copié vers /app pointerait vers un interpréteur inexistant — seul
# `python -m ...` survivrait à la copie, pas l'appel direct `streamlit run ...`.
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Le moteur lit l'enseigne a l'import : sans le paquet et son .toml, rien ne demarre. Chaque
# enseigne est copiee fichier par fichier, jamais `enseignes/` en bloc : ce dossier porte les
# corpus, qui ne doivent pas atteindre l'etape servie, ni des sorties locales perimees.
COPY sorabel_enseigne/ sorabel_enseigne/
COPY enseignes/sorabel/enseigne.toml enseignes/sorabel/enseigne.toml
COPY sorabel_rag/ sorabel_rag/
COPY sorabel_llm/ sorabel_llm/
COPY gouvernance/ gouvernance/
COPY scripts/ scripts/
COPY data/corpus/ data/corpus/
COPY data/sorabel.db data/sorabel.db

# Endpoint et nom de déploiement ne sont PAS des secrets (ce sont des identifiants de
# ressource, pas des clés) : ils passent en ARG/ENV classiques. Seule la clé d'API doit
# transiter par le mécanisme de secret BuildKit, plus bas — ARG_EMBEDDING_ENDPOINT et
# AZURE_OPENAI_ENDPOINT couvrent le cas où le déploiement d'embeddings est servi par une
# ressource « serverless » distincte de la ressource de génération (repli sorabel_rag/index.py).
ARG AZURE_EMBEDDING_ENDPOINT
ARG AZURE_OPENAI_ENDPOINT
ARG AZURE_OPENAI_EMBEDDING_DEPLOYMENT
ENV AZURE_EMBEDDING_ENDPOINT=${AZURE_EMBEDDING_ENDPOINT} \
    AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT} \
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT=${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}

# La clé d'embeddings, elle, est montée par Cloud Build depuis Secret Manager : elle ne
# subsiste dans aucune couche de l'image finale, contrairement à un ARG/ENV classique qui
# la persisterait en clair dans `docker history`.
RUN --mount=type=secret,id=azure_embedding_key \
    AZURE_EMBEDDING_API_KEY="$(cat /run/secrets/azure_embedding_key)" \
    .venv/bin/python scripts/seed_gouvernance.py \
 && AZURE_EMBEDDING_API_KEY="$(cat /run/secrets/azure_embedding_key)" \
    .venv/bin/python scripts/ingerer.py \
 && AZURE_EMBEDDING_API_KEY="$(cat /run/secrets/azure_embedding_key)" \
    .venv/bin/python scripts/indexer.py

# Kiabi, enseigne de démonstration (données FICTIVES, scripts/generer_kiabi.py) : même
# moteur, même secret, autres données. Bloc placé APRÈS l'index Sorabel, pour que les
# instructions qui produisent ce dernier restent celles d'avant Kiabi : une modification des
# données Kiabi n'invalide pas la couche Sorabel du cache et ne recalcule pas ses embeddings.
# Pas de second seed_gouvernance : la matrice d'accès est commune aux enseignes
# (enseignes/kiabi/enseigne.toml pointe vers gouvernance/gouvernance.db, peuplée plus haut).
COPY enseignes/kiabi/enseigne.toml enseignes/kiabi/enseigne.toml
COPY enseignes/kiabi/data/kiabi.db enseignes/kiabi/data/kiabi.db
COPY enseignes/kiabi/data/corpus/ enseignes/kiabi/data/corpus/

# SORABEL_ENSEIGNE posée commande par commande, pas en ENV : une ENV vaudrait pour toute la
# suite de l'étape, et une commande ajoutée plus bas basculerait sans bruit sur Kiabi.
# L'ingestion n'appelle aucun service (extraction déterministe) : seule l'indexation, qui
# calcule les embeddings, reçoit la clé.
RUN --mount=type=secret,id=azure_embedding_key \
    SORABEL_ENSEIGNE=kiabi .venv/bin/python scripts/ingerer.py \
 && SORABEL_ENSEIGNE=kiabi AZURE_EMBEDDING_API_KEY="$(cat /run/secrets/azure_embedding_key)" \
    .venv/bin/python scripts/indexer.py

# Étape 2 : l'image servie. Ni corpus, d'aucune enseigne, ni outils de construction.
#
# Elle porte les données de TOUTES les enseignes : chaque processus n'en sert qu'une, figée
# au démarrage par SORABEL_ENSEIGNE (posée au déploiement, cloudbuild.yaml ; Sorabel sans
# elle). L'isolation entre enseignes est donc par processus, pas par image — limite assumée,
# docs/EXPLOITATION.md §10.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    SORABEL_JOURNAL=stdout \
    SORABEL_TRANSPORT=http \
    SORABEL_DEPOT=firestore \
    PATH="/app/.venv/bin:$PATH"

COPY --from=index /app/.venv /app/.venv
COPY --from=index /app/data/canonique/ data/canonique/
COPY --from=index /app/data/chroma/ data/chroma/
COPY --from=index /app/data/sorabel.db data/sorabel.db
COPY --from=index /app/gouvernance/gouvernance.db gouvernance/gouvernance.db
# Les données Kiabi viennent elles aussi de l'étape index, comme celles de Sorabel : le
# contexte de build ne fournit ici que du code et de la configuration.
COPY --from=index /app/enseignes/kiabi/data/canonique/ enseignes/kiabi/data/canonique/
COPY --from=index /app/enseignes/kiabi/data/chroma/ enseignes/kiabi/data/chroma/
COPY --from=index /app/enseignes/kiabi/data/kiabi.db enseignes/kiabi/data/kiabi.db

COPY sorabel_rag/ sorabel_rag/
COPY sorabel_sql/ sorabel_sql/
COPY sorabel_llm/ sorabel_llm/
COPY sorabel_enseigne/ sorabel_enseigne/
COPY enseignes/sorabel/enseigne.toml enseignes/sorabel/enseigne.toml
COPY enseignes/kiabi/enseigne.toml enseignes/kiabi/enseigne.toml
COPY gouvernance/ gouvernance/
COPY mcp_server/ mcp_server/
COPY front/ front/
COPY .streamlit/ .streamlit/

EXPOSE 8080
CMD ["python", "-m", "mcp_server.serveur"]
