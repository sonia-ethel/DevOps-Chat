"""
Audit Engine - Runner
Exécute les audits via SSM sur les instances
"""
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.audit_engine.schemas import (
    AuditResult,
    InstanceAuditResult,
    AuditSummary,
    AuditFinding,
    AuditPlan,
)
from app.services.audit_engine.recipes import get_audit_recipe
from app.services.ssm_executor import SSMExecutor
from app.utils.execution_progress import update_execution_progress

logger = logging.getLogger(__name__)


def _fallback_detect_os(instance_id: str, region: str) -> str:
    # Minimal fallback: we assume Linux. Extend later with real detection.
    logger.debug("[AUDIT_OS_FALLBACK] instance=%s region=%s -> linux", instance_id, region)
    return "linux"


class AuditRunner:
    """Exécute des audits sur des instances"""

    def __init__(
        self,
        db=None,
        ssm_executor: SSMExecutor | None = None,
        region: str = "us-east-1",
    ):
        self.region = region
        self.db = db
        self.ssm_executor = ssm_executor
    
    def create_plan(
        self,
        instance_ids: List[str],
        recipe_names: List[str],
    ) -> AuditPlan:
        """Crée un plan d'audit"""

        recipes = []
        checks: List[str] = []
        commands_preview: List[str] = []
        total_commands = 0

        for name in recipe_names:
            recipe = get_audit_recipe(name)
            if not recipe:
                raise ValueError(f"Unknown audit recipe: {name}")
            recipes.append(recipe)
            checks.extend(recipe.checks)
            total_commands += len(recipe.commands)
            commands_preview.extend(list(recipe.commands.values())[:2])

        estimated_seconds = max(30, len(instance_ids) * max(1, total_commands) * 5)

        return AuditPlan(
            audit_type="full" if len(recipe_names) > 1 else recipe_names[0],
            recipe_names=recipe_names,
            instances_count=len(instance_ids),
            instance_ids=instance_ids,
            checks=checks,
            impact="read-only",
            estimated_duration_seconds=estimated_seconds,
            commands_preview=commands_preview[:5],
        )
    
    async def run_audit(
        self,
        plan: AuditPlan,
        user_id: int,
        session_id: int,
        task_id: str | None = None,
        execution_id_db: int | None = None,
    ) -> AuditResult:
        if not self.ssm_executor:
            raise ValueError("SSM executor manquant pour l'audit")

        #  CRITICAL: task_id doit être fourni pour publier sur le bon canal SSE
        if task_id is None:
            logger.warning(
                "[AUDIT_RUNNER] task_id is None! SSE events will NOT be published. "
                "This is acceptable for dashboard audits without SSE, but critical for chat audits."
            )
        else:
            logger.info(
                "[AUDIT_RUNNER] Starting audit with task_id=%s (will publish SSE events to this channel)",
                task_id,
            )

        logger.info(
            "[AUDIT_START] recipes=%s instances=%d task_id=%s",
            plan.recipe_names,
            len(plan.instance_ids),
            task_id,
        )

        instance_results: List[InstanceAuditResult] = []
        summary = AuditSummary(instances_total=len(plan.instance_ids))

        #  Calculate total steps for fine-grained progress
        total_instances = max(1, len(plan.instance_ids))
        total_commands = 0
        for recipe_name in plan.recipe_names:
            recipe = get_audit_recipe(recipe_name)
            if recipe:
                total_commands += len(recipe.commands)
        total_steps = max(1, total_instances * max(1, total_commands))
        
        current_step = 0
        last_progress = -1
        
        # 20% for preparation (already done in executions_routes)
        # 70% for execution
        # 10% for finalization
        
        if execution_id_db:
            update_execution_progress(
                self.db, execution_id_db, 20, "Audit démarré", "preparing"
            )

        for idx, instance_id in enumerate(plan.instance_ids, start=1):
            try:
                msg = f"Instance {idx}/{total_instances}"
                if execution_id_db:
                    update_execution_progress(
                        self.db, execution_id_db, 20, msg, "running"
                    )
                
                current_step_ref = {'value': current_step}
                last_progress_ref = {'value': last_progress}
                result = await self._audit_instance(
                    instance_id,
                    plan.recipe_names,
                    execution_id=task_id,
                    execution_id_db=execution_id_db,
                    instance_index=idx,
                    total_instances=total_instances,
                    current_step_ref=current_step_ref,
                    total_steps=total_steps,
                    last_progress_ref=last_progress_ref,
                )
                instance_results.append(result)

                if result.status == "success":
                    summary.ok += 1
                else:
                    summary.failed += 1

                for finding in result.findings:
                    if finding.severity == "critical":
                        summary.critical_findings += 1
                    elif finding.severity == "high":
                        summary.high_findings += 1
                    elif finding.severity == "medium":
                        summary.medium_findings += 1
                    elif finding.severity == "low":
                        summary.low_findings += 1
                
                # Update current_step from the result
                current_step = current_step_ref['value']
                last_progress = last_progress_ref['value']

            except Exception as e:
                logger.error("[AUDIT_ERROR] instance=%s error=%s", instance_id, str(e))
                summary.failed += 1
                instance_results.append(
                    InstanceAuditResult(
                        instance_id=instance_id,
                        os="unknown",
                        status="failed",
                        error=str(e),
                    )
                )
            finally:
                pass

        if summary.ok == summary.instances_total:
            overall_status = "success"
        elif summary.ok > 0:
            overall_status = "partial"
        else:
            overall_status = "failed"

        audit_result = AuditResult(
            audit_type=plan.audit_type,
            status=overall_status,
            summary=summary,
            instances=instance_results,
            task_id=task_id,
        )

        logger.info(
            "[AUDIT_COMPLETE] task_id=%s status=%s ok=%d/%d",
            task_id,
            overall_status,
            summary.ok,
            summary.instances_total,
        )

        # Final progress update
        if execution_id_db:
            update_execution_progress(
                self.db, execution_id_db, 100, "Audit terminé", "finalizing"
            )

        return audit_result
    
    async def _audit_instance(
        self,
        instance_id: str,
        recipe_names: List[str],
        execution_id: str | None = None,
        execution_id_db: int | None = None,
        instance_index: int = 1,
        total_instances: int = 1,
        current_step_ref: Dict[str, int] | None = None,
        total_steps: int = 1,
        last_progress_ref: Dict[str, int] | None = None,
    ) -> InstanceAuditResult:
        logger.info("[AUDIT_INSTANCE] instance=%s recipes=%s", instance_id, recipe_names)

        os_type = _fallback_detect_os(instance_id, self.region)
        outputs: Dict[str, str] = {}
        all_stdout: List[str] = []
        all_stderr: List[str] = []

        for recipe_name in recipe_names:
            recipe = get_audit_recipe(recipe_name)
            if not recipe:
                all_stderr.append(f"=== {recipe_name} ===\nUnknown recipe")
                continue

            for cmd_name, cmd in recipe.commands.items():
                try:
                    logger.debug("[AUDIT_CMD] instance=%s recipe=%s cmd=%s", instance_id, recipe_name, cmd_name)
                    
                    exec_result = self.ssm_executor.execute_command(
                        instance_ids=[instance_id],
                        command=cmd,
                        timeout=45,
                    )
                    cmd_output = exec_result.get(instance_id, {})
                    stdout_val = cmd_output.get("stdout", "")
                    stderr_val = cmd_output.get("stderr", "") or cmd_output.get("error", "")
                    if cmd_output.get("status") not in ("success", "Success"):
                        stderr_val = stderr_val or "Commande SSM échouée"
                    outputs[f"{recipe_name}.{cmd_name}"] = stdout_val
                    all_stdout.append(f"=== {recipe_name}:{cmd_name} ===\n{stdout_val}")
                    if stderr_val:
                        all_stderr.append(f"=== {recipe_name}:{cmd_name} ===\n{stderr_val}")
                    
                    #  Update fine-grained progress
                    if current_step_ref is not None and execution_id_db:
                        current_step_ref['value'] += 1
                        computed_progress = 20 + int((current_step_ref['value'] / total_steps) * 70)
                        
                        # Only update if progress changed
                        if last_progress_ref is None:
                            last_progress_ref = {'value': -1}
                        
                        if computed_progress != last_progress_ref['value']:
                            last_progress_ref['value'] = computed_progress
                            msg = f"Instance {instance_index}/{total_instances} • {recipe_name}"
                            update_execution_progress(
                                self.db, execution_id_db, computed_progress, msg, "running"
                            )
                
                except Exception as e:
                    logger.warning(
                        "[AUDIT_CMD_ERROR] instance=%s recipe=%s cmd=%s error=%s",
                        instance_id,
                        recipe_name,
                        cmd_name,
                        str(e),
                    )
                    outputs[f"{recipe_name}.{cmd_name}"] = f"ERROR: {str(e)}"
                    all_stderr.append(f"=== {recipe_name}:{cmd_name} ===\nERROR: {str(e)}")
                    
                    # Still update progress counter even on error
                    if current_step_ref is not None:
                        current_step_ref['value'] += 1

        findings: List[AuditFinding] = []
        metrics: Dict[str, Any] = {}
        command_errors = [
            value for value in all_stderr
            if isinstance(value, str) and value.strip()
        ]
        status = "failed" if command_errors and len(command_errors) >= len(outputs) else "partial" if command_errors else "success"

        for recipe_name in recipe_names:
            recipe = get_audit_recipe(recipe_name)
            if not recipe:
                continue
            try:
                # Filter outputs belonging to this recipe
                recipe_outputs = {
                    k.split(".", 1)[1]: v
                    for k, v in outputs.items()
                    if k.startswith(f"{recipe_name}.")
                }
                parsed = recipe.parser_func(recipe_outputs, os_type)
                findings.extend([AuditFinding(**f) for f in parsed.get("findings", [])])
                metrics.update(parsed.get("metrics", {}))
            except Exception as e:
                logger.error("[AUDIT_PARSE_ERROR] instance=%s recipe=%s error=%s", instance_id, recipe_name, str(e))
                status = "partial"

        return InstanceAuditResult(
            instance_id=instance_id,
            os=os_type,
            status=status,
            findings=findings,
            metrics=metrics,
            stdout="\n\n".join(all_stdout),
            stderr="\n\n".join(all_stderr) if all_stderr else None,
        )


