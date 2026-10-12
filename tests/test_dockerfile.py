"""Garde-fou statique : l'image Docker copie tout ce que le code importe, et chaque enseigne
avec les données qu'elle sert — jamais avec son corpus.

Le Dockerfile copie une liste fermée de dossiers. Un paquet ajouté au code mais oublié dans
le Dockerfile ne casse aucun test et ne se voit qu'au démarrage du conteneur. Il en va de même
d'une enseigne ajoutée sous enseignes/ : son serveur démarrerait sans base ni index. On
compare donc, sans jamais appeler docker, les imports réels et les chemins de chaque
`enseigne.toml` aux instructions de chaque étape.
"""

from __future__ import annotations

import ast
import posixpath
import re
import shlex
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

from sorabel_enseigne import ENSEIGNE_PAR_DEFAUT, enseigne, enseignes_disponibles

RACINE = Path(__file__).resolve().parent.parent
PAQUETS = {
    dossier.name
    for dossier in RACINE.iterdir()
    if dossier.is_dir() and (dossier / "__init__.py").exists() and dossier.name != "tests"
}
# Identifiant du secret BuildKit que l'étape `build` de cloudbuild.yaml fournit
# (`--secret id=...`) : un RUN qui monterait un autre identifiant n'aurait pas la clé.
SECRET_EMBEDDINGS = "azure_embedding_key"
# Variable que lit sorabel_rag/index.py : monter le secret ne la renseigne pas, c'est au RUN de
# lire /run/secrets/<id> et de l'exporter sous ce nom.
VARIABLE_CLE = "AZURE_EMBEDDING_API_KEY"


def _imports_du_projet(fichier: Path) -> set[str]:
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    noms: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
            noms.add(noeud.module.split(".")[0])
    return noms & PAQUETS


def _fermeture(depart: set[str]) -> set[str]:
    """Paquets atteignables depuis `depart` : on scanne tous les `.py` de chaque paquet."""
    vus: set[str] = set()
    a_voir = set(depart)
    while a_voir:
        paquet = a_voir.pop()
        if paquet in vus:
            continue
        vus.add(paquet)
        for fichier in (RACINE / paquet).rglob("*.py"):
            a_voir |= _imports_du_projet(fichier) - vus
    return vus


def _etapes() -> list[list[str]]:
    """Sources des `COPY` sans `--from`, une liste par étape (blocs séparés par `FROM`)."""
    etapes: list[list[str]] = []
    for ligne in (RACINE / "Dockerfile").read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if re.match(r"FROM\s", ligne, re.IGNORECASE):
            etapes.append([])
        elif re.match(r"COPY\s", ligne, re.IGNORECASE):
            arguments = ligne.split()[1:]
            if any(a.startswith("--from") for a in arguments):
                continue
            arguments = [a for a in arguments if not a.startswith("--")]
            etapes[-1].extend(arguments[:-1])
    return etapes


def _premiers_composants(sources: list[str]) -> set[str]:
    return {source.strip("/").split("/")[0] for source in sources}


def test_etape_finale_copie_la_fermeture_de_mcp_server_et_front():
    attendus = _fermeture({"mcp_server", "front"})
    copies = _premiers_composants(_etapes()[-1])
    assert attendus - copies == set(), f"paquets non copies dans l'image servie : {attendus - copies}"


def test_etape_index_copie_la_fermeture_des_scripts_de_construction():
    departs: set[str] = set()
    for script in ("seed_gouvernance.py", "ingerer.py", "indexer.py"):
        departs |= _imports_du_projet(RACINE / "scripts" / script)
    attendus = _fermeture(departs)
    copies = _premiers_composants(_etapes()[0])
    assert attendus - copies == set(), f"paquets non copies a l'etape index : {attendus - copies}"


