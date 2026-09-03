"""Journalisation (E4, E5) : une ligne JSON par appel, en ajout seul.

Tout appel est journalisé, autorisé comme refusé. On trace la question, la requête et le
volume — jamais le contenu des résultats : un journal ne doit pas devenir une copie de la
base sans les contrôles d'accès de la base.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

CHEMIN_JOURNAL = Path(__file__).resolve().parent.parent / "logs" / "appels.jsonl"


def journaliser(
    *,
    profil: str,
    tool: str,
    autorise: bool,
    statut: str,
    entrees: dict,
    sql: str | None = None,
    n_lignes: int = 0,
    duree_ms: float = 0.0,
    motif: str | None = None,
    code: str | None = None,
) -> None:
    ligne = {
        "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profil": profil,
        "tool": tool,
        "autorise": autorise,
        "statut": statut,
        "code": code,
        "entrees": entrees,
        "sql": sql,
        "n_lignes": n_lignes,
        "duree_ms": duree_ms,
        "motif": motif,
    }
    CHEMIN_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with CHEMIN_JOURNAL.open("a", encoding="utf-8") as fichier:
        fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")
