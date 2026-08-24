# app/services/plan_generator.py
"""
Convert user intent (natural language) -> structured Plan with deterministic requirements.

This is the HEART of the system: bridges natural language to infrastructure code.

Responsibilities:
1. Parse user prompt into deterministic categories
2. Extract infrastructure requirements (what AWS resources to create)
3. Extract configuration requirements (what to configure on servers)
4. Extract verification requirements (what to test after deployment)
5. Extract audit requirements (what to audit)
6. Generate execution plan (order of phases)
"""

import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


@dataclass
class InfraReq:
    """Infrastructure requirement (Terraform)."""
    type: str  # "ec2", "vpc", "sg", "alb", "rds", "iam_role", "route53", "acm"
    count: int = 1
    os: Optional[str] = None  # ubuntu, debian, centos, amazon-linux, windows
    instance_type: Optional[str] = None  # t3.micro, m5.large, etc.
    security_groups: List[Dict] = field(default_factory=list)  # [{"name": "web", "ingress": [80, 443]}]
    tags: Dict[str, str] = field(default_factory=dict)
    properties: Dict[str, Any] = field(default_factory=dict)  # Additional properties


@dataclass
class ConfigReq:
    """Configuration requirement (Ansible)."""
    type: str  # "package", "service", "user", "file", "docker", "nginx", "postgres", "firewall"
    state: str = "present"  # present, absent, running, stopped
    name: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)  # service=nginx, port=80, etc.


@dataclass
class VerifyReq:
    """Verification requirement (tests/checks)."""
    type: str  # "http", "tcp", "ssh", "dns"
    port: Optional[int] = None
    path: Optional[str] = None  # for HTTP
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReq:
    """Audit requirement."""
    type: str  # "lynis", "cis_benchmark", "security_scan"
    scope: Optional[str] = None  # system, application, network


@dataclass
class StructuredPlan:
    """Output of plan generation: deterministic structure."""
    infra_requirements: List[InfraReq] = field(default_factory=list)
    config_requirements: List[ConfigReq] = field(default_factory=list)
    verification_requirements: List[VerifyReq] = field(default_factory=list)
    audit_requirements: List[AuditReq] = field(default_factory=list)
    
    def to_dict(self):
        return {
            "infra": [asdict(r) for r in self.infra_requirements],
            "config": [asdict(r) for r in self.config_requirements],
            "verify": [asdict(r) for r in self.verification_requirements],
            "audit": [asdict(r) for r in self.audit_requirements],
        }


# ============ DETERMINISTIC KEYWORDS MAPPING ============

# AWS/Infrastructure keywords -> requirement types
INFRA_KEYWORDS = {
    # Compute
    "ec2|instance|instances|vm|machine": ("ec2", {}),
    "ami|image": ("ami", {}),
    "auto.?scaling|asg": ("asg", {}),
    "spot": ("spot_instance", {}),
    
    # Network
    "vpc|virtual.?private|network": ("vpc", {}),
    "subnet|subnets": ("subnet", {}),
    "igw|internet.?gateway": ("igw", {}),
    "nat.?gateway": ("nat_gateway", {}),
    "route.?table": ("route_table", {}),
    
    # Security
    "security.?group|sg": ("sg", {}),
    "nacl|network.?access": ("nacl", {}),
    "eip|elastic.?ip": ("eip", {}),
    
    # Load Balancing
    "alb|application.?load|balancer": ("alb", {}),
    "nlb|network.?load": ("nlb", {}),
    "target.?group": ("target_group", {}),
    
    # Database
    "rds|database": ("rds", {"engine": None}),
    "postgres|postgresql": ("rds", {"engine": "postgres"}),
    "mysql|mariadb": ("rds", {"engine": "mysql"}),
    "elasticsearch|opensearch": ("elasticsearch", {}),
    
    # Storage
    "s3|bucket": ("s3", {}),
    "ebs|volume": ("ebs", {}),
    "efs": ("efs", {}),
    
    # DNS & Certificates
    "route.?53|dns": ("route53", {}),
    "acm|certificate": ("acm", {}),
    
    # IAM
    "iam.?role|role": ("iam_role", {}),
    "iam.?policy|policy": ("iam_policy", {}),
    
    # Kubernetes
    "eks|kubernetes": ("eks", {}),
    "k8s": ("eks", {}),
}

# System/Configuration keywords -> requirement types
CONFIG_KEYWORDS = {
    # Package management
    "install|apt-get|yum|dnf": ("package", {"state": "present"}),
    "uninstall|remove": ("package", {"state": "absent"}),
    
    # Services
    "nginx|apache|httpd": ("service", {"name": "nginx"}),
    "docker": ("docker", {}),
    "postgres|postgresql": ("postgres_server", {}),
    "mysql|mariadb": ("mysql_server", {}),
    "redis": ("redis_server", {}),
    
    # Users & SSH
    "user|ssh|hardening": ("user", {}),
    "ssh.?key": ("ssh_key", {}),
    
    # Firewall OS
    "ufw|firewall|iptables": ("firewall", {}),
    
    # Config files
    "config|configuration|/etc": ("file", {}),
    
    # Systemd
    "systemd|service": ("systemd", {}),
    
    # Monitoring/Audit
    "monitoring|agent": ("monitoring", {}),
    "lynis|audit": ("audit", {}),
}

