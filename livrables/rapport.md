## 1. Contexte métier et problématique

Le département des ressources humaines d'une entreprise cherche à mettre à
disposition de ses collaborateurs un assistant capable de répondre à leurs
questions à partir des procédures internes existantes. L'objectif est que le
système retrouve, dans l'ensemble de la documentation qui lui est fournie, la
réponse exacte à la question posée. Le bénéfice est double : le service RH
cesse de traiter manuellement des demandes répétitives, et le collaborateur
obtient une réponse immédiate, à toute heure, sans avoir à solliciter un
interlocuteur pour une question qu'il juge parfois trop mineure pour être
posée.

L'approche retenue est le RAG (Retrieval-Augmented Generation). Comparée à une
recherche par mots-clés, elle permet de retrouver les passages dont le sens
correspond à la question, même lorsque la formulation diffère de celle du
document : « comment poser des congés » et « procédure de demande de vacances »
n'ont presque aucun terme en commun, mais expriment la même intention. Comparée
à l'usage d'un grand modèle de langage seul, sans corpus, elle évite que le
système invente des procédures plausibles mais étrangères à l'entreprise — ce
qui reviendrait à diffuser de fausses informations auprès des salariés.

Une fois l'outil livré et calibré, rien ne garantit qu'il conservera le niveau
de qualité mesuré le premier jour. Les procédures RH évoluent : une convention
est révisée, un barème change, une note interne est reformulée. Le fournisseur
du modèle de langage peut lui aussi modifier son offre, retirer une version ou
durcir ses quotas. Ces deux risques n'ont toutefois pas la même nature. Un
changement de modèle provoque une panne visible, que l'on détecte
immédiatement. Une procédure modifiée, elle, ne casse rien : l'assistant
continue de répondre avec la même assurance et cite une source qui existe
réellement, mais dont le contenu est désormais périmé. Personne ne s'en aperçoit
tant qu'un collaborateur n'a pas agi sur une réponse obsolète.

C'est précisément ce risque silencieux qui motive ce projet. Vérifier
manuellement la qualité des réponses chaque jour n'est pas envisageable :
il faut un dispositif qui mesure cette qualité de façon automatique, en
conserve l'historique, et signale de lui-même toute dégradation.

## 2. Architecture du système

Le système se décompose en trois ensembles qui n'ont ni la même périodicité ni
la même finalité : une phase d'indexation exécutée une seule fois, une phase
d'interrogation déclenchée à chaque question, et une phase de mesure rejouée
périodiquement.

![Architecture du système](images/architecture.png)

### 2.1 Indexation

Les dix documents du corpus RH sont d'abord découpés en fragments de 500
caractères, avec un chevauchement de 100 caractères entre fragments successifs.
Ce recouvrement évite qu'une information située à la frontière de deux
fragments ne se retrouve tronquée dans les deux.

Chaque fragment est ensuite converti en vecteur de 384 dimensions par le modèle
`paraphrase-multilingual-MiniLM-L12-v2`, exécuté localement. Ces vecteurs, les
textes correspondants et leurs métadonnées — document d'origine, position dans
le document — sont stockés dans une base vectorielle Chroma persistée sur
disque.

Chaque fragment est préfixé du nom de son document source avant vectorisation.
Un fragment isolé peut en effet ne contenir qu'une portion de tableau, sans son
titre de section ; le préfixe lui restitue un minimum de contexte.

### 2.2 Interrogation

La question posée est vectorisée par le même modèle que celui utilisé à
l'indexation — condition nécessaire, deux modèles distincts produisant des
espaces vectoriels incomparables. Chroma retourne les cinq fragments dont les
vecteurs sont les plus proches.

Ces fragments sont assemblés en un contexte transmis à l'API Gemini, accompagné
de la question et d'une consigne système. Cette consigne impose deux
comportements : répondre exclusivement à partir des extraits fournis, et
déclarer explicitement ne pas disposer de l'information lorsqu'elle ne s'y
trouve pas. La réponse renvoyée mentionne le document d'origine, ce qui permet
au collaborateur de remonter à la source.

### 2.3 Mesure et surveillance

Un jeu de vingt questions de référence, dont les réponses attendues sont
connues, constitue l'étalon de qualité. Le rejouer produit trois indicateurs :
le taux de réponses correctes selon deux systèmes de jugement indépendants, et
le taux de rappel de la source, qui mesure la qualité de la recherche
indépendamment de celle de la génération.

Prefect déclenche cette évaluation chaque nuit et en conserve l'historique
d'exécution — statut, durée, journaux. MLflow enregistre pour sa part les
paramètres de la configuration testée et les métriques obtenues, ce qui rend
les exécutions comparables entre elles dans le temps.

Lorsque le taux de réponses correctes passe sous le seuil de 90 %, le flux
émet une requête HTTP vers un webhook n8n, qui se charge de la notification.
Chaque exécution régénère enfin le rapport de suivi, document Markdown
accompagné de deux graphiques, consultable sans ouvrir MLflow.

### 2.4 Séparation des responsabilités

Deux outils d'orchestration coexistent dans ce système, avec des rôles
distincts. Prefect orchestre le code Python interne : il exécute, réessaie,
journalise. n8n orchestre la réaction vers l'extérieur : il reçoit un signal et
décide quoi en faire.

