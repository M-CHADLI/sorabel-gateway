"""Serveur MCP minimal pour Sorabel — exposé via stdio.

Lance en tant que : python -m mcp_server.serveur
Gouvernance via : SORABEL_PROFIL
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Chemin de la base de gouvernance
RACINE = Path(__file__).resolve().parent.parent
CHEMIN_GOUVERNANCE_DB = str(RACINE / "gouvernance" / "gouvernance.db")


async def _get_perimetre():
    """Charge le périmètre selon le profil de la variable d'environnement."""
    from gouvernance.perimetre import Perimetre
    from gouvernance.modeles import charger_matrice

    profil = os.getenv("SORABEL_PROFIL", "support")
    matrice = charger_matrice(CHEMIN_GOUVERNANCE_DB)
    return Perimetre(profil, matrice)


def _get_tools() -> list[Tool]:
    """Retourne la liste de tous les outils possibles (stub).

    8 tools totaux : 4 RAG + 4 données.
    """
    # Schema minimaliste pour tous les outils
    empty_schema = {"type": "object", "properties": {}}

    return [
        Tool(name="answer_question", description="Répond à une question avec le RAG", inputSchema=empty_schema),
        Tool(name="search_docs", description="Cherche dans le corpus documentaire", inputSchema=empty_schema),
        Tool(name="get_document", description="Récupère un document spécifique", inputSchema=empty_schema),
        Tool(name="list_sources", description="Liste les sources du corpus", inputSchema=empty_schema),
        Tool(name="ask_database", description="Interroge la base de données en SQL", inputSchema=empty_schema),
        Tool(name="get_schema", description="Retourne le schéma SQL filtré par profil", inputSchema=empty_schema),
        Tool(name="check_stock", description="Vérifie le stock d'une référence", inputSchema=empty_schema),
        Tool(name="order_status", description="Consulte l'état d'une commande", inputSchema=empty_schema),
    ]


async def main():
    """Lance le serveur MCP en mode stdio."""
    server = Server("sorabel-mcp")

    @server.list_tools()
    async def list_tools_handler():
        """Implémente tools/list : retourne les outils autorisés pour le profil."""
        perimetre = await _get_perimetre()
        all_tools = _get_tools()
        outils_filtres = [t for t in all_tools if perimetre.peut_appeler(t.name)]
        return outils_filtres

    @server.call_tool()
    async def call_tool_handler(name: str, arguments: dict):
        """Implémente tools/call : exécute un outil selon le profil et les arguments."""
        perimetre = await _get_perimetre()
        tool_name = name
        arguments = arguments or {}

        # Vérifier que l'outil est autorisé
        if not perimetre.peut_appeler(tool_name):
            result_dict = {
                "statut": "non_autorise",
                "message": f"le profil {perimetre.profil!r} n'a pas accès au tool {tool_name!r}",
            }
            return [TextContent(type="text", text=json.dumps(result_dict))]

        # Dispatcher sur les outils implémentés
        if tool_name == "get_schema":
            from sorabel_sql.schema import schema_commente
            schema_text = schema_commente(perimetre)
            result_dict = {
                "statut": "ok",
                "schema": schema_text,
            }
        elif tool_name == "search_docs":
            # Stub : retourner un résultat vide
            result_dict = {
                "statut": "ok",
                "resultats": [],
            }
        elif tool_name == "get_document":
            result_dict = {
                "statut": "ok",
                "document": None,
            }
        elif tool_name == "list_sources":
            result_dict = {
                "statut": "ok",
                "sources": [],
            }
        elif tool_name == "ask_database":
            # Stub : retourner un résultat vide
            result_dict = {
                "statut": "ok",
                "resultats": [],
            }
        elif tool_name == "check_stock":
            result_dict = {
                "statut": "ok",
                "ref": arguments.get("ref"),
                "entrepots": [],
            }
        elif tool_name == "order_status":
            result_dict = {
                "statut": "ok",
                "order_id": arguments.get("order_id"),
                "status": None,
            }
        elif tool_name == "answer_question":
            result_dict = {
                "statut": "ok",
                "reponse": "",
                "sources": [],
            }
        else:
            result_dict = {
                "statut": "erreur",
                "message": f"outil {tool_name} non implémenté",
            }

        return [TextContent(type="text", text=json.dumps(result_dict))]

    # Lancer le serveur en mode stdio
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
