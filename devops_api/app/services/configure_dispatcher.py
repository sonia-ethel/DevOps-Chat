# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

"""
Configure Dispatcher - Routage intelligent entre Installer Engine et configure_only
===================================================================================

Responsabilité:
    Analyser le texte de configuration et router vers:
    - InstallerEngine: si une app du catalogue est détectée (nginx, apache, docker, etc.)
    - handle_configure_only: sinon (fallback pour configurations génériques)

Intégration:
    Remplace tous les appels directs à handle_configure_only dans chat_creation_routes.py
"""

import json
import logging
import re
import time
from typing import List, Dict
from pathlib import Path
from fastapi import HTTPException

from app.services.installer_engine.installer_engine import (
    InstallerEngine,
    create_installation_request_from_text,
)
from app.services.installer_engine.installer_runner import InstallerRunner
from app.services.installer_engine.app_recipes import list_recipes
from app.services.ssm_executor import execute_via_ssm
from app.services.configure_only import handle_configure_only
from app import models

logger = logging.getLogger(__name__)


def _normalize_aws_creds(creds: Dict[str, str] | None) -> Dict[str, str] | None:
    if not creds:
        return None
    access_key = creds.get("AWS_ACCESS_KEY_ID") or creds.get("access_key_id")
    secret_key = creds.get("AWS_SECRET_ACCESS_KEY") or creds.get("secret_access_key")
    session_token = creds.get("AWS_SESSION_TOKEN") or creds.get("session_token")
    region = creds.get("AWS_DEFAULT_REGION") or creds.get("region") or "eu-north-1"

    normalized = {
        "AWS_ACCESS_KEY_ID": access_key,
        "AWS_SECRET_ACCESS_KEY": secret_key,
        "AWS_DEFAULT_REGION": region,
    }
    if session_token:
        normalized["AWS_SESSION_TOKEN"] = session_token

    # Backward-compat keys for existing configure_only usage
    normalized["access_key_id"] = access_key
    normalized["secret_access_key"] = secret_key
    normalized["region"] = region

    return normalized


def _extract_runner_json(stdout: str) -> dict | None:
    """
    Extrait le JSON du runner avec le marqueur DAC_RESULT_JSON:
    Utilise le même système que installer_runner.extract_dac_result_json
    """
    if not stdout:
        return None
    
    lines = stdout.strip().split('\n')
    
    # Chercher la dernière ligne qui commence par DAC_RESULT_JSON:
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('DAC_RESULT_JSON:'):
            json_str = line[len('DAC_RESULT_JSON:'):].strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse DAC_RESULT_JSON: {e}")
                return None
    
    # Fallback: chercher un JSON brut sur une ligne (legacy)
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('{'):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    
    return None


def dispatch_configure(
    text: str,
    instances: List[models.Instance],
    base_dir: Path,
    aws_credentials: Dict[str, str],
    db_session,
    session_id: int,
    user_id: int,
    trace_id: str = None,
) -> dict:
    """
    Dispatcher principal pour la configuration.
    
    Args:
        text: Texte de la demande utilisateur
        instances: Liste des instances cibles
        base_dir: Répertoire de travail pour les fichiers générés
        aws_credentials: Credentials AWS (access_key, secret_key, region)
        db_session: Session SQLAlchemy
        session_id: ID de la session de chat
        user_id: ID de l'utilisateur
        trace_id: ID de trace pour logging (optionnel)
        
    Returns:
        dict: Résultat de la configuration avec structure:
            {
                "status": "success" | "failed" | "partial",
                "mode": "installer_configure" | "configure_only",
                "results": [...],  # Détails par instance
                "summary": {...},  # Résumé global
                "error": str | None,
                "trace_id": str
            }
    """
    if not trace_id:
        trace_id = "no-trace"
    
    text_lower = text.lower()
    logger.info(f"[TRACE:{trace_id}] [CONFIGURE_DISPATCHER] Analyzing text: {text[:100]}")
    
    # ===================================================================
    # Étape 1: Détecter si une app du catalogue est mentionnée
    # ===================================================================
    apps = list_recipes()
    apps_sorted = sorted(apps, key=lambda x: len(x), reverse=True)

    matched_app = None
    for app in apps_sorted:
        pattern = rf"\b{re.escape(app.lower())}\b"
        if re.search(pattern, text_lower):
            matched_app = app
            break

    normalized_creds = _normalize_aws_creds(aws_credentials)
    
    if matched_app:
        logger.info(f"[TRACE:{trace_id}] [CONFIGURE_DISPATCHER] App detected: {matched_app} -> routing to InstallerEngine")
        return _dispatch_to_installer(
            text=text,
            matched_app=matched_app,
            instances=instances,
            base_dir=base_dir,
            aws_credentials=normalized_creds,
            db_session=db_session,
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
        )
    
    # ===================================================================
    # Étape 2: Fallback sur configure_only (configuration générique)
    # ===================================================================
    logger.info(f"[TRACE:{trace_id}] [CONFIGURE_DISPATCHER] No app detected -> routing to configure_only (fallback)")
    return _dispatch_to_configure_only(
        text=text,
        instances=instances,
        base_dir=base_dir,
        aws_credentials=normalized_creds,
        db_session=db_session,
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
    )


