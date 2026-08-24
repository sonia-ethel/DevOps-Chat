"""
OS-Aware Command Builder for Configure-Only

Generates OS-specific commands for:
- Linux (bash): apt/yum/systemctl/ufw
- Windows (PowerShell): Install-Package/New-NetFirewallRule/Start-Service
"""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class OSAwareCommandBuilder:
    """Build OS-specific commands for configure-only."""
    
    @staticmethod
    def install_package(os_family: str, package_name: str) -> str:
        """Generate install command for package."""
        os_family = os_family.lower()
        
        if os_family == "windows":
            # Windows: use Chocolatey or built-in commands
            if package_name == "nginx":
                # IIS instead of nginx on Windows
                return "Install-WindowsFeature -Name Web-Server -IncludeManagementTools"
            else:
                return f"Install-Package {package_name} -Force"
        
        # Linux: apt/yum detection
        return f"""
if command -v apt-get &> /dev/null; then
    apt-get update -y
    apt-get install -y {package_name}
elif command -v yum &> /dev/null; then
    yum install -y {package_name}
fi
""".strip()
    
    @staticmethod
    def ensure_service_running(os_family: str, service_name: str) -> str:
        """Generate command to ensure service is running."""
        os_family = os_family.lower()
        
        if os_family == "windows":
            if service_name == "nginx":
                service_name = "W3SVC"  # IIS service
            return f"""
Set-Service -Name {service_name} -StartupType Automatic
Start-Service -Name {service_name}
""".strip()
        
        # Linux: systemctl
        return f"""
systemctl enable {service_name}
systemctl start {service_name}
""".strip()
    
    @staticmethod
    def open_local_firewall_port(os_family: str, port: int, protocol: str = "tcp") -> str:
        """Generate command to open firewall port."""
        os_family = os_family.lower()
        
        if os_family == "windows":
            return f"""
New-NetFirewallRule -DisplayName "DAC-Port-{port}" -Direction Inbound -LocalPort {port} -Protocol {protocol.upper()} -Action Allow
""".strip()
        
        # Linux: ufw/firewalld detection
        return f"""
if command -v ufw &> /dev/null; then
    ufw allow {port}/{protocol}
elif command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-port={port}/{protocol}
    firewall-cmd --reload
fi
""".strip()
    
    @staticmethod
    def build_from_ansible_reqs(os_family: str, ansible_reqs: List[dict]) -> str:
        """
        Build shell/PowerShell script from Ansible requirements.
        
        Args:
            os_family: 'linux' or 'windows'
            ansible_reqs: List of requirements dicts
        
        Returns:
            Complete script (bash or PowerShell)
        """
        os_family = os_family.lower()
        commands = []
        
        # Build commands from requirements
        for req in ansible_reqs:
            keyword = req.get("keyword", "").lower()
            
            if "nginx" in keyword:
                commands.append(OSAwareCommandBuilder.install_package(os_family, "nginx"))
                commands.append(OSAwareCommandBuilder.ensure_service_running(os_family, "nginx"))
            
            elif "docker" in keyword:
                commands.append(OSAwareCommandBuilder.install_package(os_family, "docker" if os_family == "linux" else "docker-desktop"))
            
            elif "firewall" in keyword or "ufw" in keyword:
                # Open common ports
                commands.append(OSAwareCommandBuilder.open_local_firewall_port(os_family, 80))
                commands.append(OSAwareCommandBuilder.open_local_firewall_port(os_family, 443))
        
        # Join commands
        if os_family == "windows":
            # PowerShell script
            script = "# DAC Configure-Only PowerShell Script\n"
            script += "Set-ExecutionPolicy Bypass -Scope Process -Force\n\n"
            script += "\n\n".join(commands)
            return script
        else:
            # Bash script
            script = "#!/bin/bash\n"
            script = "# DAC Configure-Only Bash Script\n"
            script += "set -e\n\n"
            script += "\n\n".join(commands)
            return script


def build_os_aware_commands(os_family: str, ansible_reqs: List[dict]) -> str:
    """
    Convenience function to build OS-aware commands.
    
    Args:
        os_family: 'linux' or 'windows'
        ansible_reqs: List of requirement dicts from task_router
    
    Returns:
        Shell/PowerShell script
    """
    return OSAwareCommandBuilder.build_from_ansible_reqs(os_family, ansible_reqs)
