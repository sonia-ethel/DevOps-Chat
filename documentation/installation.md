# Installation et lancement de DAC

Ce guide explique comment installer et lancer DAC pour le CodeCamp ETNA 2026.

Pour une fiche de commandes rapides, voir [commandes-linux.md](commandes-linux.md).
Pour comprendre le fichier `.env`, voir [variables-environnement.md](variables-environnement.md).

## 1. Prerequis

Obligatoire:

- Git
- Docker Desktop ou Docker Engine recent
- Docker Compose v2
- Un navigateur web recent

Recommande pour le lancement local hors Docker:

- Python 3.12+
- Node.js 22.12+ ou au minimum 20.19+
- npm
- Terraform CLI si le backend est lance sans Docker

Verifier les versions:

git --version
docker version
docker compose version
python3 --version
node -v
npm -v
terraform -version

Versions conseillees:

Docker API 1.44+
Python 3.12+
Node.js 22.12+
Terraform 1.6+

## 2. Configuration `.env`

Depuis la racine du projet:

cp .env.example .env

Le fichier `.env` officiel est celui de la racine.

Il est utilise par:

- Docker Compose;
- le backend FastAPI;
- le lancement manuel depuis `devops_api`.

Pour generer `SECRET_KEY`, `FERNET_KEY` et `FERNET_SECRET`, voir [variables-environnement.md](variables-environnement.md).

## 3. Lancement avec Docker

Depuis la racine du projet:

docker compose up --build

Acces:

Frontend: http://localhost:5173
Backend:  http://localhost:8000
Swagger:  http://localhost:8000/docs
Health:   http://localhost:8000/health

Arreter le projet:

docker compose down

Arreter et supprimer aussi la base PostgreSQL Docker:

docker compose down -v

## 4. Lancement local sans Docker complet

Cette methode est utile si Docker ne peut pas lancer tout le projet.

Terminal 1 - PostgreSQL:

docker compose up -d postgres

Terminal 2 - Backend FastAPI:

cp .env.example .env
cd devops_api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Verifier le backend:

curl http://localhost:8000/health

Terminal 3 - Frontend React:

cd frontend
npm install
npm run dev

Ouvrir:

http://localhost:5173

## 5. Configuration AWS

Pour deployer reellement une VM, il faut un compte AWS de test et des credentials IAM.

Dans l'interface DAC:

1. Creer un compte utilisateur.
2. Aller dans l'onboarding AWS.
3. Entrer l'Access Key ID, la Secret Access Key et la region.
4. DAC valide les credentials avant de les enregistrer.

Droits AWS minimaux attendus pour la demo:

- `sts:GetCallerIdentity`
- actions EC2 necessaires pour creer, lister et supprimer une instance
- security groups si le workflow en cree

Utiliser un compte sandbox pour eviter les risques.

## 6. Test manuel de demo

Dans le chat DAC:

cree une instance EC2 Ubuntu

Puis:

AWS Ubuntu 22.04 t3.micro eu-west-1

Puis confirmer:

ok

Tester l'inventaire:

liste des ressources

Tester la suppression:

supprimer mon instance

## 7. Problemes frequents

### Docker refuse de lancer

Erreur possible:

client version 1.43 is too old. Minimum supported API version is 1.44

Solution: mettre Docker a jour.

### Frontend Vite ne demarre pas

Erreur possible:

TypeError: crypto.hash is not a function

Solution: utiliser Node.js 22.12+.

nvm install 22
nvm use 22
npm install
npm run dev

### AWS refuse Terraform

Erreur possible:

InvalidClientTokenId

Cela veut dire que les credentials AWS sont invalides, expires ou mal copies.

Solution: retourner dans l'onboarding AWS et enregistrer une nouvelle cle.

### Cle Fernet manquante

Erreur possible:

ERR FERNET_KEY non defini dans l'environnement.

Solution: generer les secrets avec [variables-environnement.md](variables-environnement.md), puis redemarrer le backend.

## 8. Commandes de verification

Backend:

cd devops_api
python3 -m compileall app

Frontend:

cd frontend
npm run build

Docker:

docker compose config
