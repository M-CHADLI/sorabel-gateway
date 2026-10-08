# Sorabel Data Gateway — raccourcis de développement et de démonstration.
# `make` seul affiche l'aide. Détails du code : docs/DOSSIER_TECHNIQUE.md.

# Lancé depuis PowerShell ou cmd, GNU Make sous Windows retombe sur cmd.exe et aucune
# recette POSIX ne passe. On force le sh de Git for Windows, et on met ses outils (rm,
# find, awk…) en tête du PATH : sans ça, sh démarre sans /usr/bin. Chemin court 8.3
# parce que Make ne sait pas quoter un SHELL contenant une espace.
ifeq ($(OS),Windows_NT)
GIT_USR ?= $(firstword $(wildcard C:/PROGRA~1/Git/usr/bin C:/PROGRA~2/Git/usr/bin))
ifeq ($(GIT_USR),)
$(error Git for Windows introuvable : installer Git, ou passer GIT_USR=<dossier contenant sh.exe>)
endif
SHELL := $(GIT_USR)/sh.exe
export PATH := $(GIT_USR);$(PATH)
endif

# Les scripts impriment accents et pictogrammes : sans UTF-8 forcé, une console Windows
# en cp1252 lève UnicodeEncodeError au premier « é ».
export PYTHONUTF8 := 1

# Pas d'accent dans le texte des recettes (echo…) : sous Windows, Make transmet la ligne
# de commande à sh en page de code ANSI et « é » ressort « Ã© ». Les descriptions `##`
# ne sont pas concernées — awk les lit directement dans ce fichier.

# `uv run` synchronise l'environnement avant chaque commande : pas de venv à activer.
PY := uv run python

PROFIL ?= commercial
N      ?= 10

URL_FRONT  := https://sorabel-front-4g2lzykvia-ew.a.run.app
GCP_PROJET := sorabel-vitrine-2026
GCP_REGION := europe-west1

# Motifs grep -E : sorabel_llm accepte AZURE_OPENAI_DEPLOYMENT_NAME comme alias.
CLES_AZURE := AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY 'AZURE_OPENAI_DEPLOYMENT(_NAME)?' \
              AZURE_OPENAI_EMBEDDING_DEPLOYMENT AZURE_OPENAI_RERANK_DEPLOYMENT

GOUVERNANCE_DB := gouvernance/gouvernance.db
MANIFESTE      := data/canonique/_manifeste.json
INDEX          := data/chroma/bm25.pkl
CORPUS         := $(wildcard data/corpus/*/*)

.DEFAULT_GOAL := help
.PHONY: help install verifier donnees reindexer test serveur demo contraste demo-http \
        inspecteur journal vitrine gcp-statut clean reset-donnees

##@ Mise en route

help: ## Affiche cette aide
	@awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
	  /^[a-z][a-z-]*:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "Variables : PROFIL=support|commercial|dev|admin (actuel : $(PROFIL)), N=$(N)"

install: ## Installe les dépendances (uv sync, Python 3.12)
	uv sync

verifier: ## Contrôle avant démo : .env Azure, données construites, front déployé joignable
	@echo "Azure : variables du .env"
	@for cle in $(CLES_AZURE); do \
	  if grep -Eq "^$$cle=." .env 2>/dev/null; then echo "  ok      $${cle%%(*}"; \
	  else echo "  VIDE    $${cle%%(*}"; fi; done
	@echo "Fichiers construits"
	@for f in $(GOUVERNANCE_DB) $(MANIFESTE) $(INDEX); do \
	  if [ -f $$f ]; then echo "  ok      $$f"; \
	  else echo "  ABSENT  $$f  -> make donnees"; fi; done
	@echo "Front Cloud Run (302 attendu : IAP redirige vers la connexion Google)"
	@code=$$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 $(URL_FRONT)); \
	  echo "  HTTP $$code  $(URL_FRONT)"

donnees: $(GOUVERNANCE_DB) $(MANIFESTE) $(INDEX) ## Construit matrice d'accès, canoniques et index (seulement ce qui manque)

reindexer: $(MANIFESTE) ## Force la réindexation — obligatoire après un changement de déploiement d'embeddings
	$(PY) scripts/indexer.py

##@ Qualité

test: $(GOUVERNANCE_DB) $(MANIFESTE) ## Lance les 182 tests
	$(PY) -m pytest -q

##@ Démonstration locale (stdio, sans authentification)

demo: donnees .env ## Client MCP scripté : recherche doc, SQL, tentative d'écriture, schéma (PROFIL=…)
	$(PY) scripts/mcp_client.py --profil $(PROFIL)

contraste: donnees .env ## Même séquence en support puis en commercial : marges masquées puis visibles (E5)
	@for p in support commercial; do $(PY) scripts/mcp_client.py --profil $$p; done

journal: ## Derniers appels journalisés, refus compris (N=…)
	@$(PY) -c "import json; \
	lignes = [json.loads(l) for l in open('logs/appels.jsonl', encoding='utf-8')][-$(N):]; \
	[print(f\"{l['horodatage'][:19]}  {l['profil']:<10} {l['tool']:<16} {l['statut']:<13} {l.get('motif') or ''}\") for l in lignes]"

serveur: donnees .env ## Serveur MCP en stdio, profil figé au démarrage (PROFIL=…)
	SORABEL_PROFIL=$(PROFIL) $(PY) -m mcp_server.serveur

inspecteur: donnees .env ## MCP Inspector (navigateur) branché sur le serveur stdio (PROFIL=…)
	npx @modelcontextprotocol/inspector -e SORABEL_PROFIL=$(PROFIL) uv run python -m mcp_server.serveur

demo-http: donnees .env ## Serveur HTTP :8080 SANS authentification, pour un playground MCP (PROFIL=…)
	$(PY) scripts/demo_mcp_http.py --profil $(PROFIL)

##@ Production (GCP)

vitrine: ## Ouvre le poste de travail déployé (Cloud Run derrière IAP)
	$(PY) -m webbrowser $(URL_FRONT)

gcp-statut: ## État des services Cloud Run sorabel-mcp et sorabel-front
	gcloud run services list --project=$(GCP_PROJET) --region=$(GCP_REGION)

##@ Nettoyage

clean: ## Supprime caches Python et journaux d'outils locaux (*.log)
	find . -path ./.venv -prune -o -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -f *.log

reset-donnees: ## Supprime les données régénérables — la reconstruction rappellera Azure
	rm -rf data/canonique data/chroma $(GOUVERNANCE_DB)

# --- Fichiers construits ---------------------------------------------------------------

$(GOUVERNANCE_DB): gouvernance/seed.py
	$(PY) scripts/seed_gouvernance.py

$(MANIFESTE): $(CORPUS)
	$(PY) scripts/ingerer.py

# Prérequis d'ordre seul (après `|`) : l'index se construit s'il manque, mais une
# ingestion plus récente ne le périme pas. Chaque réindexation paie les embeddings Azure,
# et l'ingestion réécrit le manifeste même quand le corpus n'a pas bougé — une dépendance
# par date relancerait l'indexation à chaque fois. Pour la forcer : `make reindexer`.
$(INDEX): | $(MANIFESTE)
	$(PY) scripts/indexer.py

.env:
	@cp .env.example .env
	@echo ".env absent : copie de .env.example faite. Renseigner les variables AZURE_*, puis relancer."
	@exit 1
