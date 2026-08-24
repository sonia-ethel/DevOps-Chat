# app/services/terraform_service.py
import logging
logger = logging.getLogger(__name__)

import uuid
import os
import json
import re
from datetime import datetime
from sqlalchemy.orm import Session

from app.services.execution_logger import log_execution_event
from app.models import Execution, Session as UserSession, Provider, GeneratedTerraformFile
from app.services.parse_instance_result import parse_instance_result
from app.utils.crypto import decrypt
from app.utils.file_utils import create_and_store_terraform_file  # pour compat si on génère ici
from app.utils.extra_data_utils import get_extra, set_extra
from app.security.safe_subprocess import run_safe_command, CommandResult
from app.services.aws_credentials_service import validate_aws_credentials

#  Import du module (on gère le fallback si certaines fonctions sont absentes)
import app.services.terraform_validator as tf_validator


# 
# Option utilitaire : générer et persister un fichier Terraform
# 
async def generate_terraform_file(
    instructions: str,
    username: str,
    session_id: int,
    db: Session,
    user_id: int
) -> GeneratedTerraformFile:
    """
    Génère un fichier Terraform via la couche file_utils (arbo lisible):
      generated/<user>/<YYYY-MM-DD>/s<session>/terraform/<filename>.tf
    """
    logger.info(" [Terraform] Génération du fichier Terraform (service helper)...")

    terraform_code = (instructions or "").strip()
    safe_username = (username or "user").replace("@", "_").replace(".", "_")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    short_uuid = str(uuid.uuid4())[:6]
    filename = f"tf_{safe_username}_s{session_id}_{timestamp}_{short_uuid}.tf"

    tf_file = create_and_store_terraform_file(
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        content=terraform_code,
        ssh_user="ubuntu",
        base_name="vm"
    )
    logger.info(" [Terraform] Fichier créé: %s", tf_file.file_path)
    return tf_file