def test_toml_de_l_enseigne_copie_avec_le_paquet_sans_jamais_copier_enseignes_entier():
    for sources in _etapes():
        normalisees = {source.strip("/") for source in sources}
        # `enseignes/` en bloc emporterait les corpus de toutes les enseignes, et leurs
        # sorties locales : chaque étape copie nommément ce qu'il lui faut.
        assert "enseignes" not in normalisees
        if "sorabel_enseigne" in _premiers_composants(sources):
            assert "enseignes/sorabel/enseigne.toml" in normalisees


# --- Enseignes -----------------------------------------------------------------------------
#
# `_etapes()` lit le Dockerfile ligne à ligne et écarte les `COPY --from` : assez pour les
# paquets, pas pour les enseignes, dont les données servies viennent de l'étape index et dont
# la construction tient dans des `RUN` écrits sur plusieurs lignes. D'où une seconde lecture,
# qui garde l'ordre du fichier : une donnée copiée APRÈS la commande qui la lit ne sert à rien.
#
# Chaque contrôle renvoie la liste de ses fautes plutôt que d'échouer lui-même : les mêmes
# fonctions jugent le vrai Dockerfile et, plus bas, des Dockerfile délibérément cassés — un
# garde-fou qui ne détecterait rien passerait aussi.


@dataclass(frozen=True)
class Copie:
    depuis: str | None  # étape source (`--from`), None pour le contexte de build
    # Chemins vus depuis la racine du dépôt : le Dockerfile reproduit l'arborescence du dépôt
    # sous le WORKDIR (/app) de chaque étape, et le moteur résout ses chemins depuis là.
    source: str
    destination: str


@dataclass(frozen=True)
class Commande:
    script: str
    # Valeur de SORABEL_ENSEIGNE pour cette commande, résolue comme enseigne_active() : la
    # variable de la commande, sinon celle de l'étape (ENV), sinon l'enseigne par défaut.
    enseigne: str
    secret_monte: bool
    # La clé est dans l'environnement de CETTE commande, lue depuis le secret monté : une clé
    # lue par la commande voisine du même RUN ne profite pas à celle-ci.
    cle_lue: bool


@dataclass(frozen=True)
class RunAvecSecret:
    """Un RUN qui monte le secret des embeddings. `cle_lue` : au moins une commande de ce RUN
    reçoit la clé, lue depuis le secret, dans VARIABLE_CLE."""

    cle_lue: bool


@dataclass
class Etape:
    nom: str | None
    workdir: str = "/"
    env: dict[str, str] = field(default_factory=dict)
    evenements: list[Copie | Commande | RunAvecSecret] = field(default_factory=list)

    @property
    def copies(self) -> list[Copie]:
        return [e for e in self.evenements if isinstance(e, Copie)]

    @property
    def commandes(self) -> list[Commande]:
        return [e for e in self.evenements if isinstance(e, Commande)]

    @property
    def runs_avec_secret(self) -> list[RunAvecSecret]:
        return [e for e in self.evenements if isinstance(e, RunAvecSecret)]


def _texte_dockerfile() -> str:
    return (RACINE / "Dockerfile").read_text(encoding="utf-8")


def _instructions(texte: str) -> list[tuple[str, str]]:
    """(mot-clé, arguments) de chaque instruction, continuations jointes, commentaires et
    lignes vides écartés — Docker fait de même à l'intérieur d'une instruction continuée."""
    instructions: list[tuple[str, str]] = []
    en_cours = ""
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        if ligne.endswith("\\"):
            en_cours += ligne[:-1] + " "
            continue
        mot, _, arguments = (en_cours + ligne).partition(" ")
        instructions.append((mot.upper(), arguments.strip()))
        en_cours = ""
    return instructions


def _options(arguments: str) -> tuple[list[str], str]:
    """Sépare les options `--x=y` placées en tête d'une instruction du reste de la ligne."""
    options = []
    while arguments.startswith("--"):
        option, _, arguments = arguments.partition(" ")
        options.append(option)
        arguments = arguments.lstrip()
    return options, arguments


def _depuis_workdir(chemin: str, workdir: str) -> str:
    return posixpath.relpath(posixpath.normpath(posixpath.join(workdir, chemin)), workdir)


