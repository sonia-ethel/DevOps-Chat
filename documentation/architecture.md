# Architecture MVP CodeCamp

## Vue simple

React frontend
  -> FastAPI backend
    -> detection intention
    -> generation Terraform
    -> execution Terraform
    -> sauvegarde DB
    -> retour chat / inventaire

## Backend actif

Le backend part de `devops_api/app/main.py`.

Routers principaux:

- `auth_routes`: register/login/me.
- `user_credentials_routes`: sauvegarde et statut credentials AWS.
- `chat_creation_routes`: route DAC principale.
- `chat_metadata_routes`: creation, liste et messages des chats.
- `generate_routes` et `generate_terraform`: generation Terraform.
- `executions_routes`: execution d'une action.
- `resource_routes`: liste et suppression des ressources.
- `async_tasks_routes`: suivi des taches longues.
- `dashboard_routes`: vues dashboard.

## Frontend actif

Le frontend part de `frontend/src/App.tsx`.

Pages montees:

- `/`
- `/auth`
- `/register`
- `/dashboard`
- `/chat`
- `/onboarding/aws`
- `/resources`
- `/settings`
- `/profile`

## Decisions de nettoyage

- Les anciennes routes dev/test/admin/Kubernetes/plans ont ete retirees du rendu etudiant.
- Les anciens scripts de reset DB et tests E2E ont ete retires du rendu etudiant.
- Le MVP garde un seul moteur de chat actif: `/chat_creation/chat_message`.
- Docker utilise PostgreSQL, un backend FastAPI avec Terraform CLI, et un frontend Nginx.

## Risques connus

- Les migrations Alembic historiques ne reconstruisent pas une DB neuve complete; Docker cree les tables via SQLAlchemy au demarrage.
- Les actions AWS peuvent generer des couts: utiliser un compte sandbox et supprimer les ressources apres demo.
