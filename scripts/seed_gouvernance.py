"""Peuple gouvernance/gouvernance.db avec la matrice d'accès. À relancer après toute
modification de gouvernance/seed.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gouvernance.seed import peupler

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_DB = RACINE / "gouvernance" / "gouvernance.db"

if __name__ == "__main__":
    peupler(CHEMIN_DB)
    print(f"-> {CHEMIN_DB}")