Ce découplage a une conséquence pratique. Modifier le destinataire d'une
alerte, ajouter un canal Slack ou créer un ticket ne demande aucune
intervention dans le code Python : il suffit de reconfigurer le dernier nœud du
workflow n8n, à la souris. La personne qui maintient les règles d'alerte n'a
pas besoin d'être celle qui maintient le pipeline.

### 3.x Le modèle de langage

Le choix de Gemini répond d'abord à une contrainte budgétaire. L'API Claude
fonctionne au crédit prépayé et n'entrait pas dans le cadre de ce projet
étudiant ; l'exécution d'un modèle en local, elle, supposait une machine
suffisamment dotée, ce qui n'était pas le cas de l'environnement de
développement utilisé. Le niveau gratuit de Gemini offrait le meilleur
compromis entre qualité de réponse et coût nul.

Ce choix s'est révélé plus instable que prévu. Le modèle initialement retenu,
`gemini-2.0-flash`, avait été retiré et redirigeait vers `gemini-3.6-flash`.
Ce dernier fonctionnait, mais avec un quota gratuit de vingt requêtes par
jour — alors qu'une seule évaluation complète en consomme quarante. Un troisième
modèle, `gemini-2.5-flash-lite`, n'était plus ouvert aux nouveaux comptes. Le
système tourne finalement sur `gemini-3.5-flash-lite`, dont la limite est de
quinze requêtes par minute.

Cette succession n'est pas anecdotique : elle a directement façonné le code.
La temporisation de huit secondes entre deux questions et le mécanisme de
réessai avec attente croissante existent uniquement pour absorber ces quotas.
Elle illustre surtout un risque structurel du recours à une API externe : le
fournisseur peut retirer un modèle, en restreindre l'accès ou en modifier les
limites sans préavis, et l'application doit alors s'adapter.

En contexte professionnel, un modèle hébergé en interne serait préférable pour
un assistant RH. Trois arguments le justifient : les documents traités
contiennent des données internes qui ne sortiraient pas du réseau de
l'entreprise, aucun quota ne viendrait contraindre le volume de requêtes, et la
version du modèle resterait sous contrôle, ce qui garantit la reproductibilité
des mesures dans le temps. Cette option a néanmoins un coût — un serveur doté
d'un accélérateur graphique, son administration — et les modèles auto-hébergés
accessibles restent généralement en deçà des modèles propriétaires à taille
comparable. L'arbitrage dépend donc du volume d'usage attendu et de la
sensibilité réelle des documents indexés.

### 3.x Le modèle d'embedding

La recherche sémantique repose sur un modèle qui convertit un texte en vecteur,
distinct du modèle de langage chargé de rédiger la réponse. Son rôle n'est pas
de comprendre la question mais de la situer dans un espace où la proximité
géométrique traduit la proximité de sens.

Le critère déterminant ici est la langue. Les modèles d'embedding les plus
répandus, comme `all-MiniLM-L6-v2`, sont entraînés exclusivement sur de
l'anglais : appliqués à un corpus français, ils dégradent fortement la qualité
de la recherche. Le choix s'est donc porté sur
`paraphrase-multilingual-MiniLM-L12-v2`, entraîné sur plusieurs langues dont le
français, qui produit des vecteurs de 384 dimensions.

Ce modèle s'exécute localement, sans appel réseau. Deux conséquences en
découlent. D'une part, l'indexation et la recherche ne consomment aucun quota
d'API et ne sont pas exposées aux retraits de version évoqués plus haut — le
système est donc hybride, sa partie recherche étant autonome et seule la
génération dépendant d'un fournisseur externe. D'autre part, les documents
indexés ne quittent jamais la machine au moment de la vectorisation, ce qui
limite la surface d'exposition des données RH.

Le coût de ce choix est local : le modèle pèse environ 470 Mo et doit être
chargé en mémoire. Une première implémentation le rechargeait à chaque
question, ce qui saturait la mémoire de la machine de développement. Il est
désormais chargé une seule fois puis conservé entre les appels.

### 3.x La base vectorielle

Chroma a été retenu pour stocker les fragments, leurs vecteurs et leurs
métadonnées. Le critère principal est l'adéquation à l'échelle du projet :
soixante-neuf fragments pour la configuration retenue.

À ce volume, la performance de recherche n'est pas un enjeu. Une comparaison
exhaustive de la question avec chaque vecteur s'exécuterait en quelques
millisecondes, et les structures d'indexation approximatives que proposent les
bases vectorielles n'apportent un gain qu'à partir de plusieurs centaines de
milliers d'entrées. Des solutions comme Qdrant, Weaviate ou Milvus, conçues
pour de tels volumes, auraient imposé une infrastructure serveur sans bénéfice
mesurable ici.

Chroma fonctionne en bibliothèque intégrée, sans processus séparé, et persiste
ses données dans un fichier local. Cette simplicité de déploiement pèse dans un
projet où quatre composants distincts — pipeline, MLflow, Prefect, n8n —
cohabitent déjà.

Deux fonctionnalités ont été déterminantes au-delà du simple stockage. Chroma
conserve le texte original de chaque fragment aux côtés de son vecteur : le
vecteur sert à retrouver, mais c'est le texte qui est transmis au modèle de
langage. Il stocke également des métadonnées librement définies — ici le
document d'origine et la position du fragment — qui permettent de citer les
sources dans la réponse et rendent possible la mesure du rappel de la source
présentée plus loin.