# Verification keywords
VERIFY_KEYWORDS = {
    "test|verify|check|health": "test",
    "http|port|80|443": "http",
    "tcp|port|connectivity": "tcp",
    "ssh|port|22": "ssh",
    "dns|domain": "dns",
}

# ============ MAIN PARSER ============

def generate_plan(prompt: str) -> StructuredPlan:
    """
    Convert natural language prompt -> StructuredPlan with deterministic requirements.
    
    Flow:
    1. Split prompt into sentences
    2. For each sentence, classify as infra/config/verify/audit
    3. Extract specific requirements
    4. Return structured plan
    """
    logger.info(f"Generating plan from prompt: {prompt[:100]}...")
    
    plan = StructuredPlan()
    
    # Normalize text
    text_lower = prompt.lower()
    sentences = re.split(r'[.;!?]', prompt)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        sent_lower = sentence.lower()
        
        # 1. Check for infrastructure keywords
        if _matches_keywords(sent_lower, INFRA_KEYWORDS):
            _extract_infra_requirements(sentence, sent_lower, plan)
        
        # 2. Check for configuration keywords
        if _matches_keywords(sent_lower, CONFIG_KEYWORDS):
            _extract_config_requirements(sentence, sent_lower, plan)
        
        # 3. Check for verification keywords
        if _matches_keywords(sent_lower, VERIFY_KEYWORDS):
            _extract_verify_requirements(sentence, sent_lower, plan)
        
        # 4. Check for audit keywords
        if any(kw in sent_lower for kw in ["audit", "lynis", "cis", "security.?scan"]):
            plan.audit_requirements.append(AuditReq(type="lynis", scope="system"))
    
    logger.info(f"Plan generated: {len(plan.infra_requirements)} infra, {len(plan.config_requirements)} config")
    return plan


def _matches_keywords(text: str, keywords_map: Dict[str, tuple]) -> bool:
    """Check if text contains any keywords from the map."""
    for pattern in keywords_map.keys():
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _extract_infra_requirements(sentence: str, sent_lower: str, plan: StructuredPlan):
    """Extract infrastructure requirements from sentence."""
    for pattern, (req_type, defaults) in INFRA_KEYWORDS.items():
        if re.search(pattern, sent_lower):
            # Extract count if present (e.g., "2 instances")
            count_match = re.search(r'(\d+)\s+(?:instance|vm|server|node)', sent_lower)
            count = int(count_match.group(1)) if count_match else 1
            
            # Extract OS if present
            os = None
            for os_name in ["ubuntu", "debian", "centos", "amazon-linux", "windows"]:
                if os_name in sent_lower:
                    os = os_name
                    break
            
            # Extract instance type if present
            instance_type = None
            type_match = re.search(r'\b([a-z]\d+[a-z]?\.\w+)\b', sent_lower)
            if type_match:
                instance_type = type_match.group(1)
            
            req = InfraReq(
                type=req_type,
                count=count,
                os=os,
                instance_type=instance_type,
                properties=defaults or {}
            )
            plan.infra_requirements.append(req)
            logger.debug(f"Extracted infra: {req}")
            break


def _extract_config_requirements(sentence: str, sent_lower: str, plan: StructuredPlan):
    """Extract configuration requirements from sentence."""
    for pattern, (req_type, defaults) in CONFIG_KEYWORDS.items():
        if re.search(pattern, sent_lower):
            state = defaults.get("state", "present")
            
            req = ConfigReq(
                type=req_type,
                state=state,
                properties=defaults or {}
            )
            plan.config_requirements.append(req)
            logger.debug(f"Extracted config: {req}")
            break


def _extract_verify_requirements(sentence: str, sent_lower: str, plan: StructuredPlan):
    """Extract verification requirements from sentence."""
    for pattern, verify_type in VERIFY_KEYWORDS.items():
        if re.search(pattern, sent_lower):
            # Extract port if present
            port_match = re.search(r'port\s*:?\s*(\d+)', sent_lower)
            port = int(port_match.group(1)) if port_match else None
            
            req = VerifyReq(
                type=verify_type,
                port=port
            )
            plan.verification_requirements.append(req)
            logger.debug(f"Extracted verify: {req}")
            break


# ============ EXPORT ============

def plan_to_json(plan: StructuredPlan) -> Dict:
    """Convert plan to JSON-serializable dict for database storage."""
    return plan.to_dict()


def plan_from_dict(data: Dict) -> StructuredPlan:
    """Reconstruct plan from database JSON."""
    plan = StructuredPlan()
    
    for item in data.get("infra", []):
        plan.infra_requirements.append(InfraReq(**item))
    
    for item in data.get("config", []):
        plan.config_requirements.append(ConfigReq(**item))
    
    for item in data.get("verify", []):
        plan.verification_requirements.append(VerifyReq(**item))
    
    for item in data.get("audit", []):
        plan.audit_requirements.append(AuditReq(**item))
    
    return plan
