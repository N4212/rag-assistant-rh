from prefect import flow, task
from prefect.logging import get_run_logger

from src.evaluation import evaluer_configuration
from src.experimentation import lancer_run

import requests

# Configuration retenue à l'issue du plan d'expérience
COLLECTION = "rh_taille500_chev100"
TAILLE_CHUNK = 500
CHEVAUCHEMENT = 100
TOP_K = 5
MODELE_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"
MODELE_LLM = "gemini-3.5-flash-lite"

URL_WEBHOOK_N8N = "http://localhost:5678/webhook/alerte-qualite-rag"

SEUIL_ALERTE = 0.90


@task(retries=1, retry_delay_seconds=60)
def evaluer_et_enregistrer() -> dict:
    """Rejoue le jeu de questions et enregistre le run dans MLflow."""
    rapport = lancer_run(
        nom_collection=COLLECTION,
        taille_chunk=TAILLE_CHUNK,
        chevauchement=CHEVAUCHEMENT,
        top_k=TOP_K,
        modele_embedding=MODELE_EMBEDDING,
        modele_llm=MODELE_LLM,
    )
    return rapport["metriques"]


@task
def verifier_seuil(metriques: dict, seuil: float) -> dict:
    """Compare le taux mesuré au seuil et prépare le verdict."""
    logger = get_run_logger()

    taux = metriques["taux_llm"]
    alerte = taux < seuil

    if alerte:
        logger.warning(
            f"Qualité dégradée : {taux:.1%} sous le seuil de {seuil:.0%}"
        )
    else:
        logger.info(f"Qualité conforme : {taux:.1%}")

    return {
        "alerte": alerte,
        "taux": taux,
        "seuil": seuil,
        "erreurs_techniques": metriques["nb_erreurs_techniques"],
    }

@task(retries=2, retry_delay_seconds=30)
def declencher_alerte(verdict: dict) -> bool:
    """Notifie n8n si le seuil est franchi."""
    logger = get_run_logger()

    if not verdict["alerte"]:
        logger.info("Pas d'alerte à envoyer")
        return False

    reponse = requests.post(
        URL_WEBHOOK_N8N,
        json={
            "taux": verdict["taux"],
            "seuil": verdict["seuil"],
            "alerte": verdict["alerte"],
            "erreurs_techniques": verdict["erreurs_techniques"],
        },
        timeout=10,
    )
    reponse.raise_for_status()

    logger.warning(f"Alerte envoyée à n8n (taux : {verdict['taux']:.1%})")
    return True

@task
def generer_rapport() -> str:
    """Régénère le rapport de suivi à partir de l'historique MLflow."""
    from src.rapport_qualite import (
        DOSSIER_RAPPORTS,
        charger_runs,
        separer_phases,
        graphique_configurations,
        graphique_suivi,
        generer_markdown,
    )

    logger = get_run_logger()

    DOSSIER_RAPPORTS.mkdir(exist_ok=True)
    runs = charger_runs()
    plan, suivi = separer_phases(runs)

    graphique_configurations(plan, DOSSIER_RAPPORTS / "configurations.png")
    graphique_suivi(suivi, DOSSIER_RAPPORTS / "suivi.png")
    chemin = DOSSIER_RAPPORTS / "rapport_qualite.md"
    generer_markdown(plan, suivi, chemin)

    logger.info(f"Rapport régénéré : {len(suivi)} exécutions de suivi")
    return str(chemin)

@flow(name="surveillance-assistant-rag")
def surveiller_qualite(seuil: float = SEUIL_ALERTE) -> dict:
    """Flux principal : évalue, enregistre, vérifie le seuil, alerte, rapporte."""
    metriques = evaluer_et_enregistrer()
    verdict = verifier_seuil(metriques, seuil)
    declencher_alerte(verdict)
    generer_rapport()
    return verdict

if __name__ == "__main__":
    import sys

    # Mode planifié : python -m src.flux_surveillance --planifier
    if "--planifier" in sys.argv:
        surveiller_qualite.serve(
            name="surveillance-quotidienne",
            cron="0 2 * * *",          # tous les jours à 2 h du matin
            tags=["rag", "qualite"],
        )
    else:
        # Mode manuel : exécution immédiate
        resultat = surveiller_qualite()
        print(f"\nTaux mesuré : {resultat['taux']:.1%}")
        print(f"Seuil        : {resultat['seuil']:.0%}")
        print(f"Alerte       : {'OUI' if resultat['alerte'] else 'non'}")