### 3.x Le corpus

Trois corpus réels avaient été envisagés : une documentation technique open
source, le règlement des études de l'établissement, ou des rapports économiques
publics. Le choix s'est porté sur un corpus fictif de dix procédures RH.

Ce choix tient à la nature de l'exercice. Le cœur du projet n'est pas
l'ingestion de documents mais la mesure de la qualité des réponses dans la
durée. Un corpus réel aurait imposé un travail de conversion et de nettoyage —
extraction de PDF, correction de mises en forme irrégulières — sans rien
apporter à la démonstration du dispositif de surveillance.

Le contrôle total du contenu a surtout rendu l'évaluation possible. Chaque
document contient des faits précis et vérifiables : un barème kilométrique de
0,45 euro, un délai de carence de trois jours, une longueur minimale de
quatorze caractères pour un mot de passe. Une réponse portant sur ces
informations est correcte ou fausse, sans zone intermédiaire. Un corpus aux
formulations vagues n'aurait autorisé aucune métrique binaire.

Le même contrôle a permis d'y placer des difficultés délibérées. Le document
sur l'entretien annuel décrit deux dispositifs voisins que l'on confond
facilement, l'entretien d'évaluation et l'entretien professionnel. La question
du télétravail d'un nouvel arrivant exige de croiser deux documents distincts.
Le congé sabbatique et le compte épargne-temps, enfin, ne figurent nulle part :
ils servent à vérifier que l'assistant reconnaît son ignorance au lieu
d'inventer une procédure plausible.

Cette maîtrise a une contrepartie qu'il faut assumer. Un corpus réel serait plus
bruité : formulations ambiguës, contradictions entre documents, redondances,
structures hétérogènes. Le corpus utilisé ici est donc plus propre que la
documentation d'une entreprise réelle, et les taux mesurés sont vraisemblablement
supérieurs à ceux qu'obtiendrait le même système sur des procédures
authentiques.

### 3.x La taille de découpage et le nombre de passages

Ces deux paramètres n'ont pas été choisis a priori : ils résultent d'un plan
d'expérience dont le détail figure en section 5. Ce point mérite d'être posé
comme un choix méthodologique à part entière.

Le découpage du corpus en fragments répond à deux besoins distincts. Transmettre
un document entier au modèle de langage à chaque question serait coûteux et
lent ; c'est le premier. Le second tient au fonctionnement des embeddings : un
vecteur représente le sens global du texte qu'il encode, si bien qu'un fragment
mélangeant congés, télétravail et notes de frais produit un vecteur imprécis,
proche d'aucune question particulière.

Deux forces opposées s'exercent donc. Des fragments courts isolent bien chaque
information mais découpent les unités de sens : un tableau de barème coupé en
deux perd son en-tête, et le fragment orphelin devient difficilement
interprétable. Des fragments longs préservent la structure mais diluent le
vecteur. Aucune valeur ne s'impose par le raisonnement seul, ce qui justifie la
démarche expérimentale.

Le second paramètre, `top_k`, fixe le nombre de fragments transmis au modèle de
langage. Une valeur faible réduit le contexte envoyé, donc le coût et le temps
de réponse, mais augmente le risque que le passage pertinent soit absent. Une
valeur élevée augmente les chances de le retenir, au prix d'un contexte plus
chargé.

Un chevauchement de l'ordre de 20 % de la taille du fragment a été retenu dans toutes les
configurations. Sans recouvrement, une information située à la frontière de deux
fragments se retrouverait tronquée dans les deux ; avec recouvrement, elle
apparaît entière dans au moins l'un d'eux.

Six configurations ont été évaluées sur le même jeu de questions, en ne faisant
varier qu'un facteur à la fois. La configuration retenue — fragments de 500
caractères, chevauchement de 100, `top_k` fixé à 5 — est celle qui a obtenu les
meilleures mesures. Les résultats, dont un qui contredit l'intuition initiale,
sont analysés en section 5.

### 3.x Le système de jugement

Mesurer un taux de réponses correctes suppose de décider automatiquement, pour
chaque réponse produite, si elle est juste. La comparaison littérale au texte
attendu a été écartée d'emblée : trop rigide, elle rejetterait une réponse
correcte simplement reformulée.

Deux méthodes de jugement ont été retenues et appliquées en parallèle à chaque
réponse.

La première vérifie la présence de mots-clés obligatoires, définis question par
question dans le jeu de référence. Pour le barème kilométrique, le mot-clé est
`0,45`. Ce juge est gratuit, instantané et parfaitement déterministe, mais
grossier : il ne mesure qu'une présence de chaîne de caractères.

La seconde soumet à un modèle de langage la question, la réponse attendue et la
réponse produite, en lui demandant un verdict binaire. Ce juge apprécie
l'équivalence de sens et accepte une reformulation, une réponse plus détaillée
ou un chiffre écrit en toutes lettres. Il coûte en revanche un appel d'API par
question et peut lui-même se tromper.

Leur conservation conjointe se justifie par trois raisons.

