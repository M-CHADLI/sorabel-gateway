"""Choisit l'implémentation du dépôt d'identités selon l'environnement, et calcule les
droits d'un profil depuis la matrice figée dans l'image.

Ce module ne parle jamais au serveur MCP : la matrice est un fichier en lecture seule,
identique pour les deux services (§5 de la conception GCP). Calculer les droits ici plutôt
que via `tools/list` est une décision délibérée (revue de la Task 4) : depuis que le
périmètre est résolu par requête, `tools/list` renvoie les 8 tools à tout appelant, et ne
dit donc plus rien sur ce qu'un profil PEUT appeler.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from gouvernance.modeles import CodeTool, charger_matrice
from gouvernance.perimetre import Perimetre

RACINE = Path(__file__).resolve().parent.parent


@functools.lru_cache(maxsize=1)
def _matrice():
    return charger_matrice(RACINE / "gouvernance" / "gouvernance.db")


def tools_accordes(profil: str) -> frozenset[str]:
    """Les tools que ce profil peut appeler, lus dans la matrice — jamais dans `tools/list`."""
    perimetre = Perimetre(profil, _matrice())
    return frozenset(t for t in CodeTool.__args__ if perimetre.peut_appeler(t))


@functools.lru_cache(maxsize=1)
def depot_identites():
    # Trace explicite de l'implémentation choisie : une variable d'environnement oubliée ou
    # mal orthographiée sur le déploiement fait retomber silencieusement sur SQLite, chaque
    # instance Cloud Run écrivant alors dans sa propre copie éphémère de l'image — invisible
    # du serveur MCP. Un simple message sur stdout, cohérent avec `SORABEL_JOURNAL=stdout`.
    if os.environ.get("SORABEL_DEPOT") == "firestore":
        from google.cloud import firestore

        from gouvernance.identites_firestore import DepotIdentitesFirestore

        print("depot_identites : implémentation Firestore (SORABEL_DEPOT=firestore)")
        return DepotIdentitesFirestore(
            firestore.Client(), profils_valides=frozenset(_matrice().profils)
        )

    from gouvernance.identites import DepotIdentitesSqlite

    valeur = os.environ.get("SORABEL_DEPOT")
    print(f"depot_identites : implémentation SQLite (SORABEL_DEPOT={valeur!r})")
    return DepotIdentitesSqlite(RACINE / "gouvernance" / "gouvernance.db")