def _lire_copie(etape: Etape, etapes: list[Etape], arguments: str) -> None:
    options, reste = _options(arguments)
    depuis = next((o.split("=", 1)[1] for o in options if o.startswith("--from=")), None)
    *sources, destination = reste.split()
    for source in sources:
        if depuis is None:
            relative = posixpath.normpath(source)
        else:
            # Une source `--from` est un chemin du système de fichiers de l'étape source.
            (origine,) = [e for e in etapes if e.nom == depuis]
            relative = _depuis_workdir(posixpath.join("/", source), origine.workdir)
        # Un fichier copié dans un dossier (destination en `/`) y garde son nom ; un dossier
        # copié (source en `/`) y verse son contenu.
        cible = destination
        if destination.endswith("/") and not source.endswith("/"):
            cible = posixpath.join(destination, posixpath.basename(source))
        etape.evenements.append(Copie(depuis, relative, _depuis_workdir(cible, etape.workdir)))


def _lit_la_cle(environnement: dict[str, str]) -> bool:
    """VARIABLE_CLE vient-elle du secret monté (`$(cat /run/secrets/<id>)` ou `$(< …)`) ?
    Une valeur littérale, ou lue ailleurs, ne prouve pas que la clé du build arrive."""
    valeur = environnement.get(VARIABLE_CLE, "")
    return re.search(rf"(?:cat\s+|<\s*)/run/secrets/{SECRET_EMBEDDINGS}\b", valeur) is not None


def _lire_run(etape: Etape, arguments: str) -> None:
    options, script_shell = _options(arguments)
    secret = any(
        o.startswith("--mount=") and "type=secret" in o and f"id={SECRET_EMBEDDINGS}" in o
        for o in options
    )
    # Affectations qui valent pour la suite du RUN : `export X=…` ou `X=… ;` sans commande.
    # Celles préfixant une commande (`X=… cmd`) ne valent que pour elle.
    persistantes: dict[str, str] = {}
    cle_lue_du_run = False
    for commande in re.split(r"&&|\|\||;", script_shell):
        jetons = shlex.split(commande)
        if jetons and jetons[0] == "export":
            jetons.pop(0)
        assignations = {}
        while jetons and re.match(r"[A-Za-z_]\w*=", jetons[0]):
            cle, _, valeur = jetons.pop(0).partition("=")
            assignations[cle] = valeur
        if not jetons:
            persistantes.update(assignations)
            cle_lue_du_run = cle_lue_du_run or _lit_la_cle(persistantes)
            continue
        environnement = persistantes | assignations
        cle_lue = _lit_la_cle(environnement)
        cle_lue_du_run = cle_lue_du_run or cle_lue
        script = next((j for j in jetons if j.endswith(".py")), None)
        if script is None:
            continue
        nom = (
            environnement.get("SORABEL_ENSEIGNE")
            or etape.env.get("SORABEL_ENSEIGNE")
            or ENSEIGNE_PAR_DEFAUT
        )
        etape.evenements.append(Commande(posixpath.normpath(script), nom, secret, cle_lue))
    if secret:
        etape.evenements.append(RunAvecSecret(cle_lue_du_run))


def _etapes_detaillees(texte: str) -> list[Etape]:
    etapes: list[Etape] = []
    for mot, arguments in _instructions(texte):
        if mot == "FROM":
            morceaux = arguments.split()
            nom = morceaux[2] if len(morceaux) >= 3 and morceaux[1].upper() == "AS" else None
            etapes.append(Etape(nom))
        elif mot == "WORKDIR":
            etapes[-1].workdir = posixpath.normpath(posixpath.join(etapes[-1].workdir, arguments))
        elif mot == "ENV":
            for paire in shlex.split(arguments):
                cle, egal, valeur = paire.partition("=")
                if egal:
                    etapes[-1].env[cle] = valeur
        elif mot == "COPY":
            _lire_copie(etapes[-1], etapes, arguments)
        elif mot == "RUN":
            _lire_run(etapes[-1], arguments)
    return etapes


