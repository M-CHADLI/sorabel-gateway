"""get_document et list_sources : accès direct aux documents canoniques et au manifeste."""

from sorabel_rag.documents import lister_sources, obtenir_document


class _PerimetreSansConfidentielles:
    def collections_autorisees(self):
        return frozenset({"fiches", "notices", "sav", "notes_operationnelles"})


class _PerimetreComplet:
    def collections_autorisees(self):
        return frozenset(
            {"fiches", "notices", "sav", "notes_operationnelles", "notes_confidentielles"}
        )


def test_obtenir_document_existant():
    resultat = obtenir_document("fiche_technique:REF-1024:v2.1")
    assert resultat["statut"] == "ok"
    assert resultat["document"]["reference"] == "REF-1024"
    assert resultat["document"]["type_document"] == "fiche_technique"


def test_obtenir_document_inexistant_est_hors_schema():
    resultat = obtenir_document("fiche_technique:REF-0000:v1.0")
    assert resultat["statut"] == "hors_schema"


def test_obtenir_document_sans_perimetre_nest_pas_restreint():
    doc_id = "note_interne:note-2024-03-03-politique-tarifaire-21:v1.0"
    resultat = obtenir_document(doc_id)
    assert resultat["statut"] == "ok"


def test_obtenir_document_note_confidentielle_refusee_hors_perimetre():
    doc_id = "note_interne:note-2024-03-03-politique-tarifaire-21:v1.0"
    resultat = obtenir_document(doc_id, perimetre=_PerimetreSansConfidentielles())
    assert resultat["statut"] == "non_autorise"


def test_obtenir_document_note_confidentielle_autorisee_avec_le_bon_perimetre():
    doc_id = "note_interne:note-2024-03-03-politique-tarifaire-21:v1.0"
    resultat = obtenir_document(doc_id, perimetre=_PerimetreComplet())
    assert resultat["statut"] == "ok"


def test_obtenir_document_fiche_technique_nest_jamais_restreint():
    # "fiches" est autorisée pour les deux périmètres de test : jamais de faux refus.
    resultat = obtenir_document(
        "fiche_technique:REF-1024:v2.1", perimetre=_PerimetreSansConfidentielles()
    )
    assert resultat["statut"] == "ok"


def test_obtenir_document_par_reference_resout_la_version_courante():
    # REF-1024 n'a qu'une fiche technique (v1.0, v2.1) — pas de notice : sans ambiguïté.
    resultat = obtenir_document(reference="REF-1024")
    assert resultat["statut"] == "ok"
    assert resultat["document"]["version"] == "2.1"


def test_obtenir_document_par_reference_et_version_explicite():
    resultat = obtenir_document(reference="REF-1024", version="1.0")
    assert resultat["statut"] == "ok"
    assert resultat["document"]["version"] == "1.0"


def test_obtenir_document_par_reference_ambigue_entre_fiche_et_notice():
    # REF-1459 a À LA FOIS une fiche technique ET une notice : la référence seule ne suffit
    # pas à choisir.
    resultat = obtenir_document(reference="REF-1459")
    assert resultat["statut"] == "hors_schema"
    assert "ambigu" in resultat["message"].lower()


def test_obtenir_document_par_reference_inconnue():
    resultat = obtenir_document(reference="REF-0000")
    assert resultat["statut"] == "hors_schema"


def test_obtenir_document_par_reference_version_inconnue():
    resultat = obtenir_document(reference="REF-1024", version="9.9")
    assert resultat["statut"] == "hors_schema"


def test_obtenir_document_sans_doc_id_ni_reference_est_hors_schema():
    resultat = obtenir_document()
    assert resultat["statut"] == "hors_schema"


def test_lister_sources_filtre_par_type_document():
    resultat = lister_sources(type_document="procedure_sav")
    assert resultat["statut"] == "ok"
    assert len(resultat["sources"]) > 0
    assert all(s["type_document"] == "procedure_sav" for s in resultat["sources"])


def test_lister_sources_exclut_notes_confidentielles_hors_perimetre():
    resultat = lister_sources(
        type_document="note_interne", perimetre=_PerimetreSansConfidentielles()
    )
    cles = {s["cle_groupe"] for s in resultat["sources"]}
    assert "note_interne:note-2024-03-03-politique-tarifaire-21" not in cles
    assert "note_interne:note-2024-06-05-logistique-08" in cles


def test_lister_sources_inclut_notes_confidentielles_avec_le_bon_perimetre():
    resultat = lister_sources(type_document="note_interne", perimetre=_PerimetreComplet())
    cles = {s["cle_groupe"] for s in resultat["sources"]}
    assert "note_interne:note-2024-03-03-politique-tarifaire-21" in cles
