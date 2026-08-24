# Variables d'environnement DAC

Ce document explique le fichier `.env` du projet DAC CodeCamp ETNA 2026.

Le fichier officiel est a la racine du projet:

.env

Il est cree a partir du modele:

cp .env.example .env

Le meme `.env` est utilise par Docker Compose et par le backend FastAPI, meme si le backend est lance depuis le dossier `devops_api`.

Important: ne jamais commit le fichier `.env`.

## 1. Pourquoi un fichier `.env` ?

Le fichier `.env` sert a configurer le projet sans mettre de secrets dans le code.

Il contient par exemple:

- l'URL de la base PostgreSQL;
- la cle de signature JWT;
- la cle Fernet pour chiffrer les secrets en base;
- le mode IA, mock ou OpenAI;
- les URLs du backend et du frontend;
- les limites pedagogiques du mode CodeCamp.

## 2. Generer les secrets principaux

Deux valeurs doivent etre generees localement:

- `SECRET_KEY` pour signer les tokens de connexion;
- `FERNET_KEY` pour chiffrer les donnees sensibles en base.

Commande recommandee:

python3 - <<'PY'
import secrets
from cryptography.fernet import Fernet

print("SECRET_KEY=" + secrets.token_urlsafe(64))
fernet_key = Fernet.generate_key().decode()
print("FERNET_KEY=" + fernet_key)
print("FERNET_SECRET=" + fernet_key)
PY

Copier ensuite les trois lignes dans `.env`.

## 3. Variables CodeCamp

### `DAC_ENV`

Exemple:

DAC_ENV=development

Role: indique l'environnement d'execution.

Pour les etudiants, garder:

DAC_ENV=development

### `DAC_SCHOOL_MODE`

Exemple:

DAC_SCHOOL_MODE=true

Role: active les garde-fous pedagogiques du CodeCamp.

Ce mode limite le perimetre de demonstration et evite certaines actions trop larges.

Pour les etudiants, garder:

DAC_SCHOOL_MODE=true

### `DAC_SCHOOL_MAX_INSTANCES`

Exemple:

DAC_SCHOOL_MAX_INSTANCES=1

Role: limite le nombre de VM creees dans le parcours ecole.

Pour eviter les couts AWS, garder:

DAC_SCHOOL_MAX_INSTANCES=1

### `DAC_LOG_LEVEL`

Exemple:

DAC_LOG_LEVEL=debug

Role: niveau de logs souhaite.

Pour apprendre et diagnostiquer, `debug` est utile.

## 4. Variables backend

### `BACKEND_BASE_URL`

Exemple Docker:

BACKEND_BASE_URL=http://backend:8000

Role: URL interne utilisee par le backend quand il doit s'appeler lui-meme dans Docker.

Avec Docker, garder:

BACKEND_BASE_URL=http://backend:8000

En lancement manuel local, utiliser plutot:

BACKEND_BASE_URL=http://localhost:8000

### `FRONTEND_BASE_URL`

Exemple:

FRONTEND_BASE_URL=http://localhost:5173

Role: URL du frontend React.

Pour les etudiants, garder:

FRONTEND_BASE_URL=http://localhost:5173

### `DATABASE_URL`

Exemple Docker:

DATABASE_URL=postgresql://dac:dac@postgres:5432/devops_api_db

Role: indique au backend comment se connecter a PostgreSQL.

Avec Docker, garder:

DATABASE_URL=postgresql://dac:dac@postgres:5432/devops_api_db

En PostgreSQL local, adapter:

DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/devops_api_db

## 5. Authentification

### `SECRET_KEY`

Role: cle utilisee pour signer les tokens JWT de connexion.

Quand un utilisateur se connecte, le backend cree un token signe avec `SECRET_KEY`. A chaque requete protegee, le backend verifie ce token avec la meme cle.

Generation: utiliser la commande de la section 2.

Exemple dans `.env`:

SECRET_KEY=valeur_generee

Important:

- ne jamais commit une vraie `SECRET_KEY`;
- si la valeur change, les utilisateurs devront se reconnecter;
- ne pas utiliser `change-this-secret-key-for-local-dev` en production.

### `ALGORITHM`

Exemple:

ALGORITHM=HS256

Role: algorithme utilise pour signer les tokens JWT.

Pour les etudiants, garder:

ALGORITHM=HS256

### `ACCESS_TOKEN_EXPIRE_MINUTES`

Exemple:

ACCESS_TOKEN_EXPIRE_MINUTES=60

Role: duree de validite du token de connexion en minutes.

Pour les etudiants, garder:

ACCESS_TOKEN_EXPIRE_MINUTES=60

