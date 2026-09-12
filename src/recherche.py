import chromadb
from sentence_transformers import SentenceTransformer

DOSSIER_BASE = "data/chroma"
MODELE_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"

# Variables de module : elles conservent leur valeur entre les appels
_modele = None
_client = None


def obtenir_modele(nom_modele: str = MODELE_EMBEDDING) -> SentenceTransformer:
    """Charge le modèle une seule fois et le réutilise ensuite."""
    global _modele
    if _modele is None:
        _modele = SentenceTransformer(nom_modele)
    return _modele


def obtenir_client() -> chromadb.ClientAPI:
    """Ouvre la connexion à Chroma une seule fois."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=DOSSIER_BASE)
    return _client


def rechercher(question: str, nom_collection: str, top_k: int = 3) -> list[dict]:
    """Renvoie les top_k chunks les plus proches de la question."""
    client = obtenir_client()
    collection = client.get_collection(name=nom_collection)

    modele = obtenir_modele()
    vecteur_question = modele.encode([question]).tolist()

    resultats = collection.query(
        query_embeddings=vecteur_question,
        n_results=top_k,
    )

    chunks = []
    for i in range(len(resultats["ids"][0])):
        chunks.append({
            "id": resultats["ids"][0][i],
            "texte": resultats["documents"][0][i],
            "source": resultats["metadatas"][0][i]["source"],
            "distance": resultats["distances"][0][i],
        })

    return chunks

if __name__ == "__main__":
    COLLECTION = "rh_taille500_chev100"

    question = "Combien de jours de congé pour un mariage ?"

    resultats = rechercher(question, COLLECTION, top_k=3)

    print(f"Question : {question}\n")
    for i, chunk in enumerate(resultats):
        print(f"--- Résultat {i + 1} (distance : {chunk['distance']:.3f}) ---")
        print(f"Source : {chunk['source']}")
        print(chunk["texte"][:250])
        print()