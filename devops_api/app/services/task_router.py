from typing import List
from pydantic import BaseModel


class RoutedPlan(BaseModel):
    needs_terraform: bool
    needs_ansible: bool
    terraform_reqs: List[dict]
    ansible_reqs: List[dict]
    is_mixed: bool


def route_config_request(text: str) -> RoutedPlan:
    t_keywords = [
        "vpc", "subnet", "route table", "internet gateway", "nat gateway",
        "security group", "sg", "nacl", "load balancer", "alb", "nlb",
        "target group", "listener", "autoscaling", "asg", "launch template",
        "ebs", "volume", "snapshot", "ami", "iam", "role", "policy",
        "rds", "route53", "dns", "acm", "certificate", "cloudwatch", "alarm"
    ]
    a_keywords = [
        "install", "nginx", "apache", "docker", "user", "sudo", "ssh",
        "systemd", "ufw", "iptables", "package", "service", "config file",
        "/etc", "firewall", "listen", "port"
    ]

    lower = text.lower()
    hits_t = [kw for kw in t_keywords if kw in lower]
    hits_a = [kw for kw in a_keywords if kw in lower]

    needs_t = bool(hits_t)
    needs_a = bool(hits_a) or ("configure" in lower and not needs_t)

    return RoutedPlan(
        needs_terraform=needs_t,
        needs_ansible=needs_a,
        terraform_reqs=[{"keyword": kw} for kw in hits_t],
        ansible_reqs=[{"keyword": kw} for kw in hits_a],
        is_mixed=needs_t and needs_a,
    )
