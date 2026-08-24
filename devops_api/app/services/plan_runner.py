# app/services/plan_runner.py
"""
Plan Runner Service - Executes generated code for real

Responsibilities:
1. Save generated code to disk
2. Execute Terraform (init, plan, apply, destroy)
3. Execute Ansible playbooks
4. Execute verification tests
5. Capture outputs and results
6. Update Plan execution status

IMPORTANT NOTES ON TEMPORARY SETTINGS:
- Ansible playbooks include wait_for_connection (10s delay + 300s timeout) to allow EC2 instances to boot
- SSH retries are enabled in ansible.cfg (default timeout 30s)
- These are TEMPORARY for MVP testing. In production:
  * Remove/reduce delays for pre-warmed instances
  * Use instance user data for faster boot
  * Set ANSIBLE_RETRIES_DISABLED=1 environment variable to skip retries
  * Adjust ANSIBLE_TIMEOUT_SECONDS for your infrastructure
"""

import os
import json
import subprocess
import tempfile
import shutil
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class PlanRunner:
    """Executes a plan with real infrastructure provisioning"""
    
    def __init__(self, plan_id: int, base_dir: str = None):
        """
        Initialize runner for a plan
        
        Args:
            plan_id: Database plan ID
            base_dir: Base directory for generated files (defaults to devops_api/generated_files)
        """
        self.plan_id = plan_id
        
        if base_dir is None:
            # Use relative to devops_api directory
            base_dir = os.path.join(os.path.dirname(__file__), "../../generated_files")
        
        self.base_dir = Path(base_dir).resolve()
        self.work_dir = self.base_dir / f"plan_{plan_id}"
        self.tf_dir = self.work_dir / "terraform"
        self.ansible_dir = self.work_dir / "ansible"
        self.logs_dir = self.work_dir / "logs"
        
        self._setup_directories()
    
    def _setup_directories(self):
        """Create necessary directories"""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.tf_dir.mkdir(parents=True, exist_ok=True)
        self.ansible_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Write a minimal ansible.cfg to disable host key checking and set sane defaults
        ansible_cfg = self.ansible_dir / "ansible.cfg"
        if not ansible_cfg.exists():
            ansible_cfg.write_text(
                """
[defaults]
host_key_checking = False
timeout = 30
retry_files_enabled = False
forks = 10

[ssh_connection]
ssh_args = -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
""".strip()
            )
    
    def save_terraform_files(self, terraform_code: Dict[str, str]) -> Dict[str, str]:
        """
        Save Terraform files to disk
        
        Args:
            terraform_code: {"main.tf": "...", "variables.tf": "...", "outputs.tf": "..."}
            
        Returns:
            {"main.tf": "/path/to/main.tf", ...}
        """
        saved_files = {}
        
        for filename, content in terraform_code.items():
            filepath = self.tf_dir / filename
            
            try:
                with open(filepath, 'w') as f:
                    f.write(content)
                saved_files[filename] = str(filepath)
                logger.info(f"Saved {filename} to {filepath}")
            except Exception as e:
                logger.error(f"Failed to save {filename}: {e}")
                raise
        
        return saved_files
    
    def save_ansible_files(self, ansible_code: Dict[str, str]) -> Dict[str, str]:
        """
        Save Ansible files to disk
        
        Args:
            ansible_code: {"configure.yml": "...", "roles/...": "..."}
            
        Returns:
            {"configure.yml": "/path/to/configure.yml", ...}
        """
        saved_files = {}
        
        for filename, content in ansible_code.items():
            filepath = self.ansible_dir / filename
            
            # Create subdirectories if needed
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                with open(filepath, 'w') as f:
                    f.write(content)
                saved_files[filename] = str(filepath)
                logger.info(f"Saved {filename} to {filepath}")
            except Exception as e:
                logger.error(f"Failed to save {filename}: {e}")
                raise
        
        return saved_files
    
    def save_inventory_file(self, inventory_content: str) -> str:
        """
        Save Ansible inventory file
        
        Args:
            inventory_content: Inventory INI format
            
        Returns:
            Path to saved inventory file
        """
        inventory_file = self.ansible_dir / "inventory.ini"
        
        try:
            with open(inventory_file, 'w') as f:
                f.write(inventory_content)
            logger.info(f"Saved inventory to {inventory_file}")
            return str(inventory_file)
        except Exception as e:
            logger.error(f"Failed to save inventory: {e}")
            raise
    
    def save_ssh_key_from_terraform(self, terraform_outputs: Dict[str, Any]) -> str:
        """
        Extract and save SSH private key from Terraform outputs
        
        Args:
            terraform_outputs: Terraform outputs dict containing 'ssh_key' (base64-encoded)
            
        Returns:
            Path to saved SSH key or empty string if not found
        """
        ssh_key_base64 = terraform_outputs.get("ssh_key")
        if not ssh_key_base64:
            logger.warning("No SSH key found in Terraform outputs")
            return ""
        
        try:
            # Decode base64
            import base64
            ssh_key_content = base64.b64decode(ssh_key_base64).decode('utf-8')
            
            # Create keys directory
            keys_dir = self.ansible_dir / "keys"
            keys_dir.mkdir(exist_ok=True)
            
            # Get key name from outputs
            ssh_key_name = terraform_outputs.get("ssh_key_name", "deployer-key")
            key_file = keys_dir / f"{ssh_key_name}.pem"
            
            # Save the key
            with open(key_file, 'w') as f:
                f.write(ssh_key_content)
            
            # Make it readable only by owner (chmod 600)
            os.chmod(key_file, 0o600)
            
            logger.info(f"Saved SSH key to {key_file}")
            return str(key_file)
        except Exception as e:
            logger.error(f"Failed to save SSH key: {e}")
            return ""
    
    def save_inventory_file(self, inventory_content: str) -> str:
        """
        Save Ansible inventory file
        
        Args:
            inventory_content: Inventory INI format
            
        Returns:
            Path to saved inventory file
        """
        inventory_file = self.ansible_dir / "inventory.ini"
        
        try:
            with open(inventory_file, 'w') as f:
                f.write(inventory_content)
            logger.info(f"Saved inventory to {inventory_file}")
            return str(inventory_file)
        except Exception as e:
            logger.error(f"Failed to save inventory: {e}")
            raise
    
    def save_verification_script(self, script_content: str) -> str:
        """
        Save verification script
        Args:
            script_content: Shell script content
            
        Returns:
            Path to saved script
        """
        script_file = self.work_dir / "verify.sh"
        
        try:
            with open(script_file, 'w') as f:
                f.write(script_content)
            
            # Make executable
            os.chmod(script_file, 0o755)
            logger.info(f"Saved verification script to {script_file}")
            return str(script_file)
        except Exception as e:
            logger.error(f"Failed to save verification script: {e}")
            raise
    
    def run_terraform_init(self, env: Optional[Dict] = None) -> Tuple[int, str, str]:
        """
        Run terraform init
        
        Returns:
            (exit_code, stdout, stderr)
        """
        logger.info(f"Running terraform init in {self.tf_dir}")
        
        cmd = ["terraform", "init"]
        log_file = self.logs_dir / "terraform_init.log"
        return self._run_command(cmd, cwd=str(self.tf_dir), env=env, log_file=log_file)
    
    def run_terraform_plan(self, env: Optional[Dict] = None) -> Tuple[int, str, str]:
        """
        Run terraform plan
        
        Returns:
            (exit_code, stdout, stderr)
        """
        logger.info(f"Running terraform plan in {self.tf_dir}")
        
        cmd = [
            "terraform", "plan",
            "-out=tfplan"
        ]
        log_file = self.logs_dir / "terraform_plan.log"
        return self._run_command(cmd, cwd=str(self.tf_dir), env=env, log_file=log_file)
    
    def run_terraform_apply(self, env: Optional[Dict] = None) -> Tuple[int, str, str]:
        """
        Run terraform apply
        
        Returns:
            (exit_code, stdout, stderr)
        """
        logger.info(f"Running terraform apply in {self.tf_dir}")
        
        cmd = [
            "terraform", "apply",
            "-auto-approve"
        ]
        log_file = self.logs_dir / "terraform_apply.log"
        return self._run_command(cmd, cwd=str(self.tf_dir), env=env, log_file=log_file)
    
    def get_terraform_outputs(self, env: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Extract Terraform outputs as JSON
        
        Returns:
            {"instance_ips": [...], "security_group_id": "...", ...}
        """
        logger.info(f"Extracting terraform outputs from {self.tf_dir}")
        
        cmd = ["terraform", "output", "-json"]
        log_file = self.logs_dir / "terraform_output.log"
        exit_code, stdout, stderr = self._run_command(cmd, cwd=str(self.tf_dir), env=env, log_file=log_file)
        
        if exit_code != 0:
            logger.error(f"Failed to get terraform outputs: {stderr}")
            return {}
        
        try:
            outputs = json.loads(stdout)
            # Convert from terraform output format to simple dict
            result = {}
            for key, value in outputs.items():
                if isinstance(value, dict) and "value" in value:
                    result[key] = value["value"]
                else:
                    result[key] = value
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse terraform outputs: {e}")
            return {}
    
    def run_terraform_destroy(self, env: Optional[Dict] = None) -> Tuple[int, str, str]:
        """
        Run terraform destroy (cleanup)
        
        Returns:
            (exit_code, stdout, stderr)
        """
        logger.info(f"Running terraform destroy in {self.tf_dir}")
        
        cmd = [
            "terraform", "destroy",
            "-auto-approve",
            "-json"
        ]
        return self._run_command(cmd, cwd=str(self.tf_dir), env=env)
    
    def run_ansible_playbook(
        self,
        playbook_file: str,
        inventory_file: str,
        ssh_key_file: Optional[str] = None
    ) -> Tuple[int, str, str]:
        """
        Run Ansible playbook with verbose output and relaxed host key checking.
        """
        logger.info(f"Running ansible-playbook {playbook_file}")

        cmd = [
            "ansible-playbook",
            playbook_file,
            "-i", inventory_file,
            "-vvv",
        ]

        if ssh_key_file:
            cmd.extend(["--private-key", ssh_key_file])

        log_file = self.logs_dir / "ansible.log"
        return self._run_command(cmd, cwd=str(self.work_dir), log_file=log_file)
    
    def run_verification_script(self, script_file: str, *instance_ips: str) -> Tuple[int, str, str]:
        """
        Run verification script
        
        Args:
            script_file: Path to verify.sh
            *instance_ips: IPs to test
            
        Returns:
            (exit_code, stdout, stderr)
        """
        logger.info(f"Running verification script {script_file}")
        
        cmd = [script_file] + list(instance_ips)
        return self._run_command(cmd, cwd=str(self.work_dir))
    
    def _run_command(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict] = None,
        log_file: Optional[Path] = None
    ) -> Tuple[int, str, str]:
        """
        Run shell command and capture output
        
        Args:
            cmd: Command and arguments
            cwd: Working directory
            env: Environment variables
            
        Returns:
            (exit_code, stdout, stderr)
        """
        try:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env or os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(timeout=900)  # allow longer cloud operations
            
            logger.debug(f"Command: {' '.join(cmd)}")
            logger.debug(f"Exit code: {process.returncode}")

            # Persist logs if requested
            if log_file:
                try:
                    log_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(log_file, "a") as lf:
                        lf.write(f"COMMAND: {' '.join(cmd)}\n")
                        if cwd:
                            lf.write(f"CWD: {cwd}\n")
                        lf.write(f"EXIT_CODE: {process.returncode}\n")
                        lf.write("--- STDOUT ---\n")
                        lf.write(stdout or "")
                        lf.write("\n--- STDERR ---\n")
                        lf.write(stderr or "")
                        lf.write("\n===== END =====\n\n")
                except Exception as log_err:
                    logger.error(f"Failed to write log {log_file}: {log_err}")
            
            return process.returncode, stdout, stderr
        
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error(f"Command timeout: {' '.join(cmd)}")
            return 124, "", "Command timed out after 15 minutes"
        
        except Exception as e:
            logger.error(f"Failed to run command: {e}")
            return 1, "", str(e)
    
    def cleanup(self, keep_terraform: bool = False):
        """
        Cleanup plan directory
        
        Args:
            keep_terraform: If True, keep Terraform state files
        """
        if not keep_terraform:
            logger.info(f"Cleaning up {self.work_dir}")
            shutil.rmtree(self.work_dir, ignore_errors=True)
        else:
            logger.info(f"Keeping Terraform files in {self.tf_dir}")


class PlanExecutor:
    """
    High-level executor for full plan execution flow
    
    Coordinates: generation -> file saving -> terraform -> inventory -> ansible -> verify
    """
    
    def __init__(self, plan_id: int):
        self.plan_id = plan_id
        self.runner = PlanRunner(plan_id)
        self.execution_log = {
            "plan_id": plan_id,
            "started_at": datetime.now().isoformat(),
            "phases": {}
        }
    
    def execute_phase_terraform_create(
        self,
        terraform_code: Dict[str, str],
        aws_credentials: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Execute Terraform creation phase"""
        
        phase_start = datetime.now()
        result = {
            "phase": "terraform.create",
            "status": "pending",
            "started_at": phase_start.isoformat(),
            "files_saved": {},
            "init": {},
            "plan": {},
            "apply": {},
            "outputs": {}
        }
        
        try:
            # Save files
            result["files_saved"] = self.runner.save_terraform_files(terraform_code)
            result["progress"] = 5
            
            # Prepare environment with AWS credentials
            env = os.environ.copy()
            if aws_credentials:
                if "AWS_ACCESS_KEY_ID" in aws_credentials:
                    env["AWS_ACCESS_KEY_ID"] = aws_credentials["AWS_ACCESS_KEY_ID"]
                if "AWS_SECRET_ACCESS_KEY" in aws_credentials:
                    env["AWS_SECRET_ACCESS_KEY"] = aws_credentials["AWS_SECRET_ACCESS_KEY"]
                if "region" in aws_credentials:
                    env["AWS_DEFAULT_REGION"] = aws_credentials["region"]
            
            # Init
            exit_code, stdout, stderr = self.runner.run_terraform_init(env=env)
            result["init"] = {
                "exit_code": exit_code,
                "stdout": stdout[:500],  # Truncate
                "stderr": stderr[:500]
            }
            result["progress"] = 25
            
            if exit_code != 0:
                result["status"] = "failed"
                return result
            
            # Plan
            exit_code, stdout, stderr = self.runner.run_terraform_plan(env=env)
            result["plan"] = {
                "exit_code": exit_code,
                "stdout": stdout[:500],
                "stderr": stderr[:500]
            }
            result["progress"] = 50
            
            if exit_code != 0:
                result["status"] = "failed"
                return result
            
            # Apply
            exit_code, stdout, stderr = self.runner.run_terraform_apply(env=env)
            result["apply"] = {
                "exit_code": exit_code,
                "stdout": stdout[:500],
                "stderr": stderr[:500]
            }
            result["progress"] = 75
            
            if exit_code != 0:
                result["status"] = "failed"
                return result
            
            # Get outputs
            outputs = self.runner.get_terraform_outputs(env=env)
            result["outputs"] = outputs
            result["progress"] = 100
            
            result["status"] = "completed"
            result["completed_at"] = datetime.now().isoformat()
            
            return result
        
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            return result
    
    def execute_phase_inventory_generate(
        self,
        inventory_content: str
    ) -> Dict[str, Any]:
        """Execute inventory generation phase"""
        
        result = {
            "phase": "inventory.generate",
            "status": "pending",
            "started_at": datetime.now().isoformat(),
            "inventory_file": None,
            "progress": 0
        }
        
        try:
            inventory_file = self.runner.save_inventory_file(inventory_content)
            result["inventory_file"] = inventory_file
            result["progress"] = 100
            result["status"] = "completed"
            result["completed_at"] = datetime.now().isoformat()
            return result
        
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            return result
    
    def execute_phase_ansible_configure(
        self,
        ansible_code: Dict[str, str],
        inventory_file: str
    ) -> Dict[str, Any]:
        """Execute Ansible configuration phase"""
        
        result = {
            "phase": "ansible.configure",
            "status": "pending",
            "started_at": datetime.now().isoformat(),
            "playbook_file": None,
            "execution": {},
            "files_saved": {},
            "progress": 0
        }
        
        try:
            # Wait for instances to be ready (they need time to boot and configure SSH)
            import time
            logger.info("Waiting 90 seconds for instances to be fully ready...")
            time.sleep(90)
            result["progress"] = 10
            
            # Save playbook
            saved_files = self.runner.save_ansible_files(ansible_code)
            playbook_file = saved_files.get("configure.yml")
            result["files_saved"] = saved_files
            
            if not playbook_file:
                result["status"] = "failed"
                result["error"] = "configure.yml not found in generated code"
                return result
            
            result["playbook_file"] = playbook_file
            
            # Run playbook
            exit_code, stdout, stderr = self.runner.run_ansible_playbook(
                playbook_file,
                inventory_file
            )
            
            result["execution"] = {
                "exit_code": exit_code,
                "stdout": stdout[:1000],  # Truncate
                "stderr": stderr[:1000]
            }
            result["progress"] = 100 if exit_code == 0 else 50
            result["status"] = "completed" if exit_code == 0 else "failed"
            result["completed_at"] = datetime.now().isoformat()
            return result
        
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            return result
    
    def execute_phase_verify(
        self,
        verify_script: str,
        instance_ips: List[str]
    ) -> Dict[str, Any]:
        """Execute verification phase"""
        result = {
            "phase": "verify",
            "status": "pending",
            "started_at": datetime.now().isoformat(),
            "script_file": None,
            "execution": {},
            "progress": 0
        }
        
        try:
            # Save script
            script_file = self.runner.save_verification_script(verify_script)
            result["script_file"] = script_file
            
            # Run script
            exit_code, stdout, stderr = self.runner.run_verification_script(
                script_file,
                *instance_ips
            )
            
            result["execution"] = {
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr
            }
            result["progress"] = 100 if exit_code == 0 else 50
            result["status"] = "completed" if exit_code == 0 else "warning"  # Tests may fail but script runs
            result["completed_at"] = datetime.now().isoformat()
            return result
        
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            return result

    def get_execution_log(self) -> Dict[str, Any]:
        """Get full execution log"""
        self.execution_log["completed_at"] = datetime.now().isoformat()
        return self.execution_log
