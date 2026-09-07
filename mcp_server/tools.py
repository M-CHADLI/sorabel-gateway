"""Enregistre les 8 tools MCP, inconditionnellement, quel que soit le profil appelant.

En stdio, un processus servait un seul profil, résolu une fois au démarrage : `tools/list`
filtré tenait lieu d'intercepteur d'entrée, puisqu'un tool non enregistré n'existait tout
simplement pas pour ce processus. En HTTP, un même processus sert tous les profils et le
profil ne s'apprend qu'à la requête (depuis le jeton) : les 8 tools sont donc désormais
toujours enregistrés, et c'est le décorateur `_gouverne` — déjà le point de passage unique —
qui résout le périmètre, vérifie le droit et journalise à CHAQUE appel, refus compris.

Les imports de sorabel_sql.tools sont aliasés pour éviter toute collision de nom avec les
fonctions MCP de même nom définies plus bas (ask_database, get_schema, check_stock,
order_status) — sans l'alias, la fonction imbriquée masquerait l'import au lieu de l'appeler.
"""

from __future__ import annotations

import inspect
import time
from typing import Any, Callable

from gouvernance.journal import journaliser
from sorabel_rag.documents import lister_sources, obtenir_document
from sorabel_rag.generation import repondre
from sorabel_rag.recherche import rechercher
from sorabel_sql.tools import ask_database as _sql_ask_database
from sorabel_sql.tools import check_stock as _sql_check_stock
from sorabel_sql.tools import get_schema as _sql_get_schema
from sorabel_sql.tools import order_status as _sql_order_status


