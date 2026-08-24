# Guide Git Etudiants - DAC CodeCamp ETNA 2026

Ce guide est fait pour vous accompagner pendant le Code Camp ETNA DAC, meme si vous debutez avec Git, GitHub ou un projet full-stack existant.

L'objectif est simple: vous aider a cloner le projet, travailler proprement en equipe, lancer DAC, puis livrer une contribution claire et demonstrable.

## 1. Presentation du projet

### Qu'est-ce que DevOps-as-a-Chat ?

DevOps-as-a-Chat, ou DAC, est un projet qui permet de piloter des actions DevOps depuis une interface de chat.

Au lieu d'ecrire directement toutes les commandes ou tous les fichiers de configuration, l'utilisateur dialogue avec DAC. Le projet peut ensuite aider a:

- comprendre une demande utilisateur;
- detecter une intention DevOps;
- generer une action technique;
- lancer une execution;
- afficher un resultat;
- expliquer certaines erreurs;
- guider l'utilisateur dans un workflow.

Dans cette version CodeCamp, le parcours principal est centre sur une demonstration AWS avec Terraform, un chat DAC, un onboarding AWS et une interface React.

### Objectif du Code Camp

Pendant le Code Camp, votre objectif n'est pas de tout refaire.

Vous devez:

1. comprendre le projet existant;
2. l'installer et le lancer;
3. identifier une limite ou une amelioration utile;
4. choisir un challenge;
5. developper une contribution fonctionnelle;
6. documenter votre travail;
7. presenter une demonstration claire.

### Depot GitHub

Depot public du Code Camp:

```text
https://github.com/tourearnaud/devops-as-a-chat-codecamp-etna-2026.git
```

Branche de depart:

```text
codecamp-etna-2026
```

### Architecture generale

Structure simplifiee:

```text
devops-as-a-chat-codecamp-etna-2026/
├── devops_api/          # Backend FastAPI
├── frontend/            # Frontend React
├── documentation/       # Documentation technique et installation
├── support/             # Support de presentation
├── docker-compose.yml   # Lancement Docker
├── .env.example         # Exemple de configuration
└── README.md            # Point d'entree du projet
```

Vue generale:

```text
React frontend
  -> FastAPI backend
    -> detection d'intention
    -> generation Terraform / Ansible
    -> execution
    -> base PostgreSQL
    -> retour dans le chat
```

## 2. Installation du projet

### Cloner le projet

```bash
git clone -b codecamp-etna-2026 https://github.com/tourearnaud/devops-as-a-chat-codecamp-etna-2026.git
cd devops-as-a-chat-codecamp-etna-2026
```

### Verifier la branche

```bash
git branch
```

Resultat attendu:

```bash
* codecamp-etna-2026
```

Si vous n'etes pas sur la bonne branche:

```bash
git checkout codecamp-etna-2026
```

## 3. Commandes Git indispensables

### Voir les fichiers modifies

```bash
git status
```

Cette commande est votre meilleure amie. Utilisez-la souvent.

Elle permet de voir:

- les fichiers modifies;
- les fichiers ajoutes;
- les fichiers non suivis par Git;
- la branche courante.

### Voir les modifications

```bash
git diff
```

Cette commande montre les lignes modifiees dans vos fichiers.

### Recuperer les dernieres modifications

```bash
git pull
```

A utiliser avant de commencer a travailler, surtout en groupe.

### Ajouter les modifications

```bash
git add .
```

Cette commande prepare tous les fichiers modifies pour le prochain commit.

Pour ajouter un seul fichier:

```bash
git add nom_du_fichier
```

### Creer un commit

```bash
git commit -m "description claire"
```

Exemples de bons messages:

```bash
git commit -m "feat: improve chat error messages"
git commit -m "docs: add installation notes"
git commit -m "fix: handle missing aws credentials"
```

### Envoyer les modifications

```bash
git push
```

Si Git vous dit que la branche n'existe pas encore sur GitHub, utilisez:

```bash
git push -u origin nom-de-votre-branche
```

## 4. Creer sa branche de travail

Ne travaillez pas directement sur `codecamp-etna-2026`.

Creez une branche pour votre groupe ou votre fonctionnalite.

Exemple groupe:

```bash
git checkout -b groupe-1
```

Exemple fonctionnalite:

```bash
git checkout -b amelioration-chat
```

Verification:

```bash
git branch
```

La branche active est celle avec une etoile:

```bash
* groupe-1
  codecamp-etna-2026
```

## 5. Revenir a l'etat precedent

### Annuler un fichier modifie

```bash
git restore nom_du_fichier
```

Exemple:

```bash
git restore README.md
```

### Annuler toutes les modifications non commitees

Attention: cette commande supprime toutes vos modifications locales non commitees.

```bash
git restore .
```

Avant de l'utiliser, verifiez toujours:

```bash
git status
```

## 6. Mettre a jour sa branche

Pour recuperer la derniere version de la branche principale du Code Camp:

```bash
git checkout codecamp-etna-2026
git pull
```