def _etape_index(etapes: list[Etape]) -> Etape:
    (index,) = [etape for etape in etapes if etape.nom == "index"]
    return index


def _depuis_racine(chemin: Path) -> str:
    return chemin.relative_to(RACINE).as_posix()


def _emporte(source: str, dossier: str) -> bool:
    """Copier `source` emporte-t-il tout ou partie de `dossier` ? Oui s'il s'agit du dossier,
    d'un de ses parents (jusqu'au contexte entier, `.`), d'un élément qu'il contient, ou d'un
    motif qui désigne l'un d'eux."""
    if source == "." or source.startswith(dossier + "/"):
        return True
    parties = dossier.split("/")
    return any(fnmatchcase("/".join(parties[:i]), source) for i in range(1, len(parties) + 1))


def _manques_de_l_etape_servie(etapes: list[Etape]) -> list[str]:
    index = _etape_index(etapes)
    copies = {copie.destination: copie for copie in etapes[-1].copies}
    manques = []
    for nom in enseignes_disponibles():
        chemins = enseigne(nom).chemins
        attendus = {
            "configuration": (f"enseignes/{nom}/enseigne.toml", None),
            "base SQL": (_depuis_racine(chemins.base_sql), None),
            "matrice d'accès": (_depuis_racine(chemins.gouvernance), None),
            # Canoniques et index ne sont construits que dans l'étape index : copiés depuis le
            # contexte de build, ce seraient des sorties locales — absentes d'un checkout
            # Cloud Build, périmées ailleurs.
            "canoniques": (_depuis_racine(chemins.canonique), index.nom),
            "index": (_depuis_racine(chemins.chroma), index.nom),
        }
        for role, (chemin, provenance) in attendus.items():
            copie = copies.get(chemin)
            if copie is None:
                manques.append(f"{nom} : {role} ({chemin}) absent de l'image servie")
            elif provenance is not None and copie.depuis != provenance:
                manques.append(f"{nom} : {role} ({chemin}) doit venir de l'étape {provenance}")
    return manques


def _fuites_de_corpus(etapes: list[Etape]) -> list[str]:
    corpus = {nom: _depuis_racine(enseigne(nom).chemins.corpus) for nom in enseignes_disponibles()}
    return [
        f"étape {etape.nom or 'finale'} : COPY {copie.source} emporte le corpus {nom} ({dossier})"
        for etape in etapes
        if etape.nom != "index"
        for copie in etape.copies
        for nom, dossier in corpus.items()
        if _emporte(copie.source, dossier)
    ]


def _fautes_de_l_etape_index(etapes: list[Etape]) -> list[str]:
    etape = _etape_index(etapes)
    connues = set(enseignes_disponibles())
    fautes = [
        f"{commande.script} lancé pour une enseigne inconnue : {commande.enseigne!r}"
        for commande in etape.commandes
        if commande.enseigne not in connues
    ]
    matrices_peuplees = {
        enseigne(commande.enseigne).chemins.gouvernance
        for commande in etape.commandes
        if commande.script == "scripts/seed_gouvernance.py" and commande.enseigne in connues
    }
    for nom in sorted(connues):
        chemins = enseigne(nom).chemins
        if chemins.gouvernance not in matrices_peuplees:
            matrice = _depuis_racine(chemins.gouvernance)
            fautes.append(f"{nom} : matrice d'accès {matrice} jamais peuplée")

        def positions(script: str) -> list[int]:
            return [
                i
                for i, evenement in enumerate(etape.evenements)
                if isinstance(evenement, Commande)
                and evenement.enseigne == nom
                and evenement.script == script
            ]

        ingestions, indexations = positions("scripts/ingerer.py"), positions("scripts/indexer.py")
        if not ingestions:
            fautes.append(f"{nom} : aucune ingestion (SORABEL_ENSEIGNE={nom} scripts/ingerer.py)")
            continue
        if not indexations:
            fautes.append(f"{nom} : aucune indexation (SORABEL_ENSEIGNE={nom} scripts/indexer.py)")
            continue
        if indexations[-1] < ingestions[0]:
            fautes.append(f"{nom} : l'indexation précède l'ingestion qui produit ses canoniques")
        if not all(etape.evenements[i].secret_monte for i in indexations):
            fautes.append(f"{nom} : indexation sans le secret BuildKit {SECRET_EMBEDDINGS}")
        # Monté ne veut pas dire lu : l'indexation qui n'a pas la clé dans son environnement
        # échoue (ou, pire, tombe sur une valeur résiduelle) au premier appel d'embeddings.
        if not all(etape.evenements[i].cle_lue for i in indexations):
            fautes.append(
                f"{nom} : indexation sans {VARIABLE_CLE} lue depuis le secret {SECRET_EMBEDDINGS}"
            )
        # La configuration et le corpus doivent être là AVANT l'ingestion qui les lit.
        for prealable in (f"enseignes/{nom}/enseigne.toml", _depuis_racine(chemins.corpus)):
            if not any(
                isinstance(evenement, Copie) and evenement.destination == prealable
                for evenement in etape.evenements[: ingestions[0]]
            ):
                fautes.append(f"{nom} : {prealable} pas copié avant l'ingestion")
    return fautes