Leur désaccord signale les cas ambigus. À la question portant sur le congé pour
mariage, l'assistant a répondu « quatre jours ouvrés » alors que le mot-clé
attendu était `4` : le premier juge a conclu à un échec, le second a validé. Le
désaccord ne révélait pas une défaillance du système mais une défaillance de la
métrique.

Le juge par mots-clés sert par ailleurs de recours lorsque l'API est
indisponible, situation rencontrée à plusieurs reprises pendant le
développement. La mesure reste alors possible, fût-elle plus approximative.

Enfin, le juge par modèle de langage est lui-même un composant à valider. Sa
première version appliquait deux règles contradictoires et rejetait à tort les
réponses plus complètes que la référence. Le défaut a été identifié en testant
le juge sur des cas construits à la main, avant de s'en servir pour mesurer quoi
que ce soit.

## 4. Méthode d'évaluation

### 4.1 Le jeu de référence

L'évaluation repose sur vingt questions dont les réponses sont connues à
l'avance. Chaque entrée du jeu comporte quatre champs : la question, la réponse
attendue formulée en langage naturel, la liste des mots-clés obligatoires, et le
document censé contenir l'information.

Ce dernier champ mérite d'être souligné. Il permet de distinguer deux natures
d'échec que le seul taux de réponses correctes confondrait. Si le document
attendu n'a pas été remonté par la recherche, la défaillance est en amont. S'il
l'a été et que la réponse reste fausse, elle est dans la génération. Sans cette
distinction, on saurait que le système se trompe sans savoir quel paramètre
corriger.

La composition du jeu n'est pas homogène :

| Catégorie | Nombre | Objet |
|---|---|---|
| Factuelle | 12 | Un fait précis dans un seul document |
| Croisement | 3 | Information répartie sur deux documents |
| Piège | 3 | Deux valeurs voisines aisément confondues |
| Sans réponse | 2 | Information absente du corpus |

Cette répartition est délibérée. Un jeu composé uniquement de questions faciles
afficherait un taux proche de 100 % en permanence et ne détecterait aucune
dégradation : une métrique qui ne varie jamais n'informe pas. Les sept questions
difficiles créent la marge nécessaire pour que le taux soit sensible à un
changement.

Les deux questions sans réponse méritent une mention particulière. Le congé
sabbatique et le compte épargne-temps ne figurent nulle part dans le corpus. La
réponse correcte consiste donc à déclarer ne pas disposer de l'information. Ces
questions vérifient un comportement qui, pour un assistant d'entreprise, importe
autant que l'exactitude : reconnaître son ignorance plutôt qu'inventer une
procédure vraisemblable.

### 4.2 Les métriques

Trois indicateurs sont calculés à chaque exécution.

Le **taux de réponses correctes selon le juge par mots-clés** et le **taux selon
le juge par modèle de langage** mesurent la qualité globale du système. Leur
écart signale les cas où la métrique elle-même est en défaut.

Le **taux de rappel de la source** mesure la proportion de questions pour
lesquelles le document attendu figure parmi les passages remontés. Il évalue la
recherche seule, indépendamment de la rédaction. Les deux questions sans réponse
en sont exclues, faute de document attendu.

Un quatrième compteur, le **nombre d'erreurs techniques**, recense les questions
dont le traitement a échoué pour un motif extérieur à la qualité — API
indisponible, quota atteint. Ce compteur ne mesure pas le système mais la
validité de la mesure : une évaluation comportant des erreurs techniques produit
des taux ininterprétables, puisqu'une question non traitée est comptée comme
incorrecte.

### 4.3 Robustesse de l'exécution

Rejouer vingt questions représente quarante appels d'API, dont chacun peut
échouer. Trois mécanismes protègent l'exécution.

Chaque question est traitée dans un bloc de capture d'exception : un échec
n'interrompt pas la série, la question est marquée en erreur technique et le
traitement se poursuit. Sans ce dispositif, une panne survenue à la douzième
question ferait perdre les onze mesures déjà acquises.

Un mécanisme de réessai avec attente croissante absorbe les dépassements de
quota, qui se traduisent par un code d'erreur spécifique. Une temporisation de
huit secondes entre deux questions maintient par ailleurs le débit sous la
limite de quinze requêtes par minute imposée par le niveau gratuit — ce qui
porte la durée d'une évaluation complète à environ quatre minutes.

La température du modèle est enfin fixée à zéro, tant pour la génération que
pour le juge, afin de rendre les mesures aussi reproductibles que possible. La
section 5 montre que cette précaution ne suffit pas à les rendre strictement
déterministes.

## 5. Tests, résultats et cas d'échec

### 5.1 Protocole

Six configurations ont été évaluées sur le même jeu de vingt questions, en ne
faisant varier qu'un facteur à la fois afin que chaque écart observé soit
attribuable à un paramètre identifié. Chaque exécution a été enregistrée dans
MLflow avec ses paramètres et ses métriques.

| Taille de chunk | Chevauchement | top_k | Taux correct | Rappel source |
|---|---|---|---|---|
| 500 | 100 | 3 | 90 % | 94,4 % |
| **500** | **100** | **5** | **100 %** | **100 %** |
| 300 | 60 | 3 | 80 % | 100 % |
| 800 | 160 | 3 | 70 % | 94,4 % |
| 800 | 160 | 5 | 90 % | 94,4 % |
| 1200 | 200 | 3 | 70 % | 88,9 % |