def _dispatch_to_installer(
    text: str,
    matched_app: str,
    instances: List[models.Instance],
    base_dir: Path,
    aws_credentials: Dict[str, str],
    db_session,
    session_id: int,
    user_id: int,
    trace_id: str = "no-trace",
) -> dict:
    """
    Route vers InstallerEngine pour installation/configuration d'apps du catalogue.
    """
    try:
        def _clip_text(text: str, max_chars: int = 1500) -> str:
            if not text:
                return ""
            return text[-max_chars:] if len(text) > max_chars else text

        if not aws_credentials:
            raise HTTPException(status_code=400, detail="AWS credentials missing")
        # Créer la requête d'installation
        instance_ids = [inst.instance_id for inst in instances]
        req = create_installation_request_from_text(
            text=text,
            instances=instance_ids,
            default_app=matched_app,
        )
        
        # Forcer l'intent à "configure" (pas "install")
        req.intent = "configure"
        
        logger.info(f"[TRACE:{trace_id}] [INSTALLER_CONFIGURE] Request created: app={req.app}, instances={len(instance_ids)}")
        
        # Valider la requête
        engine = InstallerEngine()
        ok, err = engine.validate_request(req)
        if not ok:
            logger.error(f"[TRACE:{trace_id}] [INSTALLER_CONFIGURE] Validation failed: {err}")
            return {
                "status": "failed",
                "mode": "installer_configure",
                "error": err,
                "results": [],
            }
        
        # Créer le plan d'installation
        plan = engine.create_plan(req)
        steps = getattr(plan, "steps", None)
        steps_count = len(steps) if isinstance(steps, list) else 0
        logger.info(f"[TRACE:{trace_id}] [INSTALLER_CONFIGURE] Plan created: {len(getattr(plan, 'steps', []) or [])} steps")
        
        # Générer le script d'exécution
        runner = InstallerRunner()
        script = runner.generate_runner_script(plan)
        logger.info(f"[TRACE:{trace_id}] [INSTALLER_CONFIGURE] Runner script generated ({len(script)} bytes)")
        
        # ===================================================================
        # Exécuter via SSM sur chaque instance
        # ===================================================================
        results = []
        for instance in instances:
            logger.info(f"[TRACE:{trace_id}] [INSTALLER_CONFIGURE] Executing on {instance.instance_id}...")
            
            try:
                execution_start = time.time()
                ssm_results = execute_via_ssm(
                    aws_access_key=aws_credentials.get("AWS_ACCESS_KEY_ID"),
                    aws_secret_key=aws_credentials.get("AWS_SECRET_ACCESS_KEY"),
                    instance_ids=[instance.instance_id],
                    command=script,
                    region=aws_credentials.get("AWS_DEFAULT_REGION") or aws_credentials.get("region") or "eu-north-1",
                )
                execution_duration = time.time() - execution_start
                ssm_result = ssm_results.get(instance.instance_id, {})
                
                # Parser la sortie du runner pour extraire les checks
                stdout = ssm_result.get("stdout", "")
                stderr = ssm_result.get("stderr", "")
                stdout_tail = _clip_text(ssm_result.get("stdout_tail", stdout), 1500)
                stderr_tail = _clip_text(ssm_result.get("stderr_tail", stderr), 1500)
                
                installation_result = runner.parse_runner_output(
                    stdout=stdout,
                    stderr=stderr,
                    instance_id=instance.instance_id,
                    duration=execution_duration,
                )
                
                # Extraire les infos supplémentaires du JSON dans stdout
                # Le JSON contient: installed_version, chosen_port, service_name, etc.
                version = None
                port = None
                service_name = None
                
                try:
                    json_data = _extract_runner_json(stdout)
                    if json_data:
                        version = json_data.get("installed_version")
                        port = json_data.get("chosen_port")
                        service_name = json_data.get("service_name")
                except Exception as e:
                    logger.warning(f"[INSTALLER_CONFIGURE] Could not extract extra info from JSON: {e}")
                
                # Déterminer le statut du service à partir des checks
                service_status = "active" if installation_result.checks.get("service_active") else "inactive"
                
                results.append({
                    "instance_id": instance.instance_id,
                    "instance_name": getattr(instance, "name", None) or instance.instance_id,
                    "status": installation_result.status,
                    "checks": installation_result.checks,
                    "installed_version": version,
                    "chosen_port": port,
                    "service_name": service_name,
                    "service_status": service_status,
                    "error": installation_result.error,
                    "ssm_command_id": ssm_result.get("command_id"),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                    "duration_seconds": ssm_result.get("duration_seconds"),
                })
                
            except Exception as e:
                logger.error(f"[TRACE:{trace_id}] [INSTALLER_CONFIGURE] Failed on {instance.instance_id}: {e}")
                results.append({
                    "instance_id": instance.instance_id,
                    "instance_name": getattr(instance, "name", None) or instance.instance_id,
                    "status": "failed",
                    "error": str(e),
                    "checks": {},
                    "installed_version": None,
                    "chosen_port": None,
                    "service_name": None,
                    "service_status": "unknown",
                    "ssm_command_id": None,
                    "stdout_tail": "",
                    "stderr_tail": "",
                    "duration_seconds": None,
                })
        
        # ===================================================================
        # Construire le résumé
        # ===================================================================
        success_count = sum(1 for r in results if r["status"] == "success")
        failed_count = sum(1 for r in results if r["status"] == "failed")
        
        overall_status = "success" if failed_count == 0 else ("partial" if success_count > 0 else "failed")
        
        chat_lines = []
        for r in results:
            inst_label = r.get("instance_name") or r.get("instance_id")
            if r.get("status") == "success":
                service = r.get("service_name") or "service"
                port = r.get("chosen_port")
                port_msg = f"port {port} OK" if port else "port non déterminé"
                chat_lines.append(
                    f"Instance {inst_label}: succès. Service {service} actif, {port_msg}."
                )
            else:
                service = r.get("service_name") or "service"
                err = r.get("error") or "Échec inconnu"
                stderr_tail = r.get("stderr_tail") or ""
                stderr_snippet = f" stderr: {stderr_tail}" if stderr_tail else ""
                chat_lines.append(
                    f"Instance {inst_label}: échec. Service {service} inactif. {err}.{stderr_snippet}"
                )

        chat_summary = "\n".join(chat_lines)
        global_summary = f"Configuration terminée: {success_count} succès / {failed_count} échec(s)."

        return {
            "status": overall_status,
            "mode": "installer_configure",
            "app": matched_app,
            "results": results,
            "summary": {
                "total": len(instances),
                "success": success_count,
                "failed": failed_count,
            },
            "error": None,
            "trace_id": trace_id,
            "chat_summary": {
                "global": global_summary,
                "per_instance": chat_lines,
                "message": f"{global_summary}\n" + chat_summary if chat_summary else global_summary,
            },
        }
        
    except Exception as e:
        logger.exception(f"[TRACE:{trace_id}] [INSTALLER_CONFIGURE] Unexpected error")
        raise HTTPException(status_code=500, detail=f"Installer error: {str(e)}")