def _runs_qui_ne_lisent_pas_la_cle(etapes: list[Etape]) -> list[str]:
    """Tout RUN qui monte le secret doit en lire la clé et l'exporter dans VARIABLE_CLE : un
    montage laissé seul est un RUN qui a l'air d'avoir la clé et ne l'a pas."""
    return [
        f"étape {etape.nom or 'finale'} : un RUN monte le secret {SECRET_EMBEDDINGS} sans en "
        f"lire la clé dans {VARIABLE_CLE}"
        for etape in etapes
        for run in etape.runs_avec_secret
        if not run.cle_lue
    ]


def test_etape_servie_copie_config_base_canoniques_et_index_de_chaque_enseigne():
    manques = _manques_de_l_etape_servie(_etapes_detaillees(_texte_dockerfile()))
    assert not manques, "\n".join(manques)


def test_aucune_etape_servie_ne_copie_un_corpus():
    fuites = _fuites_de_corpus(_etapes_detaillees(_texte_dockerfile()))
    assert not fuites, "\n".join(fuites)


def test_etape_index_construit_l_index_de_chaque_enseigne():
    fautes = _fautes_de_l_etape_index(_etapes_detaillees(_texte_dockerfile()))
    assert not fautes, "\n".join(fautes)


def test_tout_run_qui_monte_le_secret_en_lit_la_cle():
    fautes = _runs_qui_ne_lisent_pas_la_cle(_etapes_detaillees(_texte_dockerfile()))
    assert not fautes, "\n".join(fautes)


_SERVIE = "EXPOSE 8080"
_RUN_KIABI = "RUN --mount=type=secret,id=azure_embedding_key \\\n    SORABEL_ENSEIGNE=kiabi"
_COPIE_CORPUS_KIABI = "COPY enseignes/kiabi/data/corpus/ enseignes/kiabi/data/corpus/\n"
_COPIE_CHROMA_KIABI = (
    "COPY --from=index /app/enseignes/kiabi/data/chroma/ enseignes/kiabi/data/chroma/\n"
)
_COPIE_CANONIQUES_KIABI = (
    "COPY --from=index /app/enseignes/kiabi/data/canonique/ enseignes/kiabi/data/canonique/\n"
)
_INDEXATION_KIABI = 'SORABEL_ENSEIGNE=kiabi AZURE_EMBEDDING_API_KEY="$(cat'
_LECTURE_CLE_KIABI = _INDEXATION_KIABI + ' /run/secrets/azure_embedding_key)"'