Puis revenir sur votre branche:

```bash
git checkout ma-branche
```

Si vous voulez reintegrer les modifications de `codecamp-etna-2026` dans votre branche, demandez conseil a votre equipe ou a l'encadrant avant de faire un merge ou un rebase.

## 7. Lancer le backend

Depuis la racine du projet:

```bash
cd devops_api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Le backend sera disponible ici:

```text
http://localhost:8000
```

La documentation Swagger sera disponible ici:

```text
http://localhost:8000/docs
```

Pour quitter l'environnement virtuel Python:

```bash
deactivate
```

## 8. Lancer le frontend

Dans un deuxieme terminal, depuis la racine du projet:

```bash
cd frontend
npm install
npm run dev
```

Le frontend sera disponible ici:

```text
http://localhost:5173
```

Si `npm run dev` echoue avec une erreur Node ou Vite, utilisez Node.js 22.12 ou plus recent.

Avec `nvm`:

```bash
nvm install 22
nvm use 22
npm install
npm run dev
```

## 9. Docker

Docker permet de lancer le projet plus facilement avec PostgreSQL, le backend et le frontend.

### Demarrage

Depuis la racine du projet:

```bash
docker compose up --build
```

### Arret

```bash
docker compose down
```

### Voir les logs

```bash
docker compose logs -f
```

### Pre-requis Docker

Docker doit etre recent. Le projet attend Docker API 1.44 ou plus recent.

Verifier:

```bash
docker version
docker compose version
```

## 10. Variables d'environnement

Le fichier suivant contient un exemple de configuration:

```text
.env.example
```

Pour creer votre fichier local:

```bash
cp .env.example .env
```

Important:

- `.env.example` peut etre commite;
- `.env` ne doit jamais etre commite;
- `.env` peut contenir des secrets locaux;
- ne mettez jamais de vraies cles AWS dans Git.

Le backend charge automatiquement ce `.env` racine, meme si vous lancez `uvicorn` depuis le dossier `devops_api`.

## 11. Parcours utilisateur DAC

Parcours de demonstration conseille:

1. Creer un compte.
2. Se connecter.
3. Configurer AWS via l'onboarding.
4. Ouvrir le chat DAC.
5. Demander la creation d'une VM.
6. Confirmer l'action.
7. Executer Terraform.
8. Visualiser les ressources.
9. Configurer une ressource via Ansible si votre challenge le prevoit.
10. Supprimer les ressources creees pour eviter les couts.

Exemple de message dans le chat:

```text
cree une instance EC2 Ubuntu
```

Exemple de parametres:

```text
AWS Ubuntu 22.04 t3.micro eu-west-1
```

Confirmation:

```text
ok
```

## 12. Bugs connus

Cette branche est une base pedagogique. Elle est fonctionnelle pour le Code Camp, mais certains points restent perfectibles.

Bugs ou limites connus:

- Le flux DAC peut parfois demander une double saisie lors de la detection d'intention.
- La gestion AWS depend de credentials valides et non expires.
- Docker n'a pas ete valide sur les anciennes versions de Docker.
- Quelques helpers frontend legacy existent encore mais ne sont pas utilises dans le parcours principal.
- Une vraie generation IA necessite une cle OpenAI; par defaut le projet peut fonctionner en mode mock.

Ces limites sont aussi des opportunites de challenge.

## 13. Bonnes pratiques

### A faire

- Travailler sur une branche dediee.
- Faire des commits frequents.
- Donner des messages de commit clairs.
- Lancer le projet avant de presenter votre contribution.
- Documenter vos choix techniques.
- Verifier `git status` avant chaque commit.

### A ne jamais faire

- Ne jamais commit de cles AWS.
- Ne jamais commit de fichier `.env`.
- Ne jamais commit de fichier `.pem` ou de cle privee.
- Ne jamais commit `node_modules`.
- Ne jamais commit `venv` ou `.venv`.
- Ne jamais lancer une action cloud sans comprendre ce qu'elle fait.

Avant chaque commit, posez-vous trois questions:

1. Est-ce que mon code fonctionne ?
2. Est-ce que j'ai ajoute uniquement les fichiers utiles ?
3. Est-ce que mon commit ne contient aucun secret ?

## 14. Liens utiles

Git:

```text
https://git-scm.com/docs
```

GitHub:

```text
https://docs.github.com
```

FastAPI:

```text
https://fastapi.tiangolo.com
```

React:

```text
https://react.dev
```

Terraform:

```text
https://developer.hashicorp.com/terraform/docs
```

Ansible:

```text
https://docs.ansible.com
```

AWS:

```text
https://docs.aws.amazon.com
```

## Conclusion

Git peut sembler difficile au debut, mais vous n'avez pas besoin de tout connaitre pour avancer.

Retenez surtout ce cycle:

```bash
git status
git add .
git commit -m "message clair"
git push
```

Et surtout: travaillez en equipe, demandez de l'aide quand vous etes bloques, et gardez une demonstration simple et fiable.