### 5.2 Effet du nombre de passages

À taille de chunk constante, augmenter `top_k` de 3 à 5 améliore le résultat
dans les deux cas testés : de 90 à 100 % pour des fragments de 500 caractères,
de 70 à 90 % pour des fragments de 800. Deux observations concordantes valent
mieux qu'un gain isolé, et l'effet paraît donc réel.

L'interprétation est que le pipeline tolère bien le bruit. Transmettre deux
passages supplémentaires, parfois hors sujet, ne dégrade pas la réponse : le
modèle de langage ignore ce qui ne sert pas. Le risque de manquer le passage
pertinent pèse plus lourd que celui d'en ajouter d'inutiles.

### 5.3 Effet de la taille de découpage

À `top_k` constant, faire varier la taille de fragment de 300 à 1200 caractères
donne successivement 80, 90, 70 et 70 % de réponses correctes.

Ce résultat contredit l'hypothèse initiale. Les échecs observés en première
analyse laissaient penser que des fragments plus longs amélioreraient les
choses, puisqu'ils préserveraient les tableaux entiers plutôt que de les
couper. La mesure montre l'inverse : à 800 et 1200 caractères, la performance
chute nettement.

L'explication tient au fonctionnement des embeddings. Un vecteur représente le
sens global du texte qu'il encode ; plus le fragment est long, plus il mêle de
sujets, et plus son vecteur devient un compromis qui ne ressemble précisément à
aucune question. Le taux de rappel de la source le confirme : il tombe à 88,9 %
pour les fragments de 1200 caractères, la plus mauvaise valeur de la série.

Deux conclusions en découlent. La relation entre taille de fragment et qualité
n'est pas monotone : il existe un optimum intermédiaire, situé ici autour de
500 caractères. Et cet optimum n'était pas devinable par le raisonnement, ce qui
justifie a posteriori la démarche expérimentale.

### 5.4 Ce que le rappel de la source révèle

La configuration à 300 caractères présente un profil singulier : 100 % de rappel
de la source, mais seulement 80 % de réponses correctes. Le document attendu
était donc systématiquement remonté, et la réponse restait pourtant fausse dans
une question sur cinq.

L'explication tient à la définition de la métrique. Le rappel est mesuré au
niveau du **document**, non du fragment. Avec des fragments courts,
l'information se disperse : le bon document est retrouvé, mais le passage
remonté n'est pas celui qui contient la réponse. Cette limite méthodologique
n'a été identifiée qu'en confrontant les deux métriques, ce qui illustre
l'intérêt d'en mesurer plusieurs.

### 5.5 Analyse des cas d'échec

Trois échecs observés sur la configuration `top_k = 3` relèvent de trois causes
distinctes.

**Un échec de la métrique.** À la question portant sur le congé pour mariage,
l'assistant a répondu « quatre jours ouvrés » alors que le mot-clé attendu était
`4`. La réponse était exacte ; c'est le juge par mots-clés qui a échoué, faute
de reconnaître un chiffre écrit en toutes lettres. Le juge par modèle de langage
a validé la réponse.

**Un échec de recherche.** À la question « quand un nouvel arrivant reçoit-il
son matériel informatique et par qui ? », les trois passages remontés
provenaient tous du document consacré au matériel informatique, dont le
vocabulaire correspond littéralement à la question. Le document décrivant le
parcours d'intégration, qui contient la réponse, n'a jamais eu de place.
L'assistant a déclaré ne pas disposer de l'information — comportement correct
au vu du contexte reçu, mais réponse inutile pour l'utilisateur. C'est
précisément ce cas que le passage à `top_k = 5` a corrigé.

**Un échec de génération.** À la question sur le congé pour décès d'un parent,
le document attendu figurait bien parmi les passages remontés, et l'assistant a
pourtant répondu ne pas savoir. Le fragment sélectionné contenait une partie du
tableau des congés exceptionnels, mais vraisemblablement pas la ligne concernée.
Le bon document ne garantit pas le bon passage.

Ces trois cas montrent qu'un taux global ne suffit pas à piloter un système : il
indique qu'une dégradation existe, pas où la corriger.

### 5.6 Variabilité des mesures

Plusieurs exécutions de la configuration retenue, à paramètres strictement
identiques, ont produit des taux différents : 100 %, 95 %, 95 %, 90 % et 85 %.

La température était pourtant fixée à zéro. Ce paramètre contrôle le caractère
aléatoire de la génération : à chaque étape, le modèle produit une distribution
de probabilité sur les mots possibles, et la température détermine comment y
puiser. À une valeur élevée, le tirage est aléatoire et les formulations
varient ; à zéro, le modèle retient systématiquement le mot le plus probable, ce
qui devrait rendre la sortie déterministe.

Cette attente n'est pas vérifiée en pratique. Les modèles servis par API
conservent une part de variabilité, liée au traitement par lots côté serveur et
à l'ordre des calculs en virgule flottante. La seule source d'aléa non
maîtrisée dans ce dispositif est donc le fournisseur lui-même.

La conséquence est directe. Un écart de dix points entre deux exécutions peut
relever du bruit et non d'une dégradation réelle. Le seuil d'alerte a donc été
fixé à 90 % plutôt qu'à 95 % : il tolère une question défaillante et ne se
déclenche qu'à partir de deux, ce qui limite les fausses alertes. Un seuil plus
exigeant supposerait un jeu de questions plus large, où chaque question pèserait
moins lourd dans le total.

