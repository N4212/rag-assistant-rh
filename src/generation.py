import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.recherche import rechercher

# Charge les variables du fichier .env (dont GEMINI_API_KEY)
load_dotenv()

MODELE_LLM = "gemini-3.5-flash-lite"

PROMPT_SYSTEME = """Tu es un assistant RH interne de l'entreprise Novaterra Solutions.

Règles impératives :
- Réponds UNIQUEMENT à partir des extraits de documents fournis ci-dessous.
- Si l'information ne figure pas dans les extraits, réponds exactement :
  "Je ne dispose pas de cette information dans la documentation RH."
- N'invente jamais de chiffre, de délai ou de procédure.
- Cite le document source entre parenthèses à la fin de ta réponse.
- Sois concis : deux à quatre phrases maximum."""


def construire_contexte(chunks: list[dict]) -> str:
    """Assemble les chunks récupérés en un bloc de texte unique."""
    parties = []
    for i, chunk in enumerate(chunks):
        parties.append(f"--- Extrait {i + 1} ---\n{chunk['texte']}")
    return "\n\n".join(parties)


def generer_reponse(question: str, chunks: list[dict]) -> str:
    """Envoie la question et le contexte au LLM, renvoie la réponse."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    contexte = construire_contexte(chunks)
    message = f"Extraits de la documentation :\n\n{contexte}\n\nQuestion : {question}"

    reponse = client.models.generate_content(
        model=MODELE_LLM,
        contents=message,
        config=types.GenerateContentConfig(
            system_instruction=PROMPT_SYSTEME,
            temperature=0,  # déterministe : indispensable pour l'évaluation
        ),
    )

    return reponse.text


def repondre(question: str, nom_collection: str, top_k: int = 3) -> dict:
    """Pipeline RAG complet : recherche puis génération."""
    chunks = rechercher(question, nom_collection, top_k)
    reponse = generer_reponse(question, chunks)

    return {
        "question": question,
        "reponse": reponse,
        "sources": [c["source"] for c in chunks],
    }


if __name__ == "__main__":
    COLLECTION = "rh_taille500_chev100"

    questions = [
        # 1. Fait simple et isolé
        "Quel est le barème de remboursement kilométrique ?",

        # 2. Information ABSENTE du corpus : le modèle doit refuser de répondre
        "Comment demander un congé sabbatique ?",

        # 3. Piège : deux dispositifs proches à ne pas confondre
        "Tous les combien a lieu l'entretien professionnel ?",

        # 4. Croisement de deux documents
        "Un salarié arrivé il y a deux semaines peut-il télétravailler ?",
    ]

    for question in questions:
        resultat = repondre(question, COLLECTION, top_k=3)
        print("=" * 70)
        print(f"Q : {resultat['question']}\n")
        print(f"R : {resultat['reponse']}\n")
        print(f"Sources : {resultat['sources']}\n")