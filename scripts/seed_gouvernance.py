"""Peuple gouvernance/gouvernance.db avec la matrice d'accès. À relancer après toute
modification de gouvernance/seed.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gouvernance.seed import peupler
from sorabel_enseigne import enseigne_active

CHEMIN_DB = enseigne_active().chemins.gouvernance

if __name__ == "__main__":
    peupler(CHEMIN_DB)
    print(f"-> {CHEMIN_DB}")