## 6. Chiffrement Fernet

### `FERNET_KEY`

Role: cle utilisee pour chiffrer et dechiffrer les donnees sensibles stockees en base.

Elle sert notamment pour:

- les secrets AWS;
- les credentials providers;
- les cles privees generees;
- certaines informations sensibles d'instances.

Generation: utiliser la commande de la section 2.

Exemple dans `.env`:

FERNET_KEY=valeur_generee

Important:

- garder la meme cle tant que vous utilisez la meme base;
- si vous changez la cle, les anciennes donnees chiffrees ne pourront plus etre dechiffrees;
- ne jamais commit une vraie cle Fernet.

### `FERNET_SECRET`

Exemple:

FERNET_SECRET=meme_valeur_que_FERNET_KEY

Role: alias de compatibilite avec l'ancien code.

Dans le projet actuel, `FERNET_KEY` est la variable principale. Pour eviter toute confusion, mettez la meme valeur dans `FERNET_SECRET`.

## 7. IA OpenAI ou mode mock

### `DAC_AI_PROVIDER`

Sans cle OpenAI:

DAC_AI_PROVIDER=mock

Avec OpenAI:

DAC_AI_PROVIDER=openai

Role: choisit le mode IA.

Le mode `mock` permet de lancer DAC sans cle OpenAI. Les workflows applicatifs continuent d'utiliser les regles et les fallbacks du projet.

### `OPENAI_API_KEY`

Sans OpenAI:

OPENAI_API_KEY=

Avec OpenAI:

OPENAI_API_KEY=sk-...

Role: cle API OpenAI utilisee par le backend pour les fonctions IA avancees.

Important:

- ne jamais commit cette cle;
- chaque groupe doit utiliser sa propre cle si le challenge IA le demande;
- le frontend ne doit jamais appeler OpenAI directement.

### `DAC_AI_MODEL`

Exemple:

DAC_AI_MODEL=gpt-4o-mini

Role: modele IA utilise quand `DAC_AI_PROVIDER=openai`.

Modele conseille pour les etudiants:

DAC_AI_MODEL=gpt-4o-mini

## 8. Frontend Vite

### `VITE_API_URL`

Exemple:

VITE_API_URL=http://localhost:8000

Role: URL du backend appelee par le frontend React.

Pour les etudiants, garder:

VITE_API_URL=http://localhost:8000

### `VITE_NODE_ENV`

Exemple:

VITE_NODE_ENV=development

Role: indique l'environnement frontend.

Pour les etudiants, garder:

VITE_NODE_ENV=development

## 9. Exemple `.env` minimal pour Docker

DAC_ENV=development
DAC_SCHOOL_MODE=true
DAC_SCHOOL_MAX_INSTANCES=1
DAC_LOG_LEVEL=debug

BACKEND_BASE_URL=http://backend:8000
FRONTEND_BASE_URL=http://localhost:5173
DATABASE_URL=postgresql://dac:dac@postgres:5432/devops_api_db

SECRET_KEY=GENERER_AVEC_SECRETS_TOKEN_URLSAFE
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

FERNET_KEY=GENERER_AVEC_FERNET
FERNET_SECRET=MEME_VALEUR_QUE_FERNET_KEY

OPENAI_API_KEY=
DAC_AI_PROVIDER=mock
DAC_AI_MODEL=gpt-4o-mini

VITE_API_URL=http://localhost:8000
VITE_NODE_ENV=development

## 10. Checklist avant de lancer

Avant de lancer le projet, verifier:

git status

Le fichier `.env` ne doit pas apparaitre comme fichier a commiter.

Verifier aussi:

cat .env

Vous devez avoir au minimum:

- `SECRET_KEY` generee;
- `FERNET_KEY` generee;
- `DATABASE_URL` correcte;
- `DAC_AI_PROVIDER=mock` si vous n'avez pas de cle OpenAI.

## 11. Erreurs frequentes

### `ERR FERNET_KEY non defini`

Cause: `FERNET_KEY` manque dans `.env`.

Solution: generer une cle Fernet et redemarrer le backend.

### Token invalide apres changement de `SECRET_KEY`

Cause: les anciens tokens JWT ont ete signes avec l'ancienne cle.

Solution: se deconnecter et se reconnecter.

### OpenAI ne repond pas

Causes possibles:

- `DAC_AI_PROVIDER=mock`;
- `OPENAI_API_KEY` vide;
- cle OpenAI invalide;
- modele mal configure.

Solution pour utiliser OpenAI:

DAC_AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
DAC_AI_MODEL=gpt-4o-mini

Puis redemarrer le backend.
