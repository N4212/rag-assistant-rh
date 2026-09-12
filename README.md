# Assistant RAG RH avec évaluation continue de la qualité

Assistant conversationnel interrogeant une base documentaire RH, doté d'un
dispositif de mesure et de surveillance automatisée de la qualité de ses
réponses.

Projet réalisé dans le cadre du Master 1 I2AD (INSI, Antananarivo).

## Contexte

Un assistant RAG déployé en entreprise se dégrade sans que personne ne s'en
aperçoive : le corpus documentaire évolue, le fournisseur de modèle retire ou
remplace une version, les questions posées sortent progressivement du domaine
couvert. Le problème n'est donc pas seulement de construire un assistant qui
fonctionne, mais de savoir qu'il fonctionne encore.

Ce projet répond à ce besoin par une chaîne complète : un pipeline RAG, une
évaluation automatisée rejouée périodiquement, un historique des mesures et
une alerte déclenchée lorsque la qualité passe sous un seuil défini.

Le corpus utilisé est un ensemble fictif de dix procédures RH (congés,
télétravail, notes de frais, sécurité de l'information, etc.) rédigées pour
contenir des faits précis et vérifiables — condition nécessaire à une
évaluation automatique.

## Architecture

| Composant | Rôle | Technologie |
|---|---|---|
| Indexation | Découpage et vectorisation du corpus | sentence-transformers, Chroma |
| Recherche | Récupération des passages pertinents | Chroma |
| Génération | Rédaction de la réponse | API Gemini |
| Évaluation | Mesure du taux de réponses correctes | Double juge (mots-clés + LLM) |
| Suivi | Historique des configurations et métriques | MLflow |
| Orchestration | Exécution périodique | Prefect |
| Alerte | Notification en cas de dégradation | n8n (Docker) |

Le jeu de référence compte 20 questions : 12 factuelles, 3 de croisement entre
documents, 3 pièges portant sur des informations confusables, et 2 sans réponse
dans le corpus — ces dernières vérifiant que l'assistant refuse d'inventer.

## Prérequis

- Python 3.14
- Docker (pour n8n)
- Une clé API Google Gemini ([Google AI Studio](https://aistudio.google.com/apikey))

## Installation

```bash
git clone https://github.com/N4212/rad-assistant-rh.git
cd rag-assistant-rh

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Créer un fichier `.env` à la racine :

```
GEMINI_API_KEY=votre_cle_ici
```

Lancer n8n :

```bash
docker run -d --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
```

## Utilisation

### Indexer le corpus

```bash
python -m src.indexation
```

Produit une collection Chroma dans `data/chroma/`.

### Interroger l'assistant

```bash
python -m src.generation
```

### Évaluer une configuration

```bash
python -m src.evaluation
```

Rejoue les 20 questions de référence et affiche les métriques.

### Comparer plusieurs configurations

```bash
python -m src.experimentation
```

Enchaîne indexation et évaluation pour chaque configuration du plan
d'expérience, et enregistre chaque run dans MLflow.

Interface MLflow :

```bash
python -m mlflow ui --backend-store-uri sqlite:///mlflow.db
```

### Surveillance automatisée

Exécution immédiate :

```bash
python -m src.flux_surveillance
```

Déploiement planifié (quotidien à 2 h) :

```bash
python -m prefect server start                 # dans un terminal
python -m src.flux_surveillance --planifier    # dans un autre
```

Interface Prefect : `http://127.0.0.1:4200`

### Générer le rapport de suivi

```bash
python -m src.rapport_qualite
```

Produit `rapports/rapport_qualite.md` et les graphiques associés.

## Structure du projet

```
src/
  indexation.py        Chargement, découpage, vectorisation, stockage
  recherche.py         Recherche sémantique dans Chroma
  generation.py        Pipeline RAG complet (recherche + génération)
  evaluation.py        Jeu de référence et double système de jugement
  experimentation.py   Comparaison de configurations via MLflow
  flux_surveillance.py Flux Prefect : évaluation, alerte, rapport
  rapport_qualite.py   Génération du rapport de suivi

data/
  corpus/              Dix documents RH fictifs
  evaluation/          Jeu de 20 questions de référence

rapports/              Rapport de suivi généré et graphiques
```

## Résultats

Six configurations ont été comparées en faisant varier la taille de chunk et le
nombre de passages retournés. La configuration retenue — chunks de 500
caractères, chevauchement de 100, `top_k = 5` — atteint 100 % de réponses
correctes sur le jeu de référence.

Le détail des mesures, l'analyse des cas d'échec et les limites de la méthode
figurent dans le rapport écrit du projet et dans
[`rapports/rapport_qualite.md`](rapports/rapport_qualite.md), régénéré à chaque
exécution du flux de surveillance.

## Composants externes

n8n 2.38.6, exécuté en conteneur Docker. Le workflow d'alerte comporte trois
nœuds : réception webhook, condition sur le franchissement du seuil, envoi
d'une requête HTTP vers le service de notification.
