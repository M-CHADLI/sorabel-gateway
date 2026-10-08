"""Descriptions des tools MCP : elles partent vers les clients par `tools/list`, et c'est sur
elles qu'un LLM client choisit son tool. Elles nomment l'enseigne du processus, jamais une
autre.

tests/instantanes/sorabel/tools_descriptions.json a été capturé sur le code de f19e105, AVANT
que les descriptions ne passent par l'enseigne : pour Sorabel, pas un octet ne doit changer.
S'il diverge, on corrige le code, jamais l'instantané.
"""

import asyncio
import json
from pathlib import Path

from gouvernance.seed import peupler
from mcp_server.serveur import construire_serveur
from tests.test_enseigne_raccordement import PREAMBULE, _executer

INSTANTANE = Path(__file__).resolve().parent / "instantanes" / "sorabel" / "tools_descriptions.json"


def _instantane() -> dict:
    return json.loads(INSTANTANE.read_text(encoding="utf-8"))


def test_descriptions_sorabel_inchangees(tmp_path, monkeypatch):
    chemin = tmp_path / "gouvernance.db"
    peupler(chemin)
    monkeypatch.setenv("SORABEL_TRANSPORT", "stdio")
    monkeypatch.setenv("SORABEL_PROFIL", "support")
    mcp = construire_serveur(chemin_gouvernance_db=chemin)
    descriptions = {t.name: t.description for t in asyncio.run(mcp.list_tools())}
    assert descriptions == _instantane()


# Le serveur de l'enseigne d'essai, construit comme en développement : stdio, matrice lue au
# chemin de gouvernance de l'enseigne.
SCRIPT_DESCRIPTIONS = PREAMBULE + """
import asyncio
os.environ["SORABEL_TRANSPORT"] = "stdio"
os.environ["SORABEL_PROFIL"] = "support"
from mcp_server.serveur import construire_serveur
mcp = construire_serveur()
print(json.dumps({t.name: t.description for t in asyncio.run(mcp.list_tools())}))
"""


def test_les_descriptions_nomment_l_enseigne_active(tmp_path, ecrire_enseigne):
    donnees = tmp_path / "donnees"
    ecrire_enseigne(tmp_path, "essai", donnees.as_posix())
    peupler(donnees / "gouvernance.db")
    descriptions = _executer(SCRIPT_DESCRIPTIONS, tmp_path)
    assert "à partir du corpus documentaire Essai essai." in descriptions["answer_question"]
    assert "sur les données Essai essai (produits," in descriptions["ask_database"]
    assert [nom for nom, texte in descriptions.items() if "Sorabel" in texte] == []
    # Hormis le libellé, ce sont les descriptions de Sorabel au caractère près : rien d'autre
    # ne dépend de l'enseigne.
    assert descriptions == {
        nom: texte.replace("Sorabel", "Essai essai") for nom, texte in _instantane().items()
    }
