# Fiche commandes Linux - lancer DAC

Cette fiche donne les commandes utiles pour lancer DAC pendant le CodeCamp ETNA 2026.

Objectif: un etudiant clone le projet, lance Docker, ouvre le frontend, puis teste le chat DAC.

Pour le detail des variables `.env`, voir [variables-environnement.md](variables-environnement.md).

## 1. Aller dans le projet

cd ~/devops-as-a-chat

Verifier que vous etes sur la bonne branche:

git branch --show-current
git status

La branche attendue est:

codecamp-etna-2026

## 2. Verifier les outils installes

git --version
docker version
docker compose version

Pour un lancement local sans Docker complet:

python3 --version
node -v
npm -v
terraform -version

Versions conseillees:

Docker Compose v2
Docker API 1.44+
Python 3.12+
Node.js 22.12+
Terraform 1.6+

## 3. Lancement recommande avec Docker

Depuis la racine du projet:

docker compose up --build

Ouvrir ensuite:

Frontend: http://localhost:5173
Backend:  http://localhost:8000
Swagger:  http://localhost:8000/docs
Health:   http://localhost:8000/health

## 4. Docker en arriere-plan

Lancer sans bloquer le terminal:

docker compose up --build -d

Voir les conteneurs:

docker compose ps

Voir tous les logs:

docker compose logs -f

Voir seulement les logs backend:

docker compose logs -f backend

Voir seulement les logs frontend:

docker compose logs -f frontend

Arreter le projet:

docker compose down

Arreter et supprimer aussi la base PostgreSQL Docker:

docker compose down -v

## 5. Verifier la configuration Docker

Avant de lancer, vous pouvez verifier que le fichier Docker Compose est valide:

docker compose config

Si vous voyez une erreur comme:

client version 1.43 is too old. Minimum supported API version is 1.44

Il faut mettre Docker a jour.

## 6. Lancement local sans Docker complet

Utiliser cette methode seulement si Docker ne peut pas lancer tout le projet.

### Terminal 1 - PostgreSQL

Depuis la racine du projet:

docker compose up -d postgres

### Terminal 2 - Backend FastAPI

cd ~/devops-as-a-chat
cp .env.example .env
cd devops_api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Verifier le backend:

curl http://localhost:8000/health

### Terminal 3 - Frontend React

cd ~/devops-as-a-chat/frontend
npm install
npm run dev

Ouvrir:

http://localhost:5173

## 7. Si Node.js est trop ancien

Si `npm run dev` affiche une erreur Vite ou `crypto.hash`, utiliser Node.js 22 avec `nvm`:

source ~/.nvm/nvm.sh
nvm install 22
nvm use 22
cd ~/devops-as-a-chat/frontend
npm install
npm run dev

## 8. Configuration AWS pour la demo

Dans l'interface DAC:

1. Creer un compte ou se connecter.
2. Aller dans l'onboarding AWS.
3. Renseigner une Access Key, une Secret Key et une region.
4. Revenir dans le chat DAC.

Tester dans le chat:

cree une instance EC2 Ubuntu

Puis:

AWS Ubuntu 22.04 t3.micro eu-west-1

Puis confirmer:

ok

Lister les ressources:

liste des ressources

Supprimer une ressource:

supprimer mon instance

## 9. Generer les secrets du `.env`

Pour le detail de chaque variable, voir [variables-environnement.md](variables-environnement.md).

Generer `SECRET_KEY`, `FERNET_KEY` et `FERNET_SECRET` en une commande:

python3 - <<'PY'
import secrets
from cryptography.fernet import Fernet

print("SECRET_KEY=" + secrets.token_urlsafe(64))
fernet_key = Fernet.generate_key().decode()
print("FERNET_KEY=" + fernet_key)
print("FERNET_SECRET=" + fernet_key)
PY

Copier les valeurs generees dans `.env`.

Important:

- ne committez jamais votre fichier `.env`;
- gardez la meme cle Fernet tant que vous utilisez la meme base de donnees;
- si vous changez `SECRET_KEY`, les utilisateurs devront se reconnecter;
- si vous changez `FERNET_KEY`, les anciennes donnees chiffrees ne pourront plus etre dechiffrees.

## 10. Erreurs frequentes

### Le port 8000 est deja utilise

Voir le processus qui utilise le port:

sudo lsof -i :8000

Arreter proprement le processus si vous savez que c'est un ancien backend DAC:

kill <PID>

### Le port 5173 est deja utilise

Voir le processus:

sudo lsof -i :5173

Arreter proprement le processus si c'est un ancien frontend DAC:

kill <PID>

### AWS refuse Terraform

Si le chat affiche `InvalidClientTokenId`, les credentials AWS sont invalides ou expires.

Solution:

1. Retourner dans l'onboarding AWS.
2. Enregistrer de nouvelles cles.
3. Relancer la demande dans le chat.

### Cle Fernet invalide ou manquante

Erreur possible:

ERR FERNET_KEY non defini dans l'environnement.

Solution:

1. Generer les secrets avec la commande de la section 9.
2. Ajouter `SECRET_KEY`, `FERNET_KEY` et `FERNET_SECRET` dans `.env`.
3. Redemarrer le backend.

## 11. Commandes de verification pour developpeurs

Verifier le backend Python:

cd ~/devops-as-a-chat/devops_api
source .venv/bin/activate
python3 -m compileall app

Verifier le frontend:

cd ~/devops-as-a-chat/frontend
npm run build

Verifier Docker Compose:

cd ~/devops-as-a-chat
docker compose config
