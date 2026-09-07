"""Point de passage unique pour choisir l'implémentation du dépôt d'identités.

Avant ce module, le dispatch `SORABEL_DEPOT == "firestore"` existait en double : une fois
dans `front/depot.py`, une fois dans `mcp_server/serveur.py`. Les deux appelants partagent
désormais cette seule fonction — cohérente avec la préférence du projet pour un point de
passage unique plutôt qu'une logique répétée par appelant.
"""

from __future__ import annotations

import os
from pathlib import Path


def choisir_depot(chemin_gouvernance_db: Path, profils_valides: frozenset[str]):
    """Choisit Firestore ou SQLite selon `SORABEL_DEPOT`, et trace le choix sur stdout.

    `profils_valides` est reçu déjà calculé : chaque appelant a sa propre façon d'obtenir
    la matrice (chargée directement côté serveur, mise en cache par process côté front), et
    ce n'est pas à cette fonction de choisir laquelle — seulement de la recevoir.

    Le préfixe de trace ("depot d'identites :") est délibérément indépendant du nom de la
    fonction appelante : `depot_identites` côté front et `construire_serveur` côté serveur
    doivent produire la même trace, grep-able des deux côtés dans les logs Cloud Run.
    """
    if os.environ.get("SORABEL_DEPOT") == "firestore":
        # Import local : ne pas imposer cette dépendance au transport stdio, où elle n'est
        # jamais utilisée.
        from google.cloud import firestore

        from gouvernance.identites_firestore import DepotIdentitesFirestore

        print("depot d'identites : implémentation Firestore (SORABEL_DEPOT=firestore)")
        return DepotIdentitesFirestore(firestore.Client(), profils_valides=profils_valides)

    from gouvernance.identites import DepotIdentitesSqlite

    valeur = os.environ.get("SORABEL_DEPOT")
    print(f"depot d'identites : implémentation SQLite (SORABEL_DEPOT={valeur!r})")
    return DepotIdentitesSqlite(chemin_gouvernance_db)
