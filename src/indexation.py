from pathlib import Path
from sentence_transformers import SentenceTransformer
import chromadb

# Chemin vers le dossier contenant les documents du corpus
DOSSIER_CORPUS = Path("data/corpus")


def charger_documents(dossier: Path) -> list[dict]:
    """Lit tous les fichiers .md d'un dossier et renvoie leur contenu."""
    documents = []

    # glob("*.md") liste tous les fichiers se terminant par .md
    # sorted() garantit un ordre stable d'une exécution à l'autre
    for chemin in sorted(dossier.glob("*.md")):
        texte = chemin.read_text(encoding="utf-8")

        # On garde le nom du fichier : il servira à citer la source
        documents.append({
            "source": chemin.name,
            "contenu": texte,
        })

    return documents

# Séparateurs classés du plus « naturel » au plus brutal.
# On essaie de couper au paragraphe d'abord, au caractère en dernier recours.
SEPARATEURS = ["\n\n", "\n", ". ", " ", ""]


def decouper_texte(texte: str, taille: int, chevauchement: int) -> list[str]:
    """Découpe un texte en chunks en respectant au mieux sa structure."""
    chunks = []
    debut = 0

    while debut < len(texte):
        fin = debut + taille

        # Si on atteint la fin du texte, on prend tout le reste
        if fin >= len(texte):
            chunks.append(texte[debut:].strip())
            break

        # On cherche le meilleur point de coupure avant la limite.
        # rfind() cherche la DERNIÈRE occurrence du séparateur dans la zone.
        coupure = -1
        for sep in SEPARATEURS:
            if sep == "":
                # Dernier recours : on coupe net à la limite
                coupure = fin
                break
            position = texte.rfind(sep, debut, fin)
            # On refuse une coupure trop proche du début :
            # elle produirait un chunk minuscule
            if position > debut + taille // 2:
                coupure = position + len(sep)
                break

        chunks.append(texte[debut:coupure].strip())

        # Le chunk suivant recule du chevauchement pour créer le recouvrement
        debut = coupure - chevauchement

    # On élimine les chunks vides éventuels
    return [c for c in chunks if c]

def construire_chunks(documents: list[dict], taille: int, chevauchement: int) -> list[dict]:
    """Découpe tous les documents et renvoie une liste de chunks enrichis."""
    chunks = []

    for doc in documents:
        morceaux = decouper_texte(doc["contenu"], taille, chevauchement)

        for i, morceau in enumerate(morceaux):
            # On préfixe le nom du document : le chunk reste interprétable
            # même s'il ne contient qu'un fragment de tableau
            texte_enrichi = f"[Document : {doc['source']}]\n{morceau}"

            chunks.append({
                "id": f"{doc['source']}::{i}",   # identifiant unique
                "texte": texte_enrichi,
                "source": doc["source"],
                "position": i,
            })

    return chunks

MODELE_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"


def calculer_embeddings(chunks: list[dict], nom_modele: str = MODELE_EMBEDDING):
    """Transforme le texte de chaque chunk en vecteur."""
    # Le chargement du modèle est lent : on ne le fait qu'une fois
    modele = SentenceTransformer(nom_modele, device="cpu")
    
    textes = [c["texte"] for c in chunks]

    # encode() traite toute la liste d'un coup : bien plus rapide
    # qu'un appel par chunk
    vecteurs = modele.encode(textes, show_progress_bar=True)

    return vecteurs

DOSSIER_BASE = "data/chroma"


def indexer_dans_chroma(chunks: list[dict], vecteurs, nom_collection: str):
    """Stocke les chunks et leurs vecteurs dans une collection Chroma."""
    # PersistentClient écrit sur disque : l'index survit à l'arrêt du script
    client = chromadb.PersistentClient(path=DOSSIER_BASE)

    # On repart de zéro si la collection existe déjà,
    # sinon on accumulerait des doublons à chaque exécution
    if nom_collection in [c.name for c in client.list_collections()]:
        client.delete_collection(nom_collection)

    collection = client.create_collection(name=nom_collection)

    # Chroma attend des listes parallèles, pas une liste de dictionnaires
    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["texte"] for c in chunks],
        embeddings=vecteurs.tolist(),
        metadatas=[
            {"source": c["source"], "position": c["position"]}
            for c in chunks
        ],
    )

    return collection

def construire_index(taille: int, chevauchement: int) -> str:
    """Indexe le corpus avec les paramètres donnés. Renvoie le nom de la collection."""
    nom_collection = f"rh_taille{taille}_chev{chevauchement}"

    docs = charger_documents(DOSSIER_CORPUS)
    chunks = construire_chunks(docs, taille, chevauchement)
    vecteurs = calculer_embeddings(chunks)
    indexer_dans_chroma(chunks, vecteurs, nom_collection)

    return nom_collection

if __name__ == "__main__":
    TAILLE = 500
    CHEVAUCHEMENT = 100
    COLLECTION = f"rh_taille{TAILLE}_chev{CHEVAUCHEMENT}"

    docs = charger_documents(DOSSIER_CORPUS)
    chunks = construire_chunks(docs, TAILLE, CHEVAUCHEMENT)
    print(f"{len(chunks)} chunks générés")

    vecteurs = calculer_embeddings(chunks)
    print(f"Embeddings calculés : {vecteurs.shape}")

    collection = indexer_dans_chroma(chunks, vecteurs, COLLECTION)
    print(f"\nCollection « {COLLECTION} » créée")
    print(f"Nombre d'entrées : {collection.count()}")