FROM python:3.12-slim

ARG TERRAFORM_VERSION=1.6.6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip openssh-client git \
    && curl -fsSL -o /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    && unzip /tmp/terraform.zip -d /usr/local/bin \
    && rm -f /tmp/terraform.zip \
    && terraform -version \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python -c \"import importlib,pkgutil; from app.database import Base, engine; import app.models as m; [importlib.import_module(f'{m.__name__}.{n}') for _, n, _ in pkgutil.iter_modules(m.__path__)]; Base.metadata.create_all(bind=engine)\" && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
