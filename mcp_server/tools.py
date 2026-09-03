"""Enregistre les tools MCP autorisés pour un profil donné.

tools/list filtré EST l'intercepteur d'entrée dans cette architecture (Global Constraints du
plan) : chaque processus serveur ne sert qu'un seul profil, résolu une fois au démarrage —
il n'existe donc structurellement aucun moyen d'appeler un tool non enregistré ici.

Les imports de sorabel_sql.tools sont aliasés pour éviter toute collision de nom avec les
fonctions MCP de même nom définies plus bas (ask_database, get_schema, check_stock,
order_status) — sans l'alias, la fonction imbriquée masquerait l'import au lieu de l'appeler.
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

from gouvernance.journal import journaliser
from gouvernance.perimetre import Perimetre
from sorabel_rag.documents import lister_sources, obtenir_document
from sorabel_rag.generation import repondre
from sorabel_rag.recherche import rechercher
from sorabel_sql.tools import ask_database as _sql_ask_database
from sorabel_sql.tools import check_stock as _sql_check_stock
from sorabel_sql.tools import get_schema as _sql_get_schema
from sorabel_sql.tools import order_status as _sql_order_status


def enregistrer_tools(mcp, perimetre: Perimetre) -> None:
    """Enregistre les 8 tools MCP (ou un sous-ensemble selon les droits du profil).

    Args:
        mcp: Instance FastMCP où enregistrer les tools
        perimetre: Périmètre d'accès du profil actuel
    """
    profil = perimetre.profil

    def _avec_journalisation(nom_tool: str) -> Callable:
        """Décorateur unique pour journaliser tous les appels de tool.

        Enveloppe la fonction du tool, mesure la durée, appelle journaliser() avec les
        bons arguments, et retourne le résultat inchangé.

        Args:
            nom_tool: Nom du tool pour la journalisation (ex. 'answer_question')

        Returns:
            Décorateur prêt à envelopper une fonction de tool
        """
        def decorateur(func: Callable) -> Callable:
            @functools.wraps(func)
            def enveloppe(*args: Any, **kwargs: Any) -> dict:
                debut = time.monotonic()
                resultat = func(*args, **kwargs)

                # Construire les entrées de manière générique
                entrees = {}
                if args:
                    # Les paramètres positionnels ne devraient pas être utilisés par les tools
                    pass
                entrees.update(kwargs)

                # Journaliser l'appel
                journaliser(
                    profil=profil,
                    tool=nom_tool,
                    autorise=True,
                    statut=resultat.get("statut", "ok"),
                    entrees=entrees,
                    sql=resultat.get("sql"),
                    n_lignes=resultat.get("n_lignes", 0),
                    duree_ms=(time.monotonic() - debut) * 1000,
                    motif=resultat.get("message"),
                )
                return resultat
            return enveloppe
        return decorateur

    if perimetre.peut_appeler("answer_question"):
        @mcp.tool()
        @_avec_journalisation("answer_question")
        def answer_question(question: str) -> dict:
            """Réponse rédigée avec sources, à partir du corpus documentaire Sorabel.
            N'utilisez PAS ce tool pour obtenir des extraits bruts : voyez search_docs.
            Statuts possibles : ok, hors_corpus (aucune réponse trouvée, à afficher tel quel,
            pas comme une panne)."""
            return repondre(question, perimetre=perimetre)

    if perimetre.peut_appeler("search_docs"):
        @mcp.tool()
        @_avec_journalisation("search_docs")
        def search_docs(requete: str, k: int = 5, type_document: str | None = None) -> dict:
            """Recherche documentaire hybride : extraits bruts + scores, AUCUNE génération.
            N'utilisez PAS ce tool pour obtenir une réponse rédigée : voyez answer_question."""
            resultats = rechercher(
                requete, k=k, type_document=type_document,
                collections_autorisees=perimetre.collections_autorisees(),
            )
            return {
                "statut": "ok",
                "resultats": [
                    {"chunk_id": r.chunk_id, "texte": r.texte, "score": r.score,
                     "titre": r.titre, "reference": r.reference}
                    for r in resultats
                ],
            }

    if perimetre.peut_appeler("get_document"):
        @mcp.tool()
        @_avec_journalisation("get_document")
        def get_document(
            doc_id: str | None = None,
            reference: str | None = None,
            version: str | None = None,
        ) -> dict:
            """Document canonique complet, par doc_id OU par (reference + version optionnelle
            — version courante par défaut si omise). Voir list_sources ou search_docs pour
            obtenir un doc_id ou une référence. Statuts : ok, hors_schema (introuvable, ou
            reference ambiguë entre plusieurs types de document), non_autorise (collection
            hors périmètre du profil)."""
            return obtenir_document(doc_id, reference, version, perimetre=perimetre)

    if perimetre.peut_appeler("list_sources"):
        @mcp.tool()
        @_avec_journalisation("list_sources")
        def list_sources(type_document: str | None = None) -> dict:
            """Inventaire des documents indexés et de leurs versions, reflète le périmètre
            du profil (une note confidentielle hors périmètre n'apparaît pas)."""
            return lister_sources(type_document, perimetre=perimetre)

    if perimetre.peut_appeler("ask_database"):
        @mcp.tool()
        @_avec_journalisation("ask_database")
        def ask_database(question: str) -> dict:
            """Question en langage naturel sur les données Sorabel (produits, stocks, clients,
            commandes, ventes). Utilisez ce tool quand la question demande un CALCUL ou un
            AGRÉGAT. Lecture seule ; renvoie toujours le SQL exécuté ou rejeté. Statuts :
            ok, hors_schema, non_autorise, refuse_ecriture."""
            return _sql_ask_database(question, perimetre)

    if perimetre.peut_appeler("get_schema"):
        @mcp.tool()
        @_avec_journalisation("get_schema")
        def get_schema() -> dict:
            """Schéma commenté des tables SQL tel que ce profil le voit (mêmes colonnes que
            celles disponibles via ask_database)."""
            return _sql_get_schema(perimetre)

    if perimetre.peut_appeler("check_stock"):
        @mcp.tool()
        @_avec_journalisation("check_stock")
        def check_stock(ref: str) -> dict:
            """Stock par entrepôt pour UNE référence précise (format REF-XXXX). Utilisez ce
            tool quand la question porte sur une référence précise, pas un agrégat — pour un
            agrégat (ex. "quelles références sont sous le seuil ?"), voyez ask_database."""
            return _sql_check_stock(ref)

    if perimetre.peut_appeler("order_status"):
        @mcp.tool()
        @_avec_journalisation("order_status")
        def order_status(order_id: str) -> dict:
            """Statut, date et montant d'UNE commande précise (format CMD-AAAA-NNNN)."""
            return _sql_order_status(order_id)