## 6. Coût, gouvernance et sécurité

### 6.1 Coût d'exploitation

Le dispositif d'évaluation est la source de coût dominante, bien avant l'usage
courant de l'assistant. Chaque question de référence déclenche deux appels
d'API — un pour produire la réponse, un pour la juger — soit quarante appels par
évaluation complète. Rejouée quotidiennement, la surveillance représente environ
quatorze mille six cents appels par an, pour une consommation de quatre minutes
de traitement par exécution.

Ce coût est linéaire en nombre de questions, ce qui installe un arbitrage direct
entre fiabilité de la mesure et dépense. Un jeu de cinquante questions
diviserait par plus de deux le poids de chaque question dans le total et
autoriserait un seuil d'alerte plus exigeant, au prix d'un coût multiplié par
deux et demi. Le jeu de vingt questions retenu ici est un compromis, assumé
comme tel : il impose un seuil à 90 % là où un jeu plus large permettrait 95 %.

Deux leviers permettraient de réduire cette dépense sans perdre la capacité de
détection. Le premier consiste à supprimer le juge par modèle de langage lors
des exécutions de routine : le juge par mots-clés est gratuit et suffit à
repérer une chute franche, la mesure fine n'étant nécessaire que
périodiquement. Le second consiste à découpler les fréquences — un jeu réduit
quotidien pour détecter les pannes, le jeu complet une fois par semaine.

Le calcul des embeddings, lui, s'exécute localement et n'entraîne aucun coût
d'API. Il mobilise en revanche environ 470 Mo de mémoire vive pour le modèle
chargé, ce qui constitue la contrainte matérielle principale du système.

### 6.2 Gouvernance

**Dépendance au fournisseur.** L'expérience conduite pendant ce projet a montré
qu'un modèle peut être retiré, restreint ou remplacé sans préavis : trois
modèles successifs ont dû être abandonnés avant d'aboutir à une configuration
stable. Cette dépendance a deux conséquences. D'une part, l'application doit
prévoir des mécanismes de repli — réessai, temporisation, gestion explicite des
codes d'erreur. D'autre part, la comparabilité des mesures dans le temps n'est
pas garantie : si le fournisseur modifie le modèle sous-jacent sans changer son
identifiant, une baisse de qualité pourrait être attribuée à tort au corpus. Le
modèle utilisé est pour cette raison enregistré comme paramètre de chaque
exécution MLflow.

**Traçabilité.** Trois dispositifs y concourent. MLflow conserve, pour chaque
évaluation, les paramètres employés et les métriques obtenues, ce qui permet de
retrouver quelle configuration a produit quel résultat. Prefect conserve
l'historique des exécutions avec leur statut, leur durée et leurs journaux. Le
workflow n8n est versionné, chaque publication portant un numéro et une
description. Le code, enfin, est suivi sous Git.

**Reproductibilité.** Les dépendances sont figées dans un fichier
`requirements.txt` précisant les versions exactes. Cette reproductibilité reste
partielle : l'environnement de développement a imposé un environnement virtuel
ouvert aux paquets système, plusieurs bibliothèques présentaient des
incompatibilités avec la version de Python utilisée, et n8n est déployé en
conteneur distinct. Une conteneurisation complète de la chaîne constituerait
l'étape suivante.

**Télémétrie.** Prefect transmet par défaut des données d'usage anonymes à son
éditeur. Ce comportement se désactive par une variable d'environnement. Le
signaler relève de la gouvernance : un composant d'infrastructure qui
communique vers l'extérieur sans configuration explicite mérite d'être
inventorié.

### 6.3 Sécurité des données

Le corpus utilisé ici est fictif, ce qui neutralise le risque dans le cadre du
projet. Un déploiement réel porterait en revanche sur des procédures internes,
et l'analyse doit être menée comme si c'était le cas.

**Ce qui reste local.** L'indexation ne provoque aucune sortie de données : le
découpage et le calcul des embeddings s'exécutent sur la machine, et la base
vectorielle est un fichier local. L'ensemble du corpus ne transite donc jamais
par un service externe.

**Ce qui sort.** À chaque question, les passages retrouvés sont transmis à
l'API Gemini avec la question elle-même. Une procédure RH n'est pas une donnée
personnelle, mais elle constitue une information interne dont la diffusion
échappe à l'entreprise dès lors qu'elle quitte son réseau. Le risque croît si
le corpus venait à contenir des éléments nominatifs — organigrammes,
situations individuelles, données de rémunération. Les conditions d'utilisation
et de conservation appliquées par le fournisseur devraient alors être examinées
avant tout déploiement, et un modèle hébergé en interne deviendrait le choix
par défaut.

**Gestion des secrets.** La clé d'API est stockée dans un fichier `.env` exclu
du dépôt Git, ce qui évite l'erreur la plus courante — la publication d'un
identifiant dans un dépôt public. Cette protection reste minimale : le fichier
est en clair sur la machine et n'est pas chiffré. Un déploiement en production
recourrait à un gestionnaire de secrets dédié.

