# Backend DAC

Backend FastAPI du MVP CodeCamp ETNA 2026.

## Demarrage local

Depuis `devops_api/`:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Variables principales dans `.env`:

- `DATABASE_URL`
- `SECRET_KEY`
- `FERNET_KEY`
- `FERNET_SECRET`
- `BACKEND_BASE_URL`
- `FRONTEND_BASE_URL`

## Routes utiles

- `/auth/*`: authentification.
- `/user/aws-credentials`: onboarding AWS.
- `/chat_creation/chat_message`: chat DAC principal.
- `/generate`: generation Terraform.
- `/executions/*`: execution.
- `/resources/*`: inventaire et suppression.

Les routes dev/test/admin/Kubernetes/plans historiques ont ete archivees pour simplifier le MVP etudiant.
