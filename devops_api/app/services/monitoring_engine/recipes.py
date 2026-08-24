"""
Monitoring Engine - Recipes
Définit les recettes de monitoring (commandes + parsing)
"""
from typing import Dict, Any
import re


class MonitoringRecipe:
    """Recette de monitoring"""
    
    def __init__(
        self,
        name: str,
        description: str,
        metrics: list[str],
        commands: Dict[str, str],
        parser_func: callable = None
    ):
        self.name = name
        self.description = description
        self.metrics = metrics
        self.commands = commands
        self.parser_func = parser_func or self._default_parser
    
    def _default_parser(self, outputs: Dict[str, str]) -> Dict[str, Any]:
        """Parser par défaut"""
        return {"raw_outputs": outputs}


def parse_metrics_snapshot(outputs: Dict[str, str]) -> Dict[str, Any]:
    """Parse le snapshot de métriques"""
    metrics = {}
    
    # Parse CPU (top output)
    if "cpu" in outputs:
        cpu_output = outputs["cpu"]
        # Chercher la ligne %Cpu(s):
        cpu_match = re.search(r'%Cpu.*?(\d+\.\d+)\s*id', cpu_output)
        if cpu_match:
            idle = float(cpu_match.group(1))
            metrics["cpu_percent"] = round(100 - idle, 1)
        else:
            # Fallback: chercher autre format
            cpu_match2 = re.search(r'CPU:\s*(\d+\.\d+)%', cpu_output)
            if cpu_match2:
                metrics["cpu_percent"] = float(cpu_match2.group(1))
    
    # Parse Memory
    if "memory" in outputs:
        mem_output = outputs["memory"]
        # Format free -m: total used free
        mem_match = re.search(r'Mem:\s+(\d+)\s+(\d+)\s+(\d+)', mem_output)
        if mem_match:
            total = int(mem_match.group(1))
            used = int(mem_match.group(2))
            if total > 0:
                metrics["mem_used_percent"] = round((used / total) * 100, 1)
                metrics["mem_total_mb"] = total
                metrics["mem_used_mb"] = used
    
    # Parse Disk
    if "disk" in outputs:
        disk_output = outputs["disk"]
        # Format df: Filesystem Size Used Avail Use% Mounted
        for line in disk_output.split('\n'):
            if '/' in line and (line.strip().endswith('/') or '/dev/' in line):
                parts = line.split()
                if len(parts) >= 5:
                    use_str = parts[4].replace('%', '')
                    if use_str.isdigit():
                        metrics["disk_used_percent"] = int(use_str)
                        break
    
    # Parse Load average
    if "load" in outputs:
        load_output = outputs["load"].strip()
        # Format: 0.42 0.38 0.35 1/234 12345
        parts = load_output.split()
        if len(parts) >= 3:
            try:
                metrics["load_1"] = float(parts[0])
                metrics["load_5"] = float(parts[1])
                metrics["load_15"] = float(parts[2])
            except ValueError:
                pass
    
    # Parse Uptime
    if "uptime" in outputs:
        uptime_output = outputs["uptime"].strip()
        # Nettoyer et simplifier
        if uptime_output:
            metrics["uptime"] = uptime_output
    
    return metrics


# Recipe MVP: Snapshot de métriques
METRICS_SNAPSHOT_RECIPE = MonitoringRecipe(
    name="metrics_snapshot",
    description="Snapshot des métriques système",
    metrics=["CPU", "Memory", "Disk", "Load", "Uptime"],
    commands={
        "cpu": "top -bn1 | head -5",
        "memory": "free -m",
        "disk": "df -h /",
        "load": "cat /proc/loadavg",
        "uptime": "uptime -p 2>/dev/null || uptime | awk -F'up ' '{print $2}' | awk -F',' '{print $1}'"
    },
    parser_func=parse_metrics_snapshot
)


# Registry
MONITORING_RECIPES = {
    "metrics_snapshot": METRICS_SNAPSHOT_RECIPE
}


def get_monitoring_recipe(monitoring_type: str) -> MonitoringRecipe:
    """Récupère une recipe par nom"""
    return MONITORING_RECIPES.get(monitoring_type)
