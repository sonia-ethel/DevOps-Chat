# DAC - DevOps-as-a-Chat CodeCamp ETNA 2026

DAC est un assistant DevOps conversationnel. Cette branche `codecamp-etna-2026` fournit un MVP propre pour des etudiants: authentification, onboarding AWS, chat DAC, detection d'intention, generation Terraform, execution, inventaire et suppression de ressources.

## Objectif etudiant

Le but n'est pas de refaire tout le projet. Le but est de comprendre une base existante, de lancer une demo reelle, puis d'ameliorer un axe precis: UX, intentions, preview, observabilite, logs, IA ou architecture.

## Parcours fonctionnel garde

1. Creer un compte ou se connecter.
2. Enregistrer des credentials AWS via l'onboarding.
3. Ouvrir le chat DAC.
4. Demander une infrastructure AWS.
5. Confirmer l'action.
6. Laisser Terraform creer la ressource.
7. Lister les ressources.
8. Supprimer les ressources creees.

## Prerequis

Voir le guide complet: [documentation/installation.md](documentation/installation.md).

Pour une fiche rapide de commandes Linux a copier-coller: [documentation/commandes-linux.md](documentation/commandes-linux.md).

Pour comprendre et generer les variables `.env`: [documentation/variables-environnement.md](documentation/variables-environnement.md).

Resume:

- Docker et Docker Compose recents.
- Docker API 1.44+ requis pour lancer les conteneurs.
- Node.js 22.12+ si lancement frontend hors Docker.
- Python 3.12+ si lancement backend hors Docker.
- Un compte AWS de test avec credentials IAM valides.

## Lancement Docker

Lancer le projet:

```bash
docker compose up --build
```

Optionnel: copier `.env.example` vers `.env` si vous voulez personnaliser les variables locales.

Le fichier `.env` officiel est celui de la racine du repo. Il est utilise par Docker Compose et par le backend FastAPI, meme quand `uvicorn` est lance depuis `devops_api`.

Acces:

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Healthcheck: http://localhost:8000/health

## Lancement manuel

### Backend

```bash
cd devops_api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Configuration AWS

Dans l'interface, cliquer sur l'indicateur AWS ou aller dans l'onboarding AWS.

Renseigner:

- AWS Access Key ID
- AWS Secret Access Key
- Region, par exemple `eu-west-1`

Le backend valide les credentials via AWS STS avant de les sauvegarder. Si la cle est expiree ou invalide, DAC renvoie une erreur lisible et l'utilisateur peut corriger ses credentials.

## Tests manuels rapides

Dans le chat DAC:

```text
cree une instance EC2 Ubuntu
```

Puis donner les details:

```text
AWS Ubuntu 22.04 t3.micro eu-west-1
```

Confirmer:

```text
ok
```

Autres prompts utiles:

```text
liste des ressources
```

```text
supprimer mon instance
```

## Endpoints principaux

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `POST /user/aws-credentials`
- `GET /user/aws-credentials`
- `POST /chat_creation/chat_message`
- `POST /generate`
- `POST /executions/create`
- `POST /executions/{execution_id}/execute`
- `GET /resources/list_all_resources`
- `POST /resources/delete_resource`

## Structure du rendu

```text
devops-as-a-chat/
├── devops_api/
├── frontend/
├── docker-compose.yml
├── .env.example
├── documentation/
└── support/
```

## Limites connues

- Le MVP etudiant cible AWS et Terraform.
- Les credentials AWS doivent etre valides et non expires.
- Le compte AWS doit avoir les droits IAM necessaires.
- Le backend cree les tables au demarrage Docker via SQLAlchemy `create_all`; les migrations Alembic historiques sont conservees mais ne sont pas le chemin principal du MVP.
- Le build frontend affiche un warning de taille de bundle et recommande Node 20.19+ ou 22.12+.

## Nettoyage realise sur cette branche

- Artefacts generes retires du runtime.
- Routes dev/test/admin/Kubernetes/plans retirees du rendu etudiant.
- Un seul moteur chat actif pour le parcours etudiant: `/chat_creation/chat_message`.
- Frontend simplifie: login/register, onboarding AWS, dashboard, chat, ressources, profile.
- Dockerfiles backend/frontend ajoutes.
- Documentation legacy retiree du rendu etudiant.