def _dispatch_to_configure_only(
    text: str,
    instances: List[models.Instance],
    base_dir: Path,
    aws_credentials: Dict[str, str],
    db_session,
    session_id: int,
    user_id: int,
    trace_id: str = "no-trace",
) -> dict:
    """
    Route vers configure_only (Ansible fallback) pour configurations génériques.
    """
    try:
        logger.info(f"[TRACE:{trace_id}] [CONFIGURE_ONLY] Executing generic configuration for {len(instances)} instances")
        
        result = handle_configure_only(
            text=text,
            instances=instances,
            base_dir=base_dir,
            aws_credentials=aws_credentials,
            db_session=db_session,
            session_id=session_id,
            user_id=user_id,
        )
        
        # Ajouter le mode et garantir le contrat minimum
        result.setdefault("results", [])
        result.setdefault("summary", {"total": len(instances), "success": 0, "failed": 0})
        result.setdefault("error", None)
        result["mode"] = "configure_only"
        result["trace_id"] = trace_id
        return result
        
    except Exception as e:
        logger.exception(f"[TRACE:{trace_id}] [CONFIGURE_ONLY] Unexpected error: {e}")
        return {
            "status": "failed",
            "mode": "configure_only",
            "error": str(e),
            "results": [],
            "trace_id": trace_id,
        }
