# swagger_doc.py

from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI


def custom_openapi(app: FastAPI):
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="DevOps-as-a-Chat API",
        version="2.0.0",
        description="""
##  DevOps-as-a-Chat – API Documentation

Cette API vous permet de piloter automatiquement des infrastructures Cloud via **Terraform**, **Ansible**, **Kubernetes**, avec un chatbot intelligent, tout en gardant la traçabilité dans une base de données relationnelle.

---

###  Authentification
Toutes les routes principales nécessitent un token **JWT**. Veuillez :
1. Vous connecter via `/login`
2. Cliquer sur le bouton **Authorize ** dans Swagger
3. Coller le token dans le champ `Bearer <votre_token>`

---

###  Flux utilisateur standard

1. **Créer une session**  
   `POST /sessions/create`

2. **Ajouter un provider cloud (AWS, Azure, GCP)**  
   `POST /providers/create`

3. **Ajouter une intention (create/configure/audit/kubernetes)**  
   `POST /intents/create`

4. **Générer un fichier Terraform / Ansible / Kubernetes**  
   `POST /generate`

5. **Créer une exécution à partir du fichier généré**  
   `POST /executions/create`

6. **Lancer l'exécution (apply, playbook, audit)**  
   `POST /executions/{execution_id}/execute`

7. **Suivre les logs / consulter les résultats**  
   `GET /executions/{execution_id}`

---

###  Inventaire Ansible

- **Lister les instances prêtes** :  
  `GET /sessions/available-instances`

- **Générer un inventaire Ansible** :  
  `POST /inventories/generate`

---

###  Gestion des ressources

- **Lister toutes les instances créées**  
  `GET /list_resources?session_id=`

- **Supprimer une ou plusieurs instances du cloud**  
  `POST /delete_resource?session_id=...&instance_id=...`

---

###  Chat intelligent (optionnel)

- `POST /chat_message` : envoyer une requête au bot
- `POST /start_chat` : démarrer une session de chat
- `GET /get_messages` : récupérer les messages
- `POST /rename_chat` : renommer un chat
- `GET /list_chats` : voir l’historique

---

###  Gestion des intentions

- `POST /intents/create` : ajouter une intention
- `GET /intents/by_session/{session_id}` : lister les intentions par session

---

###  Providers cloud

- `POST /providers/create` : ajouter des credentials
- `GET /providers/for_session` : vérifier le provider d'une session
- `GET /providers/list` : lister tous les providers de l’utilisateur

---

###  Utilitaires (tests internes)

- `/test-utils/*` : pour développement et tests automatiques

---

###  Infos techniques

- Fichiers générés stockés dans `generated_files/`
- Chaque ressource créée est tracée dans une table SQL
- Les credentials sont **chiffrés** avec AES en base
- Support multi-cloud : AWS, Azure, GCP
- Compatible avec `Ansible`, `Terraform`, `Kubernetes`

---
        """,
        routes=app.routes,
    )

    app.openapi_schema = openapi_schema
    return app.openapi_schema

# À appeler dans main.py après avoir monté les routes :
# app.openapi = lambda: custom_openapi(app)
