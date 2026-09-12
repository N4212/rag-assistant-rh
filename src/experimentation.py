import mlflow

from src.evaluation import evaluer_configuration

DOSSIER_MLFLOW = "sqlite:///mlflow.db"
NOM_EXPERIENCE = "assistant-rag-rh"


def lancer_run(
    nom_collection: str,
    taille_chunk: int,
    chevauchement: int,
    top_k: int,
    modele_embedding: str,
    modele_llm: str,
    pause: float = 8.0,
) -> dict:
    """Évalue une configuration et enregistre le run dans MLflow."""
    mlflow.set_tracking_uri(DOSSIER_MLFLOW)
    mlflow.set_experiment(NOM_EXPERIENCE)

    # Le bloc with garantit que le run est correctement clôturé,
    # même si une erreur survient au milieu
    with mlflow.start_run():
        # --- Paramètres : ce que l'on a choisi ---
        mlflow.log_params({
            "collection": nom_collection,
            "taille_chunk": taille_chunk,
            "chevauchement": chevauchement,
            "top_k": top_k,
            "modele_embedding": modele_embedding,
            "modele_llm": modele_llm,
        })

        # --- Exécution de l'évaluation ---
        rapport = evaluer_configuration(nom_collection, top_k, pause)
        m = rapport["metriques"]

        # --- Métriques : ce que l'on a mesuré ---
        mlflow.log_metrics({
            "taux_mots_cles": m["taux_mots_cles"],
            "taux_llm": m["taux_llm"],
            "taux_rappel_source": m["taux_rappel_source"],
            "nb_erreurs_techniques": m["nb_erreurs_techniques"],
        })

        return rapport

from src.indexation import construire_index

# Configurations à comparer : (taille_chunk, chevauchement, top_k)
PLAN_EXPERIENCE = [
    (500, 100, 5),
    (300, 60, 3),
    (800, 160, 3),
    (800, 160, 5),
    (1200, 200, 3),
]


def lancer_plan(configurations: list[tuple], pause: float = 8.0):
    """Enchaîne indexation et évaluation pour chaque configuration."""
    collections_construites = set()

    for i, (taille, chevauchement, top_k) in enumerate(configurations, start=1):
        print(f"\n{'=' * 60}")
        print(f"Configuration {i}/{len(configurations)} : "
              f"taille={taille}, chev={chevauchement}, top_k={top_k}")
        print("=" * 60)

        cle = (taille, chevauchement)
        nom_collection = f"rh_taille{taille}_chev{chevauchement}"

        # On ne réindexe pas si la collection existe déjà :
        # top_k ne dépend pas de l'indexation
        if cle not in collections_construites:
            print("Indexation en cours...")
            construire_index(taille, chevauchement)
            collections_construites.add(cle)
        else:
            print("Collection déjà indexée, réutilisation.")

        rapport = lancer_run(
            nom_collection=nom_collection,
            taille_chunk=taille,
            chevauchement=chevauchement,
            top_k=top_k,
            modele_embedding="paraphrase-multilingual-MiniLM-L12-v2",
            modele_llm="gemini-3.5-flash-lite",
            pause=pause,
        )

        m = rapport["metriques"]
        print(f"\n  → taux LLM : {m['taux_llm']:.1%} | "
              f"rappel : {m['taux_rappel_source']:.1%} | "
              f"erreurs : {m['nb_erreurs_techniques']}")

if __name__ == "__main__":
    lancer_plan(PLAN_EXPERIENCE[1:])