**Exposition des services.** MLflow, Prefect et n8n sont accessibles sans
authentification sur l'hôte local. Cette configuration convient à un poste de
développement, mais aucun de ces services ne devrait être exposé en l'état sur
un réseau d'entreprise. Le webhook n8n, en particulier, accepte toute requête
sans vérification d'origine : une authentification par jeton serait nécessaire
dès lors qu'il deviendrait joignable au-delà de la machine.

**Destination des alertes.** La démonstration achemine les alertes vers un
service public de réception de requêtes, choisi pour sa simplicité. Le contenu
transmis se limite à un taux et à un seuil, sans information sensible, mais ce
point de sortie devrait être remplacé par un canal interne — messagerie
d'entreprise ou système de tickets — dans tout usage réel.

## 6. Coût, gouvernance et sécurité

### 6.1 Coût d'exploitation

Le dispositif d'évaluation est la source de coût dominante, bien avant l'usage
courant de l'assistant. Chaque question de référence déclenche deux appels
d'API — un pour produire la réponse, un pour la juger — soit quarante appels par
évaluation complète. Rejouée quotidiennement, la surveillance représente environ
quatorze mille six cents appels par an, pour une consommation de quatre minutes
de traitement par exécution.

Ce coût est linéaire en nombre de questions, ce qui installe un arbitrage direct
entre fiabilité de la mesure et dépense. Un jeu de cinquante questions
diviserait par plus de deux le poids de chaque question dans le total et
autoriserait un seuil d'alerte plus exigeant, au prix d'un coût multiplié par
deux et demi. Le jeu de vingt questions retenu ici est un compromis, assumé
comme tel : il impose un seuil à 90 % là où un jeu plus large permettrait 95 %.

Deux leviers permettraient de réduire cette dépense sans perdre la capacité de
détection. Le premier consiste à supprimer le juge par modèle de langage lors
des exécutions de routine : le juge par mots-clés est gratuit et suffit à
repérer une chute franche, la mesure fine n'étant nécessaire que
périodiquement. Le second consiste à découpler les fréquences — un jeu réduit
quotidien pour détecter les pannes, le jeu complet une fois par semaine.

Le calcul des embeddings, lui, s'exécute localement et n'entraîne aucun coût
d'API. Il mobilise en revanche environ 470 Mo de mémoire vive pour le modèle
chargé, ce qui constitue la contrainte matérielle principale du système.

### 6.2 Gouvernance

**Dépendance au fournisseur.** L'expérience conduite pendant ce projet a montré
qu'un modèle peut être retiré, restreint ou remplacé sans préavis : trois
modèles successifs ont dû être abandonnés avant d'aboutir à une configuration
stable. Cette dépendance a deux conséquences. D'une part, l'application doit
prévoir des mécanismes de repli — réessai, temporisation, gestion explicite des
codes d'erreur. D'autre part, la comparabilité des mesures dans le temps n'est
pas garantie : si le fournisseur modifie le modèle sous-jacent sans changer son
identifiant, une baisse de qualité pourrait être attribuée à tort au corpus. Le
modèle utilisé est pour cette raison enregistré comme paramètre de chaque
exécution MLflow.

**Traçabilité.** Trois dispositifs y concourent. MLflow conserve, pour chaque
évaluation, les paramètres employés et les métriques obtenues, ce qui permet de
retrouver quelle configuration a produit quel résultat. Prefect conserve
l'historique des exécutions avec leur statut, leur durée et leurs journaux. Le
workflow n8n est versionné, chaque publication portant un numéro et une
description. Le code, enfin, est suivi sous Git.

**Reproductibilité.** Les dépendances sont figées dans un fichier
`requirements.txt` précisant les versions exactes. Cette reproductibilité reste
partielle : l'environnement de développement a imposé un environnement virtuel
ouvert aux paquets système, plusieurs bibliothèques présentaient des
incompatibilités avec la version de Python utilisée, et n8n est déployé en
conteneur distinct. Une conteneurisation complète de la chaîne constituerait
l'étape suivante.

**Télémétrie.** Prefect transmet par défaut des données d'usage anonymes à son
éditeur. Ce comportement se désactive par une variable d'environnement. Le
signaler relève de la gouvernance : un composant d'infrastructure qui
communique vers l'extérieur sans configuration explicite mérite d'être
inventorié.

### 6.3 Sécurité des données

Le corpus utilisé ici est fictif, ce qui neutralise le risque dans le cadre du
projet. Un déploiement réel porterait en revanche sur des procédures internes,
et l'analyse doit être menée comme si c'était le cas.

**Ce qui reste local.** L'indexation ne provoque aucune sortie de données : le
découpage et le calcul des embeddings s'exécutent sur la machine, et la base
vectorielle est un fichier local. L'ensemble du corpus ne transite donc jamais
par un service externe.

**Ce qui sort.** À chaque question, les passages retrouvés sont transmis à
l'API Gemini avec la question elle-même. Une procédure RH n'est pas une donnée
personnelle, mais elle constitue une information interne dont la diffusion
échappe à l'entreprise dès lors qu'elle quitte son réseau. Le risque croît si
le corpus venait à contenir des éléments nominatifs — organigrammes,
situations individuelles, données de rémunération. Les conditions d'utilisation
et de conservation appliquées par le fournisseur devraient alors être examinées
avant tout déploiement, et un modèle hébergé en interne deviendrait le choix
par défaut.

