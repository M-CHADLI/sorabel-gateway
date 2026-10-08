# tests/conftest.py
"""Les tests portent sur le moteur, avec Sorabel pour jeu de données (références, corpus et
base réels). Un `ENSEIGNE=kiabi` resté dans le shell ne doit pas les faire échouer : on
fixe l'enseigne avant que pytest n'importe le moindre module du projet."""

import os
from pathlib import Path

import pytest

os.environ["SORABEL_ENSEIGNE"] = "sorabel"

GABARIT_ENSEIGNE = """nom = "{nom_declare}"
libelle = "Essai {nom}"

[chemins]
corpus = "{donnees}/corpus"
canonique = "{donnees}/canonique"
chroma = "{donnees}/chroma"
base_sql = "{donnees}/{nom}.db"
gouvernance = "{donnees}/gouvernance.db"
journal = "{donnees}/appels.jsonl"

[rag]
collection = "{nom}_docs"
presentation = "l'assistant documentaire de {nom}"

[extraction]
pied_de_page = "Document {nom}"

[sql]
nom_base = "{nom}"

[sql.commentaires]
"stocks.entrepot" = "ENTREPOT-{nom}"
"""


@pytest.fixture
def ecrire_enseigne():
    """Écrit `<dossier>/<nom>/enseigne.toml` et renvoie son chemin.

    `donnees` préfixe tous les chemins : relatif à la racine du dépôt, ou absolu — mais
    alors en `as_posix()`, une barre oblique inverse étant un échappement en TOML.
    """

    def _ecrire(dossier: Path, nom: str, donnees: str, nom_declare: str | None = None) -> Path:
        chemin = dossier / nom / "enseigne.toml"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(
            GABARIT_ENSEIGNE.format(nom=nom, nom_declare=nom_declare or nom, donnees=donnees),
            encoding="utf-8",
        )
        return chemin

    return _ecrire