@pytest.mark.parametrize(
    ("controle", "ancien", "nouveau", "faute_attendue"),
    [
        pytest.param(
            _fuites_de_corpus, _SERVIE, "COPY enseignes/kiabi/ enseignes/kiabi/\n" + _SERVIE,
            "COPY enseignes/kiabi emporte le corpus kiabi", id="enseigne-copiee-en-bloc",
        ),
        pytest.param(
            _fuites_de_corpus, _SERVIE, "COPY --from=index /app/enseignes/ enseignes/\n" + _SERVIE,
            "COPY enseignes emporte le corpus kiabi", id="enseignes-depuis-l-etape-index",
        ),
        pytest.param(
            _fuites_de_corpus, _SERVIE, "COPY data/ data/\n" + _SERVIE,
            "COPY data emporte le corpus sorabel", id="data-sorabel-en-bloc",
        ),
        pytest.param(
            _manques_de_l_etape_servie, _COPIE_CHROMA_KIABI, "",
            "kiabi : index (enseignes/kiabi/data/chroma) absent", id="index-kiabi-oublie",
        ),
        pytest.param(
            _manques_de_l_etape_servie, _COPIE_CANONIQUES_KIABI,
            _COPIE_CANONIQUES_KIABI.replace("--from=index /app/", ""),
            "kiabi : canoniques (enseignes/kiabi/data/canonique) doit venir de l'étape index",
            id="canoniques-pris-dans-le-contexte",
        ),
        pytest.param(
            _fautes_de_l_etape_index, _INDEXATION_KIABI, 'AZURE_EMBEDDING_API_KEY="$(cat',
            "kiabi : aucune indexation", id="indexation-sur-l-enseigne-par-defaut",
        ),
        pytest.param(
            _fautes_de_l_etape_index, _RUN_KIABI,
            _RUN_KIABI.replace("--mount=type=secret,id=azure_embedding_key ", ""),
            "kiabi : indexation sans le secret", id="secret-non-monte",
        ),
        pytest.param(
            _runs_qui_ne_lisent_pas_la_cle, _LECTURE_CLE_KIABI, "SORABEL_ENSEIGNE=kiabi",
            "monte le secret azure_embedding_key sans en lire la clé",
            id="secret-monte-sans-etre-lu",
        ),
        pytest.param(
            _runs_qui_ne_lisent_pas_la_cle, _INDEXATION_KIABI,
            'SORABEL_ENSEIGNE=kiabi AZURE_EMBEDDING_KEY="$(cat',
            "monte le secret azure_embedding_key sans en lire la clé",
            id="cle-exportee-sous-un-mauvais-nom",
        ),
        pytest.param(
            _fautes_de_l_etape_index, _LECTURE_CLE_KIABI, "SORABEL_ENSEIGNE=kiabi",
            "kiabi : indexation sans AZURE_EMBEDDING_API_KEY lue depuis le secret",
            id="indexation-sans-la-cle",
        ),
        pytest.param(
            _fautes_de_l_etape_index, _COPIE_CORPUS_KIABI, "",
            "kiabi : enseignes/kiabi/data/corpus pas copié avant l'ingestion",
            id="corpus-jamais-copie",
        ),
        pytest.param(
            _fautes_de_l_etape_index,
            "SORABEL_ENSEIGNE=kiabi .venv",
            "SORABEL_ENSEIGNE=kiaby .venv",
            "enseigne inconnue : 'kiaby'",
            id="faute-de-frappe-dans-l-enseigne",
        ),
    ],
)
def test_les_controles_detectent_un_dockerfile_casse(controle, ancien, nouveau, faute_attendue):
    texte = _texte_dockerfile()
    # Si ce motif disparaît du Dockerfile, la mutation ne casse plus rien : mieux vaut un
    # échec franc ici qu'un contrôle qui ne prouve plus rien sans que personne le sache.
    assert texte.count(ancien) == 1, f"motif introuvable ou ambigu dans le Dockerfile : {ancien!r}"
    fautes = controle(_etapes_detaillees(texte.replace(ancien, nouveau)))
    assert any(faute_attendue in faute for faute in fautes), fautes