**Gestion des secrets.** La clé d'API est stockée dans un fichier `.env` exclu
du dépôt Git, ce qui évite l'erreur la plus courante — la publication d'un
identifiant dans un dépôt public. Cette protection reste minimale : le fichier
est en clair sur la machine et n'est pas chiffré. Un déploiement en production
recourrait à un gestionnaire de secrets dédié.

**Exposition des services.** MLflow, Prefect et n8n sont accessibles sans
authentification sur l'hôte local. Cette configuration convient à un poste de
développement, mais aucun de ces services ne devrait être exposé en l'état sur
un réseau d'entreprise. Le webhook n8n, en particulier, accepte toute requête
sans vérification d'origine : une authentification par jeton serait nécessaire
dès lors qu'il deviendrait joignable au-delà de la machine.

**Destination des alertes.** La démonstration achemine les alertes vers un
service public de réception de requêtes, choisi pour sa simplicité. Le contenu
transmis se limite à un taux et à un seuil, sans information sensible, mais ce
point de sortie devrait être remplacé par un canal interne — messagerie
d'entreprise ou système de tickets — dans tout usage réel.

## 7. Limites et pistes d'amélioration

### 7.1 Limites

**Le corpus.** Le jeu de documents est synthétique, donc plus régulier qu'une
documentation d'entreprise réelle : formulations homogènes, absence de
contradictions, structure uniforme. Les taux obtenus sont vraisemblablement
supérieurs à ceux qu'obtiendrait le même système sur des procédures
authentiques.

**La reproductibilité de la mesure.** Des écarts allant jusqu'à quinze points
ont été observés entre exécutions strictement identiques, malgré une
température fixée à zéro. Cette variabilité provient du service d'API, seule
source d'aléa non maîtrisée du dispositif. Elle impose un seuil d'alerte
permissif et interdit d'interpréter un écart faible comme une dégradation.

**La reproductibilité de l'environnement.** Le projet s'exécute dans un
environnement virtuel ouvert aux paquets du système, choix imposé par les
contraintes matérielles de la machine de développement. Plusieurs dépendances
ne sont donc pas installées par le fichier `requirements.txt` mais héritées de
l'hôte, ce qui ne garantit pas qu'un tiers reconstitue un environnement
identique.

**L'absence d'historique long.** Le dispositif de suivi est fonctionnel, mais
il n'a été exécuté que sur quelques jours. Aucune dérive réelle n'a donc été
observée : le détecteur est construit, il n'a pas encore eu l'occasion de
détecter quoi que ce soit. La démonstration porte sur le mécanisme, pas sur son
efficacité en conditions durables.

**La granularité du rappel.** Le jeu de référence associe à chaque question le
document censé contenir la réponse, non le passage précis. La métrique de
rappel vérifie donc qu'un fragment issu du bon document a été remonté, sans
garantir qu'il s'agisse du bon fragment. La configuration à 300 caractères
illustre l'écart : rappel parfait, mais une réponse sur cinq erronée.

**L'alerte non éprouvée de bout en bout.** Le webhook, la condition de seuil et
la notification ont été validés par envoi manuel. Le franchissement du seuil
n'a en revanche jamais été provoqué depuis le flux complet, la qualité mesurée
étant restée au-dessus de 90 % à chaque exécution.

**Le préfixe de contexte.** Chaque fragment est préfixé du nom de son document
d'origine afin de rester interprétable lorsqu'il ne contient qu'une portion de
tableau. Ce préfixe entre cependant dans le calcul de l'embedding : une
question comportant le mot « congé » se rapproche mécaniquement de tous les
fragments issus du document sur les congés payés, quel que soit leur contenu.
Le bénéfice net de ce choix n'a pas été mesuré.

### 7.2 Pistes d'amélioration

**Élargir le jeu de référence.** Passer à cinquante ou cent questions réduirait
le poids de chaque question dans le total et permettrait un seuil d'alerte plus
exigeant. Le coût doublerait ou quintuplerait, ce qui plaide pour découpler les
fréquences : un jeu réduit quotidien, le jeu complet chaque semaine.

**Mesurer le rappel au niveau du fragment.** Plutôt que d'indiquer le document
attendu, le jeu de référence pourrait contenir une phrase caractéristique
devant figurer dans au moins un fragment remonté. La métrique évaluerait alors
ce qui compte réellement : la récupération du bon passage, et non du bon
document. Cette formulation présente en outre l'avantage de rester valide
lorsque la taille de découpage change.

**Ajouter un juge de fidélité.** Un troisième juge vérifierait que la réponse
produite est justifiée par les passages transmis, indépendamment de la réponse
attendue. Cette métrique détecte les hallucinations, qu'aucun des deux juges
actuels ne mesure directement.

**Recourir à une recherche hybride.** Combiner la recherche vectorielle à une
recherche par mots-clés traiterait le cas d'échec observé, où un document au
vocabulaire littéralement proche de la question monopolisait les passages
remontés au détriment du document pertinent.

**Conteneuriser l'ensemble.** Une orchestration par `docker compose` des quatre
composants — pipeline, MLflow, Prefect, n8n — lèverait les réserves formulées
sur la reproductibilité et rendrait le déploiement indépendant de la machine
hôte.