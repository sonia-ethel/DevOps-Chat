# Instructions for DevOps-as-a-Chat (DAC)

## Project Overview

- **DevOps-as-a-Chat (DAC)** automates cloud infrastructure via natural language, converting user prompts into Terraform/Ansible code and executing on AWS. The stack is **FastAPI (Python)** backend, **React 19** frontend, PostgreSQL, and deep OpenAI GPT-4o integration.
- **SSM-first**: All VM operations use AWS Systems Manager (SSM) by default; Ansible is fallback only after SSM failure and explicit confirmation.

## Architecture & Data Flow

- **Frontend**: React 19 (Material-UI, TailwindCSS) → REST API (Axios)
- **Backend**: FastAPI (20+ route files, 10+ services, 25+ SQLAlchemy models)
- **Infra**: Terraform/Ansible code is generated and executed based on intent detection (GPT-4o)
- **Database**: PostgreSQL (with Alembic migrations)
- **External**: OpenAI API, AWS (EC2, VPC, IAM), Stripe for billing

## Key Workflows

- **Backend**: Run with `uvicorn devops_api.main:app --reload` (see devops_api/README.md)
- **Frontend**: Start with `npm run dev` in `frontend/`
- **DB Migrations**: Use Alembic (`alembic upgrade head`) for schema changes
- **Security**: P0 patches (see docs/setup/SECURITY.md) are enforced (rate limiting, audit logging, subprocess allowlist, idempotency)
- **Testing**: Run Python tests in `devops_api/tests/` and E2E in `tests_e2e/`

## Conventions & Patterns

- **Intent Routing**: All user actions flow through `/intents/create_from_prompt` → `/generate` → `/executions/create`/`/execute`
- **Resource Management**: Prefer SSM for AWS resource ops; only use Ansible if SSM fails
- **Frontend**: Chat UI is guided mode only (no "free_chat"). See `frontend/src/components/Chat/README.md` for state logic and design system
- **AWS Panel**: Use `AWSResourcePanel` for real-time instance management (see `frontend/src/components/AWS/README.md`)
- **Naming**: Use English for code, French for UI/UX and docs
- **Sensitive Data**: Never log secrets; use Fernet/JWT for auth

## Integration Points

- **OpenAI**: All intent detection and code generation
- **AWS**: Resource CRUD via Boto3, SSM, and REST endpoints
- **Stripe**: Billing integration (see docs/setup/STRIPE_SETUP.md)

## References

- **docs/architecture/**: System, data flow, state machine, API routes
- **devops_api/README.md**: Backend setup, key commands
- **frontend/README.md**: Frontend setup, linting, and build
- **docs/guides/**: Quick start, AWS setup, development
- **docs/setup/SECURITY.md**: Security requirements

---

> For more, see [docs/README.md](../docs/README.md) and [docs/architecture/](../docs/architecture/)