def enregistrer_tools(mcp, resolveur_perimetre: Callable[[], Any]) -> None:
    """Enregistre les 8 tools. Le périmètre est résolu à CHAQUE appel.

    En stdio, un processus servait un profil et `tools/list` filtré tenait lieu
    d'intercepteur d'entrée. En HTTP, le processus sert tout le monde : le contrôle
    descend donc dans le décorateur, qui reste le point de passage unique.

    Args:
        mcp: Instance FastMCP où enregistrer les tools
        resolveur_perimetre: Appelé sans argument à chaque requête, renvoie le Perimetre
            du profil courant (ex. déduit du jeton d'authentification). Peut lever si
            l'identité est inconnue ou absente.
    """

    def _gouverne(nom_tool: str) -> Callable:
        """Résout le périmètre, applique la matrice, journalise — dans cet ordre.

        Un refus est journalisé comme un appel : c'est ce que le brief demande, et ce que
        l'architecture stdio ne permettait pas puisqu'un tool non autorisé n'existait pas.
        """
        def decorateur(func: Callable) -> Callable:
            def enveloppe(*args: Any, **kwargs: Any) -> dict:
                debut = time.monotonic()
                try:
                    perimetre = resolveur_perimetre()
                except Exception as erreur:
                    journaliser(
                        profil="inconnu", tool=nom_tool, autorise=False,
                        statut="non_autorise", entrees=kwargs,
                        duree_ms=(time.monotonic() - debut) * 1000,
                        motif=str(erreur),
                    )
                    return {
                        "statut": "non_autorise",
                        "message": "Identité inconnue : aucun profil ne vous est attribué.",
                    }

                if not perimetre.peut_appeler(nom_tool):
                    journaliser(
                        profil=perimetre.profil, tool=nom_tool, autorise=False,
                        statut="non_autorise", entrees=kwargs,
                        duree_ms=(time.monotonic() - debut) * 1000,
                        motif="tool hors perimetre du profil",
                    )
                    return {
                        "statut": "non_autorise",
                        "message": f"le profil {perimetre.profil!r} n'a pas accès au tool {nom_tool!r}",
                    }

                resultat = func(*args, perimetre=perimetre, **kwargs)
                journaliser(
                    profil=perimetre.profil, tool=nom_tool, autorise=True,
                    statut=resultat.get("statut", "ok"), entrees=kwargs,
                    sql=resultat.get("sql"), n_lignes=resultat.get("n_lignes", 0),
                    duree_ms=(time.monotonic() - debut) * 1000,
                    motif=resultat.get("message"),
                )
                return resultat

            # Pas de functools.wraps ici : il copierait __wrapped__, et inspect.signature
            # (utilisé par FastMCP pour construire le schéma exposé au client) le suit par
            # défaut jusqu'à la signature de `func` — laquelle contient encore `perimetre`.
            # On copie donc explicitement nom et docstring, puis on pose une signature
            # amputée du paramètre `perimetre` : il est injecté par ce décorateur, jamais
            # fourni par l'appelant, et ne doit donc jamais apparaître dans le schéma.
            enveloppe.__name__ = func.__name__
            enveloppe.__doc__ = func.__doc__
            # eval_str=True : ce module utilise `from __future__ import annotations`, donc les
            # annotations de `func` sont des chaînes ("dict", "str | None", ...) tant qu'on ne
            # les évalue pas explicitement. Sans ça, FastMCP verrait un type de retour littéral
            # "dict" (une chaîne) au lieu du type `dict`, ce qui change silencieusement la forme
            # de la sortie structurée du tool exposé au client.
            signature = inspect.signature(func, eval_str=True)
            parametres = [p for p in signature.parameters.values() if p.name != "perimetre"]
            enveloppe.__signature__ = signature.replace(parameters=parametres)
            return enveloppe
        return decorateur

    @mcp.tool()
    @_gouverne("answer_question")
    def answer_question(question: str, *, perimetre) -> dict:
        """Réponse rédigée avec sources, à partir du corpus documentaire Sorabel.
        N'utilisez PAS ce tool pour obtenir des extraits bruts : voyez search_docs.
        Statuts possibles : ok, hors_corpus (aucune réponse trouvée, à afficher tel quel,
        pas comme une panne)."""
        return repondre(question, perimetre=perimetre)

    @mcp.tool()
    @_gouverne("search_docs")
    def search_docs(requete: str, k: int = 5, type_document: str | None = None, *, perimetre) -> dict:
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

    @mcp.tool()
    @_gouverne("get_document")
    def get_document(
        doc_id: str | None = None,
        reference: str | None = None,
        version: str | None = None,
        *, perimetre,
    ) -> dict:
        """Document canonique complet, par doc_id OU par (reference + version optionnelle
        — version courante par défaut si omise). Voir list_sources ou search_docs pour
        obtenir un doc_id ou une référence. Statuts : ok, hors_schema (introuvable, ou
        reference ambiguë entre plusieurs types de document), non_autorise (collection
        hors périmètre du profil)."""
        return obtenir_document(doc_id, reference, version, perimetre=perimetre)

    @mcp.tool()
    @_gouverne("list_sources")
    def list_sources(type_document: str | None = None, *, perimetre) -> dict:
        """Inventaire des documents indexés et de leurs versions, reflète le périmètre
        du profil (une note confidentielle hors périmètre n'apparaît pas)."""
        return lister_sources(type_document, perimetre=perimetre)

    @mcp.tool()
    @_gouverne("ask_database")
    def ask_database(question: str, *, perimetre) -> dict:
        """Question en langage naturel sur les données Sorabel (produits, stocks, clients,
        commandes, ventes). Utilisez ce tool quand la question demande un CALCUL ou un
        AGRÉGAT. Lecture seule ; renvoie toujours le SQL exécuté ou rejeté. Statuts :
        ok, hors_schema, non_autorise, refuse_ecriture."""
        return _sql_ask_database(question, perimetre)

    @mcp.tool()
    @_gouverne("get_schema")
    def get_schema(*, perimetre) -> dict:
        """Schéma commenté des tables SQL tel que ce profil le voit (mêmes colonnes que
        celles disponibles via ask_database)."""
        return _sql_get_schema(perimetre)

    @mcp.tool()
    @_gouverne("check_stock")
    def check_stock(ref: str, *, perimetre) -> dict:
        """Stock par entrepôt pour UNE référence précise (format REF-XXXX). Utilisez ce
        tool quand la question porte sur une référence précise, pas un agrégat — pour un
        agrégat (ex. "quelles références sont sous le seuil ?"), voyez ask_database."""
        return _sql_check_stock(ref)

    @mcp.tool()
    @_gouverne("order_status")
    def order_status(order_id: str, *, perimetre) -> dict:
        """Statut, date et montant d'UNE commande précise (format CMD-AAAA-NNNN)."""
        return _sql_order_status(order_id)
