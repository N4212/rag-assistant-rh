import json
from pathlib import Path
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import time
from src.generation import repondre

FICHIER_QUESTIONS = Path("data/evaluation/questions_reference.json")


def charger_questions(chemin: Path = FICHIER_QUESTIONS) -> list[dict]:
    """Charge le jeu de questions de référence."""
    with open(chemin, encoding="utf-8") as f:
        donnees = json.load(f)
    return donnees["questions"]


def juger_par_mots_cles(reponse: str, mots_cles: list[str]) -> bool:
    """Vrai si tous les mots-clés attendus figurent dans la réponse."""
    # Comparaison insensible à la casse
    reponse_min = reponse.lower()
    return all(mot.lower() in reponse_min for mot in mots_cles)


load_dotenv()

MODELE_JUGE = "gemini-3.5-flash-lite"

PROMPT_JUGE = """Tu évalues la réponse d'un assistant RH.

Compare la réponse produite à la réponse attendue.

Critères :
- Juge l'équivalence FACTUELLE, pas la similarité de formulation.
- La réponse est CORRECT si elle contient les faits de la réponse attendue,
  même reformulés, même exprimés en toutes lettres.
- Des précisions supplémentaires ne rendent PAS la réponse incorrecte,
  tant qu'elles ne contredisent pas la réponse attendue.
- La réponse est INCORRECT si un fait attendu est absent, ou si un chiffre,
  un délai ou une durée diffère de la réponse attendue.

Réponds par UN SEUL MOT : CORRECT ou INCORRECT.
N'ajoute aucune explication."""

_client_juge = None


def obtenir_client_juge() -> genai.Client:
    """Ouvre le client Gemini une seule fois."""
    global _client_juge
    if _client_juge is None:
        _client_juge = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client_juge


def juger_par_llm(question: str, reponse_attendue: str, reponse_produite: str) -> bool:
    """Demande à un LLM si la réponse produite est factuellement correcte."""
    client = obtenir_client_juge()

    message = (
        f"Question : {question}\n\n"
        f"Réponse attendue : {reponse_attendue}\n\n"
        f"Réponse produite : {reponse_produite}"
    )

    resultat = client.models.generate_content(
        model=MODELE_JUGE,
        contents=message,
        config=types.GenerateContentConfig(
            system_instruction=PROMPT_JUGE,
            temperature=0,
        ),
    )

    verdict = resultat.text.strip().upper()
    return verdict.startswith("CORRECT")

from google.genai import errors as genai_errors


def avec_reessai(fonction, *args, max_tentatives: int = 3, **kwargs):
    """Exécute une fonction en réessayant si le quota par minute est atteint."""
    for tentative in range(max_tentatives):
        try:
            return fonction(*args, **kwargs)
        except genai_errors.ClientError as e:
            # 429 = quota dépassé ; tout autre code est une vraie erreur
            if e.code != 429 or tentative == max_tentatives - 1:
                raise
            # Attente croissante : 20 s, puis 40 s
            attente = 20 * (tentative + 1)
            print(f"    quota atteint, attente de {attente} s...")
            time.sleep(attente)

def evaluer_configuration(
    nom_collection: str,
    top_k: int = 3,
    pause: float = 1.0,
    limite: int | None = None,
) -> dict:
    """Rejoue le jeu de questions et calcule les métriques."""
    questions = charger_questions()
    if limite is not None:
        questions = questions[:limite]
    resultats = []

    for q in questions:
        ligne = {
            "id": q["id"],
            "categorie": q["categorie"],
            "question": q["question"],
        }

        try:
            sortie = avec_reessai(repondre, q["question"], nom_collection, top_k)
            reponse = sortie["reponse"]
            sources = sortie["sources"]

            ligne["reponse"] = reponse
            ligne["sources"] = sources
            ligne["erreur_technique"] = False

            # Juge 1 : présence des mots-clés attendus
            ligne["correct_mots_cles"] = juger_par_mots_cles(reponse, q["mots_cles"])

            # Juge 2 : équivalence factuelle évaluée par un LLM
            ligne["correct_llm"] = avec_reessai(
                juger_par_llm, q["question"], q["reponse_attendue"], reponse
            )

            # La recherche a-t-elle remonté le bon document ?
            # (sans objet pour les questions sans réponse)
            if q["source_attendue"] is None:
                ligne["source_trouvee"] = None
            else:
                ligne["source_trouvee"] = q["source_attendue"] in sources

        except Exception as e:
            # Un échec technique ne doit pas interrompre l'évaluation
            ligne["reponse"] = None
            ligne["sources"] = []
            ligne["erreur_technique"] = True
            ligne["message_erreur"] = str(e)[:900]
            ligne["correct_mots_cles"] = False
            ligne["correct_llm"] = False
            ligne["source_trouvee"] = False

        resultats.append(ligne)
        print(f"  {ligne['id']} traitée")
        time.sleep(pause)

    return {
        "collection": nom_collection,
        "top_k": top_k,
        "resultats": resultats,
        "metriques": calculer_metriques(resultats),
    }


def calculer_metriques(resultats: list[dict]) -> dict:
    """Agrège les résultats en indicateurs synthétiques."""
    total = len(resultats)

    # Questions ayant une source attendue (les « sans réponse » sont exclues)
    avec_source = [r for r in resultats if r["source_trouvee"] is not None]

    return {
        "nb_questions": total,
        "taux_mots_cles": sum(r["correct_mots_cles"] for r in resultats) / total,
        "taux_llm": sum(r["correct_llm"] for r in resultats) / total,
        "taux_rappel_source": (
            sum(r["source_trouvee"] for r in avec_source) / len(avec_source)
            if avec_source else 0.0
        ),
        "nb_erreurs_techniques": sum(r["erreur_technique"] for r in resultats),
    }

if __name__ == "__main__":
    COLLECTION = "rh_taille500_chev100"
    TOP_K = 3

    print(f"Évaluation de « {COLLECTION} » (top_k={TOP_K})\n")

    rapport = evaluer_configuration(COLLECTION, TOP_K, pause=8.0)
    m = rapport["metriques"]

    print("\n" + "=" * 50)
    print(f"Questions évaluées      : {m['nb_questions']}")
    print(f"Taux (mots-clés)        : {m['taux_mots_cles']:.1%}")
    print(f"Taux (juge LLM)         : {m['taux_llm']:.1%}")
    print(f"Rappel de la source     : {m['taux_rappel_source']:.1%}")
    print(f"Erreurs techniques      : {m['nb_erreurs_techniques']}")

    print("\nDétail des erreurs techniques :")
    for r in rapport["resultats"]:
        if r["erreur_technique"]:
            print(f"  {r['id']} : {r['message_erreur']}")
            break   # une seule suffit pour le diagnostic

    print("\nQuestions en échec :")
    for r in rapport["resultats"]:
        if not r["correct_llm"] or not r["correct_mots_cles"]:
            print(f"\n  {r['id']} [{r['categorie']}] {r['question']}")
            print(f"    mots-clés : {r['correct_mots_cles']} | LLM : {r['correct_llm']}")
            print(f"    source trouvée : {r['source_trouvee']}")
            print(f"    réponse : {r['reponse'][:200]}")