# Helper pour sauvegarder le rapport
def save_audit_report(
    audit_result: AuditResult, 
    output_dir: str = "generated_files/audits",
    db=None,
    session_id: int = None,
    user_id: int = None
):
    """Sauvegarde le rapport d'audit dans un fichier JSON et en DB"""
    import os
    from app.models import AuditSnapshot
    
    os.makedirs(output_dir, exist_ok=True)
    
    task_id = audit_result.task_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"audit_{task_id}.json"
    filepath = os.path.join(output_dir, filename)
    
    # Save to JSON file
    with open(filepath, "w") as f:
        json.dump(audit_result.dict(), f, indent=2)
    
    logger.info(f"[AUDIT_REPORT] Saved to {filepath}")
    
    # Save to DB if db session provided
    if db is not None:
        try:
            # Count findings by severity
            severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
            for instance_result in audit_result.instances:
                for finding in instance_result.findings:
                    severity = finding.severity.upper()
                    if severity in severity_counts:
                        severity_counts[severity] += 1
            
            snapshot = AuditSnapshot(
                instances_total=audit_result.summary.instances_total,
                instances_ok=audit_result.summary.instances_ok,
                instances_failed=audit_result.summary.instances_failed,
                critical_count=severity_counts["CRITICAL"],
                high_count=severity_counts["HIGH"],
                medium_count=severity_counts["MEDIUM"],
                low_count=severity_counts["LOW"],
                info_count=severity_counts["INFO"],
                status=audit_result.status,  # FIXED: use audit_result.status instead of summary.status
                full_data=json.dumps(audit_result.dict()),
                user_id=user_id,
                session_id=session_id,
            )
            db.add(snapshot)
            db.commit()
            logger.info(f"[AUDIT_SNAPSHOT] Saved to DB: snapshot_id={snapshot.id}")
        except Exception as e:
            logger.error(f"[AUDIT_SNAPSHOT_ERROR] Failed to save to DB: {e}")
            db.rollback()
    
    return filepath
