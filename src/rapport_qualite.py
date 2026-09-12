from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # backend sans interface graphique
import matplotlib.pyplot as plt
import mlflow

DOSSIER_MLFLOW = "sqlite:///mlflow.db"
NOM_EXPERIENCE = "assistant-rag-rh"
DOSSIER_RAPPORTS = Path("rapports")
SEUIL = 0.90


def charger_runs() -> list[dict]:
    """Récupère tous les runs de l'expérience, du plus ancien au plus récent."""
    mlflow.set_tracking_uri(DOSSIER_MLFLOW)
    client = mlflow.tracking.MlflowClient()

    experience = client.get_experiment_by_name(NOM_EXPERIENCE)
    if experience is None:
        raise RuntimeError(f"Expérience « {NOM_EXPERIENCE} » introuvable")

    runs = client.search_runs(
        experiment_ids=[experience.experiment_id],
        order_by=["attributes.start_time ASC"],
    )

    resultats = []
    for r in runs:
        resultats.append({
            "nom": r.info.run_name,
            "date": datetime.fromtimestamp(r.info.start_time / 1000),
            "taux_llm": r.data.metrics.get("taux_llm"),
            "taux_mots_cles": r.data.metrics.get("taux_mots_cles"),
            "rappel": r.data.metrics.get("taux_rappel_source"),
            "erreurs": r.data.metrics.get("nb_erreurs_techniques"),
            "taille_chunk": r.data.params.get("taille_chunk"),
            "top_k": r.data.params.get("top_k"),
        })

    return resultats

CONFIG_RETENUE = {"taille_chunk": "500", "top_k": "5"}


def separer_phases(runs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Sépare les runs du plan d'expérience de ceux du suivi."""
    suivi = [
        r for r in runs
        if r["taille_chunk"] == CONFIG_RETENUE["taille_chunk"]
        and r["top_k"] == CONFIG_RETENUE["top_k"]
    ]
    # Le premier run de la config retenue appartient encore au plan d'expérience
    plan = [r for r in runs if r not in suivi[1:]]
    return plan, suivi[1:]


def graphique_configurations(plan: list[dict], chemin: Path) -> None:
    """Barres comparant les configurations testées."""
    etiquettes = [f"{r['taille_chunk']}\ntop_k={r['top_k']}" for r in plan]
    taux = [r["taux_llm"] * 100 for r in plan]
    rappel = [r["rappel"] * 100 for r in plan]

    x = range(len(plan))
    largeur = 0.38

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar([i - largeur / 2 for i in x], taux, largeur, label="Taux de réponses correctes")
    ax.bar([i + largeur / 2 for i in x], rappel, largeur, label="Rappel de la source")

    ax.set_xticks(list(x))
    ax.set_xticklabels(etiquettes, fontsize=9)
    ax.set_ylabel("%")
    ax.set_ylim(0, 105)
    ax.set_title("Comparaison des configurations testées")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(chemin, dpi=130)
    plt.close(fig)


def graphique_suivi(suivi: list[dict], chemin: Path) -> None:
    """Courbe d'évolution du taux sur la configuration retenue."""
    dates = [r["date"] for r in suivi]
    taux = [r["taux_llm"] * 100 for r in suivi]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(dates, taux, marker="o", label="Taux de réponses correctes")
    ax.axhline(SEUIL * 100, linestyle="--", color="red", label=f"Seuil d'alerte ({SEUIL:.0%})")

    ax.set_ylabel("%")
    ax.set_ylim(0, 105)
    ax.set_title("Suivi de la qualité dans le temps (configuration retenue)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()

    fig.tight_layout()
    fig.savefig(chemin, dpi=130)
    plt.close(fig)

def generer_markdown(plan: list[dict], suivi: list[dict], chemin: Path) -> None:
    """Assemble le rapport de suivi au format Markdown."""
    maintenant = datetime.now()

    lignes = [
        "# Rapport de suivi de la qualité — assistant RAG RH",
        "",
        f"*Généré le {maintenant:%d/%m/%Y à %H:%M}*",
        "",
        f"Seuil d'alerte : **{SEUIL:.0%}** du taux de réponses correctes.",
        "",
        "## 1. Comparaison des configurations",
        "",
        "Six configurations ont été évaluées sur le même jeu de 20 questions "
        "de référence, en faisant varier la taille de chunk et le nombre de "
        "passages retournés (`top_k`).",
        "",
        "![Comparaison des configurations](configurations.png)",
        "",
        "| Taille chunk | top_k | Taux correct | Rappel source | Erreurs |",
        "|---|---|---|---|---|",
    ]

    for r in plan:
        lignes.append(
            f"| {r['taille_chunk']} | {r['top_k']} | "
            f"{r['taux_llm']:.1%} | {r['rappel']:.1%} | "
            f"{int(r['erreurs'])} |"
        )

    meilleur = max(plan, key=lambda r: r["taux_llm"])
    lignes += [
        "",
        f"**Configuration retenue :** taille de chunk {meilleur['taille_chunk']}, "
        f"`top_k` = {meilleur['top_k']} ({meilleur['taux_llm']:.0%}).",
        "",
        "## 2. Suivi dans le temps",
        "",
        "Exécutions successives de la configuration retenue.",
        "",
        "![Suivi de la qualité](suivi.png)",
        "",
        "| Date | Taux correct | Rappel source | Erreurs |",
        "|---|---|---|---|",
    ]

    for r in suivi:
        lignes.append(
            f"| {r['date']:%d/%m/%Y %H:%M} | {r['taux_llm']:.1%} | "
            f"{r['rappel']:.1%} | {int(r['erreurs'])} |"
        )

    # Synthèse
    taux_suivi = [r["taux_llm"] for r in suivi]
    sous_seuil = [t for t in taux_suivi if t < SEUIL]

    lignes += [
        "",
        "## 3. Synthèse",
        "",
        f"- Exécutions de suivi : **{len(suivi)}**",
        f"- Taux moyen : **{sum(taux_suivi) / len(taux_suivi):.1%}**",
        f"- Taux minimal : **{min(taux_suivi):.1%}**",
        f"- Franchissements du seuil : **{len(sous_seuil)}**",
        "",
        "## 4. Limites",
        "",
        "- L'historique de suivi couvre une période très courte : le dispositif "
        "est opérationnel, mais la détection d'une dérive réelle nécessiterait "
        "plusieurs semaines d'exécutions quotidiennes.",
        "- Le jeu de référence compte 20 questions, soit une granularité de "
        "5 points par question. Un jeu plus large permettrait un seuil plus exigeant.",
        "- Des écarts de quelques points entre exécutions identiques ont été "
        "observés malgré une température fixée à 0 : une partie de la variation "
        "mesurée relève du bruit.",
        "",
    ]

    chemin.write_text("\n".join(lignes), encoding="utf-8")

if __name__ == "__main__":
    DOSSIER_RAPPORTS.mkdir(exist_ok=True)

    runs = charger_runs()
    plan, suivi = separer_phases(runs)

    graphique_configurations(plan, DOSSIER_RAPPORTS / "configurations.png")
    graphique_suivi(suivi, DOSSIER_RAPPORTS / "suivi.png")
    generer_markdown(plan, suivi, DOSSIER_RAPPORTS / "rapport_qualite.md")

    print(f"Rapport généré : {DOSSIER_RAPPORTS / 'rapport_qualite.md'}")
    print(f"  {len(plan)} configurations comparées")
    print(f"  {len(suivi)} exécutions de suivi")