# Étape 1 : construire l'index. Le corpus n'est lu QU'ICI — il ne part pas en production.
FROM python:3.12-slim AS index

RUN pip install --no-cache-dir uv
# Même chemin que le WORKDIR de l'étape finale : `uv sync` fige le chemin absolu du
# venv dans le shebang des scripts console (ex. `streamlit`). Un venv construit dans
# /build puis copié vers /app pointerait vers un interpréteur inexistant — seul
# `python -m ...` survivrait à la copie, pas l'appel direct `streamlit run ...`.
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

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

# Étape 2 : l'image servie. Ni corpus, ni outils de construction.
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

COPY sorabel_rag/ sorabel_rag/
COPY sorabel_sql/ sorabel_sql/
COPY sorabel_llm/ sorabel_llm/
COPY gouvernance/ gouvernance/
COPY mcp_server/ mcp_server/
COPY front/ front/
COPY .streamlit/ .streamlit/

EXPOSE 8080
CMD ["python", "-m", "mcp_server.serveur"]