# 
# Exécution Terraform
# 
async def run_terraform(
    file_id: str,
    db: Session,
    execution_id: int,
    user_id: int,
    progress_callback=None
) -> dict:
    """
    Exécute Terraform sur un fichier déjà persisté.
    - Workspace d’exécution: dossier caché juste à côté du .tf (ex: .exec_<id>)
    - Charge les credentials provider (AWS/Azure/GCP) dans l'env
    - Plan / Apply avec logs et progression (callback optionnel)
    - Parse des outputs + enregistrement des instances via parse_instance_result
    """
    logger.info(" [Terraform] Lancement d'une exécution Terraform...")

    # Import paresseux pour éviter dépendances circulaires
    try:
        from app.services.task_manager import TaskManager  # utilisé pour progress parsing/hints
    except Exception:
        TaskManager = None  # fallback

    def report_progress(step_name: str, message: str, progress: float | None = None,
                        level: str = "info", **kwargs):
        if progress_callback:
            substeps = None
            estimated_duration = None
            if TaskManager:
                try:
                    substeps = TaskManager.create_aws_deployment_substeps(progress or 0)
                except Exception:
                    substeps = None
                try:
                    estimated_duration = TaskManager.estimate_remaining_time(step_name, progress or 0)
                except Exception:
                    estimated_duration = None

            progress_callback(
                step_name, message, progress, level,
                substeps=substeps, estimated_duration=estimated_duration, **kwargs
            )
        logger.info(f"[{step_name}] {message}")

    report_progress("terraform_init", " Initialisation de l'exécution Terraform", 5.0)

    file_id = str(file_id)

    terraform_file = (
        db.query(GeneratedTerraformFile)
        .filter_by(id=file_id, user_id=user_id)
        .first()
    )
    if not terraform_file or not os.path.exists(terraform_file.file_path):
        msg = f"Fichier Terraform introuvable pour ID {file_id}."
        report_progress("terraform_error", f" {msg}", level="error")
        raise Exception(msg)

    tf_file = terraform_file.file_path
    report_progress("terraform_file_loaded", f" Fichier Terraform chargé: {os.path.basename(tf_file)}", 10.0)

    # Workspace local à côté du fichier
    tf_dir = os.path.dirname(tf_file)
    exec_dir = os.path.join(tf_dir, f".exec_{file_id}")
    os.makedirs(exec_dir, exist_ok=True)
    report_progress("terraform_workspace", f" Workspace: {exec_dir}", 15.0)

    # Copie en main.tf
    with open(tf_file, "r", encoding="utf-8") as f:
        tf_content = f.read()
    target_tf = os.path.join(exec_dir, "main.tf")
    with open(target_tf, "w", encoding="utf-8", newline="\n") as f:
        f.write((tf_content or "").rstrip() + "\n")

    logs: dict[str, str | dict] = {}

    # ENV vars dynamiques selon provider
    env = os.environ.copy()
    env["PATH"] = os.environ.get("PATH", "")
    env["TF_IN_AUTOMATION"] = "1"
    env["TF_CLI_ARGS"] = "-no-color"
    env["TF_CLI_ARGS_plan"] = "-no-color -input=false"
    env["TF_CLI_ARGS_apply"] = "-no-color -input=false -auto-approve"

    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise Exception("Exécution introuvable.")
    session = db.query(UserSession).filter(UserSession.id == execution.session_id).first()
    if not session:
        raise Exception("Session introuvable pour cette exécution.")

    provider = (
        db.query(Provider)
        .filter(Provider.user_id == user_id, Provider.session_id == session.id)
        .order_by(Provider.created_at.desc())
        .first()
    )
    if not provider:
        raise Exception("Aucun provider trouvé pour cette session.")

    decrypted_credentials = json.loads(decrypt(provider.encrypted_credentials))
    provider_type = (provider.provider_name or "").lower()

    redacted_preview = {"provider": provider_type}
    if provider_type == "aws":
        env["AWS_ACCESS_KEY_ID"] = decrypted_credentials.get("AWS_ACCESS_KEY_ID", "")
        env["AWS_SECRET_ACCESS_KEY"] = decrypted_credentials.get("AWS_SECRET_ACCESS_KEY", "")
        env["AWS_DEFAULT_REGION"] = decrypted_credentials.get("region", "eu-west-1")
        valid_aws, aws_validation = validate_aws_credentials(decrypted_credentials)
        if not valid_aws:
            raise Exception(aws_validation.get("message", "Credentials AWS invalides."))
        redacted_preview["region"] = env["AWS_DEFAULT_REGION"]
        redacted_preview["access_key_id"] = (env["AWS_ACCESS_KEY_ID"][:6] + "...") if env["AWS_ACCESS_KEY_ID"] else ""
        redacted_preview["account_id"] = aws_validation.get("account_id", "")
    elif provider_type == "azure":
        env["ARM_CLIENT_ID"] = decrypted_credentials.get("client_id", "")
        env["ARM_CLIENT_SECRET"] = decrypted_credentials.get("client_secret", "")
        env["ARM_SUBSCRIPTION_ID"] = decrypted_credentials.get("subscription_id", "")
        env["ARM_TENANT_ID"] = decrypted_credentials.get("tenant_id", "")
        redacted_preview["subscription_id"] = (env["ARM_SUBSCRIPTION_ID"][:6] + "...") if env["ARM_SUBSCRIPTION_ID"] else ""
    elif provider_type in {"gcp", "google"}:
        gcp_json = json.dumps(decrypted_credentials)
        gcp_cred_file = os.path.join(exec_dir, "gcp_credentials.json")
        with open(gcp_cred_file, "w", encoding="utf-8") as f:
            f.write(gcp_json)
        env["GOOGLE_CLOUD_KEYFILE_JSON"] = gcp_cred_file
        redacted_preview["keyfile"] = gcp_cred_file
        provider_type = "google"
    else:
        raise Exception(f"Provider non supporté : {provider_type}")

    logger.info(" [Terraform] Contexte (redacté) : %s", json.dumps(redacted_preview))

    #  Sauvegarde du provider (et région si AWS) dans extra_data pour le parseur
    try:
        extra = get_extra(execution)
        extra["provider"] = provider_type
        if provider_type == "aws":
            extra.setdefault("region", env.get("AWS_DEFAULT_REGION"))
        set_extra(execution, extra)
        db.commit()
    except Exception:
        logger.warning("Impossible de persister provider/region dans execution.extra_data")

    def run_cmd(cmd: list[str], label: str) -> CommandResult:
        logger.info(f" [Terraform]  {label} : {' '.join(cmd)}")
        result = run_safe_command(cmd, cwd=exec_dir, env=env, timeout_seconds=900)
        out = result.stdout.strip()
        err = result.stderr.strip()
        logs[label] = (out + ("\n" + err if err else "")).strip()
        if out:
            logger.info(f" [Terraform] {label} stdout:\n{out}")
        if err:
            logger.info(f" [Terraform] {label} stderr:\n{err}")
        if result.returncode != 0:
            logger.info(f" [Terraform] Échec '{label}' (rc={result.returncode})")
            raise Exception(f"Erreur '{label}': {(err or out).strip()}")
        logger.info(f" [Terraform] {label} OK")
        return result

    # Log démarrage exécution
    log_execution_event(
        db=db,
        execution_id=execution_id,
        user_id=user_id,
        event="start",
        message="Démarrage de l'exécution Terraform.",
        log_content="initialisation"
    )

    # Étape 1 : validation (fonction si dispo, sinon fallback CLI)
    report_progress("terraform_validation", " Validation de la syntaxe Terraform", 20.0)
    validator_func = getattr(tf_validator, "validate_terraform_file", None)
    if callable(validator_func):
        validator_func(target_tf)
        report_progress("terraform_validation_complete", " Syntaxe Terraform validée", 25.0)
    else:
        report_progress("terraform_validation_fallback", " Validation par CLI Terraform", 22.0)
        init_result = run_safe_command(
            ["terraform", "init", "-backend=false", "-no-color"],
            cwd=exec_dir, env=env, timeout_seconds=900
        )
        if init_result.returncode != 0:
            raise Exception(f"Terraform init (validate) failed:\n{(init_result.stderr or init_result.stdout)}")
        val_result = run_safe_command(
            ["terraform", "validate", "-no-color"],
            cwd=exec_dir, env=env, timeout_seconds=900
        )
        if val_result.returncode != 0:
            raise Exception(f"Terraform validate failed:\n{(val_result.stderr or val_result.stdout)}")

    try:
        # Version
        report_progress("terraform_version", " Vérification de la version Terraform", 30.0)
        run_cmd(["terraform", "version"], "version")

        # Init
        report_progress("terraform_init_start", " Initialisation du workspace Terraform", 40.0)
        run_cmd(["terraform", "init", "-reconfigure", "-no-color"], "init")
        report_progress("terraform_init_complete", " Terraform initialisé", 50.0)

        # Plan
        report_progress("terraform_plan_start", " Génération du plan d'exécution", 60.0)
        run_cmd(["terraform", "plan", "-no-color", "-input=false"], "plan")
        report_progress("terraform_plan_complete", " Plan généré", 70.0)

        # Apply (flux temps réel)
        report_progress("terraform_apply_start", " Déploiement de l'infrastructure", 75.0)
        logger.info(" [Terraform]  apply : terraform apply -no-color -input=false -auto-approve")

        apply_result = run_safe_command(
            ["terraform", "apply", "-no-color", "-input=false", "-auto-approve"],
            cwd=exec_dir, env=env, timeout_seconds=1800
        )

        apply_output = apply_result.stdout
        apply_output_lines = apply_output.split("\n") if apply_output else []
        resources_created = 0
        current_apply_progress = 75.0

        for line in apply_output_lines:
            if not line:
                continue
            s = line.strip()

            # Progress parsing (si TaskManager dispo)
            if TaskManager and hasattr(TaskManager, "parse_terraform_output_for_progress"):
                try:
                    info = TaskManager.parse_terraform_output_for_progress(s)
                except Exception:
                    info = None
            else:
                info = None

            if info:
                action = info.get("action")
                if action == "creating":
                    report_progress(
                        "terraform_resource_creating",
                        f" Création: {info.get('resource_type')} '{info.get('resource_name')}'",
                        current_apply_progress,
                        resource_info=info
                    )
                elif action == "created":
                    resources_created += 1
                    current_apply_progress = min(90.0, 75.0 + (resources_created * 3))
                    report_progress(
                        "terraform_resource_created",
                        f" Ressource créée: {info.get('resource_type')} '{info.get('resource_name')}'",
                        current_apply_progress,
                        level="success",
                        resource_info=info
                    )
                elif action in ("modifying", "destroying"):
                    report_progress(
                        f"terraform_resource_{action}",
                        f" {action.title()}: {info.get('resource_type')} '{info.get('resource_name')}'",
                        current_apply_progress,
                        resource_info=info
                    )

        logs["apply"] = apply_output

        if apply_result.returncode != 0:
            raise Exception(f"Erreur 'apply': {apply_output}")

        report_progress("terraform_apply_complete",
                        f" Infrastructure déployée ({resources_created} ressources)", 90.0)

    except Exception as e:
        log_execution_event(
            db=db,
            execution_id=execution_id,
            user_id=user_id,
            event="failed",
            message=str(e),
            log_content={"error": str(e), "logs": logs}
        )
        raise

    # Résumé "Apply complete! Resources: X added, Y changed, Z destroyed."
    m = re.search(
        r"Apply complete!\s*Resources:\s*([0-9]+)\s*added,\s*([0-9]+)\s*changed,\s*([0-9]+)\s*destroyed\.",
        apply_output or logs.get("apply", "")
    )
    if m:
        added, changed, destroyed = m.groups()
        summary = f"Terraform Résumé : {added} créé(s), {changed} modifié(s), {destroyed} supprimé(s)."
    else:
        summary = "Terraform Résumé indisponible."
    logger.info(" [Terraform] %s", summary)

    # Outputs (JSON)
    report_progress("terraform_outputs", " Extraction des outputs", 95.0)
    out_proc = run_cmd(["terraform", "output", "-json"], "output")

    try:
        outputs = json.loads(out_proc.stdout or "{}")
    except json.JSONDecodeError:
        outputs = {}
    logs["output"] = outputs

    report_progress("terraform_parsing", " Analyse des ressources créées", 98.0)

    # Log fin OK
    log_execution_event(
        db=db,
        execution_id=execution_id,
        user_id=user_id,
        event="completed",
        message="Terraform exécuté avec succès.",
        log_content={"summary": summary, "logs": logs}
    )

    # Valeurs “premier élément” (compat anciennes UIs)
    public_ip = None
    instance_id = None

    def extract_value(val):
        if isinstance(val, dict):
            val = val.get("value")
        if isinstance(val, list) and val:
            return val[0]
        return val

    for k, v in outputs.items():
        if not isinstance(v, dict):
            continue
        key = (k or "").lower()
        if public_ip is None and ("ip" in key or "address" in key):
            public_ip = extract_value(v)
        if instance_id is None and ("id" in key or "instance" in key):
            instance_id = extract_value(v)

    logger.info(f" IP publique détectée : {public_ip}")
    logger.info(f" Instance ID détecté : {instance_id}")

    # Enregistrement des instances en base depuis les outputs
    extra_data = get_extra(execution)
    ssh_user = extra_data.get("ssh_user")

    #  Récupération du contenu de la clé privée :
    # 1) si extra_data.ssh_private_key (chiffrée) existe -> déchiffrer
    # 2) sinon, si extra_data.private_key_path pointe vers un fichier -> lire son contenu
    ssh_private_key = extra_data.get("ssh_private_key")
    if ssh_private_key:
        try:
            ssh_private_key = decrypt(ssh_private_key)
        except Exception:
            # si ce n'est pas chiffré, on garde tel quel
            pass
    if not ssh_private_key:
        pk_path = extra_data.get("private_key_path")
        if pk_path and os.path.exists(pk_path):
            try:
                with open(pk_path, "r", encoding="utf-8") as f:
                    ssh_private_key = f.read()
            except Exception as e:
                logger.warning(f"Impossible de lire la clé privée à {pk_path}: {e}")
                ssh_private_key = None

    logger.info(" [Terraform] Apply success! Outputs keys: %s", list(outputs.keys()))
    logger.info(" [Terraform] Outputs parsed: %s", json.dumps(outputs, indent=2)[:500])
    
    try:
        if session:
            logger.info(" [DB] Début enregistrement instances (session_id=%s)", session.id)
            parse_instance_result(
                db=db,
                execution=execution,
                terraform_outputs=outputs,
                session=session,
                ssh_user=ssh_user,
                private_key=ssh_private_key
            )
            logger.info(" [DB] Instances enregistrées avec succès.")
        else:
            logger.warning(" [DB] Session introuvable, pas d'enregistrement d'instances.")
    except Exception as e:
        logger.error(f" [DB] ERREUR lors de l'enregistrement des instances : {e}", exc_info=True)
        raise

    # Fin
    report_progress(
        "terraform_complete",
        f" Terraform terminé ! IP: {public_ip or 'N/A'}",
        100.0,
        level="success"
    )
    logger.info(" [Terraform] Fin complète de l'exécution.")

    return {
        "logs": logs,
        "summary": summary,
        "instances": [
            {
                "instance_id": instance_id,
                "public_ip": public_ip
            }
        ]
    }
