"""Barrières 1 et 4 (sur 4, E3) : connexion lecture seule, LIMIT par défaut, timeout.

La barrière 1 est la seule vraiment infranchissable : elle est appliquée par SQLite
lui-même (`mode=ro`), pas par notre code. Les autres protègent contre ce qu'elle laisse
passer (une lecture légitime mais hors périmètre, une requête lente ou cartésienne).
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

CHEMIN_DB = Path(__file__).resolve().parent.parent / "data" / "sorabel.db"
LIMIT_DEFAUT = 200
TIMEOUT_SECONDES = 5.0

MOTIF_LIMIT = re.compile(r"\blimit\s+\d+\s*$", re.IGNORECASE)


def _avec_limit(sql: str) -> str:
    return sql if MOTIF_LIMIT.search(sql) else f"{sql} LIMIT {LIMIT_DEFAUT}"


def executer(sql: str, params: tuple = ()) -> dict:
    """`sql` doit déjà avoir passé `validation.valider()` pour les appels génératifs — cette
    fonction reste malgré tout la dernière ligne de défense en lecture seule."""
    sql_avait_deja_un_limit = bool(MOTIF_LIMIT.search(sql))
    sql_limite = _avec_limit(sql)

    uri = f"file:{CHEMIN_DB.as_posix()}?mode=ro"
    connexion = sqlite3.connect(uri, uri=True)
    debut = time.monotonic()

    def _verifier_timeout() -> int:
        return 1 if time.monotonic() - debut > TIMEOUT_SECONDES else 0

    connexion.set_progress_handler(_verifier_timeout, 1000)
    try:
        curseur = connexion.execute(sql_limite, params)
        colonnes = [d[0] for d in curseur.description] if curseur.description else []
        lignes = curseur.fetchall()
    except sqlite3.OperationalError as erreur:
        if "interrupted" in str(erreur).lower():
            raise TimeoutError(
                f"requête interrompue après {TIMEOUT_SECONDES}s (barrière timeout)"
            ) from erreur
        raise
    finally:
        connexion.close()

    return {
        "sql": sql_limite,
        "colonnes": colonnes,
        "lignes": [list(ligne) for ligne in lignes],
        "n_lignes": len(lignes),
        "tronque": len(lignes) == LIMIT_DEFAUT and not sql_avait_deja_un_limit,
    }
