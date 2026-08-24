import logging

from app.paths import K8S_DIR
logger = logging.getLogger(__name__)

import os
import uuid
import yaml
import re
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.execution_log import ExecutionLog
from app.security.safe_subprocess import run_safe_command

BASE_DIR = K8S_DIR

def validate_kubernetes_manifest(yaml_code: str) -> str:
    """
    Valide et nettoie un manifest Kubernetes YAML :
    - Retire les ```yaml éventuels
    - Valide la structure YAML
    - Vérifie la présence des champs obligatoires
    - Normalise les indentations et la syntaxe
    - Retourne le YAML propre
    """
    logger.info(" [K8s] Validation du manifest Kubernetes...")
    cleaned_content = yaml_code.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = re.sub(r"^```(yaml)?", "", cleaned_content, flags=re.IGNORECASE).strip()
        cleaned_content = re.sub(r"```$", "", cleaned_content).strip()

    try:
        documents = list(yaml.safe_load_all(cleaned_content))
    except yaml.YAMLError as e:
        raise ValueError(f"Le YAML Kubernetes est invalide : {str(e)}")

    if not documents or not isinstance(documents, list):
        raise ValueError("Le manifest doit contenir au moins un document YAML.")

    cleaned_docs = []
    for idx, doc in enumerate(documents):
        if not isinstance(doc, dict):
            raise ValueError(f"Le document #{idx+1} doit être un dictionnaire YAML.")

        if "apiVersion" not in doc:
            raise ValueError(f"Le document #{idx+1} doit contenir 'apiVersion'.")
        if not isinstance(doc["apiVersion"], str):
            raise ValueError(f"Le champ 'apiVersion' du document #{idx+1} doit être une chaîne.")

        if "kind" not in doc:
            raise ValueError(f"Le document #{idx+1} doit contenir 'kind'.")
        if not isinstance(doc["kind"], str):
            raise ValueError(f"Le champ 'kind' du document #{idx+1} doit être une chaîne.")

        metadata = doc.get("metadata")
        if not metadata or not isinstance(metadata, dict):
            raise ValueError(f"Le document #{idx+1} doit contenir un bloc 'metadata'.")
        if "name" not in metadata:
            raise ValueError(f"Le bloc 'metadata' du document #{idx+1} doit contenir 'name'.")

        if "spec" not in doc:
            raise ValueError(f"Le document #{idx+1} doit contenir un bloc 'spec'.")

        cleaned_docs.append(doc)

    serialized = "---\n".join(
        yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True).strip()
        for doc in cleaned_docs
    )

    logger.info("[K8s] Manifest validé avec succès.")
    return serialized


async def generate_kubernetes_manifest(yaml_code: str) -> str:
    """
    Valide et sauvegarde le manifest Kubernetes dans un fichier.
    Retourne le chemin du manifest.
    """
    logger.info(" [K8s] Génération du manifest Kubernetes...")
    os.makedirs(BASE_DIR, exist_ok=True)

    cleaned_yaml = validate_kubernetes_manifest(yaml_code)

    file_id = str(uuid.uuid4())
    manifest_path = os.path.join(BASE_DIR, f"{file_id}.yaml")

    with open(manifest_path, "w") as f:
        f.write(cleaned_yaml)

    logger.info(f"[K8s] Manifest sauvegardé : {manifest_path}")
    return manifest_path


async def deploy_kubernetes(
    manifest_path: str,
    db: Session,
    execution_id: int,
    user_id: int
) -> dict:
    """
    Applique un manifest Kubernetes avec kubectl apply.
    Journalise les logs.
    """
    logger.info("[K8s] Kubernetes deployment started...")

    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Le manifest '{manifest_path}' n'existe pas.")

    logger.info(f" [K8s] Manifest trouvé : {manifest_path}")

    db.add(
        ExecutionLog(
            execution_id=execution_id,
            user_id=user_id,
            log_type="started",
            content=f"Déploiement Kubernetes démarré avec {manifest_path}",
            timestamp=datetime.now(timezone.utc)
        )
    )
    db.commit()

    cmd = [
        "kubectl", "apply",
        "-f", manifest_path
    ]

    logger.info(f"[K8s] Command: {' '.join(cmd)}")

    result = run_safe_command(cmd, timeout_seconds=900)

    if result.returncode != 0:
        logger.info("[K8s] Erreur kubectl.")
        db.add(
            ExecutionLog(
                execution_id=execution_id,
                user_id=user_id,
                log_type="failed",
                content=result.stderr,
                timestamp=datetime.now(timezone.utc)
            )
        )
        db.commit()
        raise Exception(f"Erreur Kubernetes:\n{result.stderr}")

    logger.info("[K8s] kubectl apply réussi.")
    db.add(
        ExecutionLog(
            execution_id=execution_id,
            user_id=user_id,
            log_type="completed",
            content=result.stdout,
            timestamp=datetime.now(timezone.utc)
        )
    )
    db.commit()

    return {
        "logs": result.stdout,
        "summary": "Déploiement Kubernetes réussi."
    }
