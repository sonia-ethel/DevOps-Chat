# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/security/safe_subprocess.py
"""
P0.4 — Subprocess Injection Protection (PRODUCTION READY)

Règles:
- Interdit: shell=True, commandes en string, concat user input.
- Autorisé: commandes en LISTE d'arguments uniquement.
- Allowlist stricte des binaires.
- Timeout obligatoire.
- Retour standardisé (returncode/stdout/stderr).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any


# OK Allowlist des binaires autorisés (adapter si nécessaire)
ALLOWED_BINARIES = {
    "terraform",
    "ansible-playbook",
    "ansible-galaxy",
    "kubectl",
    "helm",
}

# OK Caractères/patterns typiques d'injection (defense-in-depth)
FORBIDDEN_TOKENS = {";", "&&", "||", "|", "`", "$(", ")", "\n", "\r"}


class UnsafeCommandError(Exception):
    pass


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def _validate_command(cmd: List[str]) -> None:
    if not isinstance(cmd, list) or not cmd or any(not isinstance(x, str) for x in cmd):
        raise UnsafeCommandError("Command must be a non-empty list[str].")

    # binaire
    binary = cmd[0].strip()
    if binary not in ALLOWED_BINARIES:
        raise UnsafeCommandError(f"Binary not allowed: {binary}")

    # no injection tokens
    joined = " ".join(cmd)
    for t in FORBIDDEN_TOKENS:
        if t in joined:
            raise UnsafeCommandError(f"Forbidden token detected in command: {t}")


def _validate_cwd(cwd: Optional[str]) -> Optional[str]:
    if cwd is None:
        return None
    p = Path(cwd).resolve()
    if not p.exists() or not p.is_dir():
        raise UnsafeCommandError(f"Invalid cwd: {cwd}")
    # Optionnel: restreindre à un sous-dossier contrôlé (generated_files)
    return str(p)


def run_safe_command(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout_seconds: int = 900,
) -> CommandResult:
    """
    Exécute une commande système de façon sûre.
    - cmd: list[str] (obligatoire)
    - shell: interdit
    - timeout: obligatoire
    """
    _validate_command(cmd)
    safe_cwd = _validate_cwd(cwd)

    merged_env = os.environ.copy()
    if env:
        merged_env.update({k: str(v) for k, v in env.items()})

    completed = subprocess.run(
        cmd,
        cwd=safe_cwd,
        env=merged_env,
        text=True,
        capture_output=True,
        shell=False,            # OK interdit
        check=False,            # OK on gère le code retour
        timeout=timeout_seconds # OK anti-freeze
    )

    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
