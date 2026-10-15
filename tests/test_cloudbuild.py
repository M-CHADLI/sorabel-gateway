"""Garde-fou statique de cloudbuild.yaml : kiabi-mcp reste calqué sur sorabel-mcp, et le front
sait joindre chaque serveur MCP déployé.

Les deux serveurs tournent sur la même image et le même compte de service ; seule l'enseigne
change. Une variable ajoutée à `deploy-mcp` (nouveau secret, nouvel émetteur) et oubliée dans
`deploy-kiabi-mcp` ne casserait aucun test et ne se verrait qu'au démarrage de kiabi-mcp, en
production — de même qu'une substitution mal orthographiée, que Cloud Build refuse au
lancement du build. On compare donc, sans jamais appeler gcloud.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from sorabel_enseigne import ENSEIGNE_PAR_DEFAUT, enseignes_disponibles

RACINE = Path(__file__).resolve().parent.parent
# Ce qui distingue légitimement le serveur MCP d'une enseigne de celui de Sorabel.
PROPRES_A_L_ENSEIGNE = {"SORABEL_ENSEIGNE", "SORABEL_URL_PUBLIQUE"}
# Substitutions utilisateur (préfixe `_`) ; celles que Cloud Build fournit lui-même
# (PROJECT_ID, SHORT_SHA…) n'ont pas à être déclarées. `$$` échappe un `$` de shell, et
# `$$NOM` ne correspond pas : le caractère qui suit le second `$` n'est pas `_`.
SUBSTITUTION = re.compile(r"\$\{?(_[A-Z0-9_]+)\}?")


def _config() -> dict:
    return yaml.safe_load((RACINE / "cloudbuild.yaml").read_text(encoding="utf-8"))


def _etape(config: dict, identifiant: str) -> dict:
    (etape,) = [e for e in config["steps"] if e["id"] == identifiant]
    return etape


def _variables(etape: dict) -> dict[str, str]:
    (brut,) = [
        a.removeprefix("--set-env-vars=") for a in etape["args"] if a.startswith("--set-env-vars=")
    ]
    return dict(paire.split("=", 1) for paire in brut.split(","))


def _arguments_hors_service_et_variables(etape: dict) -> list[str]:
    """`run deploy <service> ...` sans le nom du service ni les variables d'environnement."""
    args = etape["args"]
    return args[:2] + [a for a in args[3:] if not a.startswith("--set-env-vars=")]


def _serveurs_mcp(config: dict) -> dict[str, dict]:
    """Étapes qui déploient un serveur MCP, par enseigne servie."""
    serveurs: dict[str, dict] = {}
    for etape in config["steps"]:
        args = etape.get("args", [])
        if args[:2] == ["run", "deploy"] and "--args=-m,mcp_server.serveur" in args:
            nom = _variables(etape).get("SORABEL_ENSEIGNE") or ENSEIGNE_PAR_DEFAUT
            assert nom not in serveurs, f"deux serveurs MCP déployés pour l'enseigne {nom}"
            serveurs[nom] = etape
    return serveurs


def _chaines(valeur):
    if isinstance(valeur, str):
        yield valeur
    elif isinstance(valeur, dict):
        for element in valeur.values():
            yield from _chaines(element)
    elif isinstance(valeur, list):
        for element in valeur:
            yield from _chaines(element)


def test_kiabi_mcp_est_calque_sur_sorabel_mcp():
    config = _config()
    sorabel, kiabi = _etape(config, "deploy-mcp"), _etape(config, "deploy-kiabi-mcp")

    assert kiabi["args"][:3] == ["run", "deploy", "kiabi-mcp"]
    # Image, région, compte de service, secrets, --async… : tout le reste est identique.
    assert {k: v for k, v in kiabi.items() if k not in ("id", "args")} == {
        k: v for k, v in sorabel.items() if k not in ("id", "args")
    }
    assert _arguments_hors_service_et_variables(kiabi) == _arguments_hors_service_et_variables(
        sorabel
    )

    variables_sorabel, variables_kiabi = _variables(sorabel), _variables(kiabi)
    assert {k: v for k, v in variables_kiabi.items() if k not in PROPRES_A_L_ENSEIGNE} == {
        k: v for k, v in variables_sorabel.items() if k not in PROPRES_A_L_ENSEIGNE
    }
    assert variables_kiabi["SORABEL_ENSEIGNE"] == "kiabi"
    assert (variables_sorabel.get("SORABEL_ENSEIGNE") or ENSEIGNE_PAR_DEFAUT) == "sorabel"
    # Chaque serveur publie sa propre URL : une URL partagée annoncerait l'autre service
    # dans les métadonnées de ressource protégée.
    assert variables_kiabi["SORABEL_URL_PUBLIQUE"] != variables_sorabel["SORABEL_URL_PUBLIQUE"]


def test_le_front_joint_chaque_serveur_mcp_par_l_url_qu_il_publie():
    config = _config()
    serveurs = _serveurs_mcp(config)
    front = _variables(_etape(config, "deploy-front"))

    assert {"sorabel", "kiabi"} <= set(serveurs)
    for nom, etape in serveurs.items():
        assert nom in enseignes_disponibles(), f"SORABEL_ENSEIGNE={nom} : enseigne inconnue"
        if nom == ENSEIGNE_PAR_DEFAUT:
            continue  # le front joint Sorabel par SORABEL_URL_MCP, comme avant Kiabi
        variable = f"SORABEL_URL_MCP_{nom.upper()}"
        assert variable in front, f"deploy-front ne reçoit pas {variable}"
        # La même substitution, telle quelle, des deux côtés : le front appelle l'URL que le
        # serveur publie, et une substitution vide (amorçage, retour arrière) donne au front
        # une variable vide — l'enseigne n'est pas proposée — plutôt qu'une URL fantôme
        # comme « /mcp » qu'un suffixe ajouté ici produirait.
        assert SUBSTITUTION.fullmatch(front[variable]), f"{variable}={front[variable]}"
        assert front[variable] == _variables(etape)["SORABEL_URL_PUBLIQUE"]


def test_chaque_substitution_utilisee_est_declaree_et_inversement():
    config = _config()
    declarees = set(config["substitutions"])
    utilisees = {
        nom
        for section in ("steps", "substitutions", "availableSecrets")
        for chaine in _chaines(config.get(section, {}))
        for nom in SUBSTITUTION.findall(chaine)
    }
    # Une substitution utilisée sans être déclarée fait refuser le build par Cloud Build.
    assert utilisees - declarees == set(), "utilisées sans être déclarées"
    assert declarees - utilisees == set(), "déclarées sans être utilisées"


def test_le_detecteur_de_substitutions_ignore_les_variables_de_shell():
    # L'étape build écrit `$$AZURE_EMBEDDING_API_KEY` (variable de shell échappée) : ce n'est
    # pas une substitution, et le test précédent la réclamerait à tort s'il la comptait.
    assert SUBSTITUTION.findall('echo "$$AZURE_EMBEDDING_API_KEY" "$_IMAGE:${_REGION}"') == [
        "_IMAGE",
        "_REGION",
    ]
