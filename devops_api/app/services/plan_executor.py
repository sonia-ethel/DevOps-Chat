# app/services/plan_executor.py
"""
Plan Executor Service
Converts structured plan requirements into executable code (Terraform, Ansible, etc.)
"""

import json
import uuid
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from app.models.plan import Plan, PlanExecution, PlanPhase
from app.services.plan_generator import InfraReq, ConfigReq, VerifyReq, AuditReq
from app.services.ami_resolver import resolve_ami_for_create


@dataclass
class TerraformContext:
    """Context for Terraform generation from infra requirements"""
    project_name: str
    region: str = "eu-west-1"
    infra_reqs: List[InfraReq] = None
    
    def __post_init__(self):
        if self.infra_reqs is None:
            self.infra_reqs = []


@dataclass
class AnsibleContext:
    """Context for Ansible generation from config requirements"""
    playbook_name: str
    config_reqs: List[ConfigReq] = None
    inventory_path: str = None
    
    def __post_init__(self):
        if self.config_reqs is None:
            self.config_reqs = []


def extract_terraform_from_requirements(infra_requirements: List) -> Dict[str, str]:
    """
    Convert plan.infra_requirements to Terraform code
    
    Input: [
        InfraReq(type="ec2", ...) objects or dicts
    ]
    
    Output: {"main.tf": "...", "variables.tf": "...", "outputs.tf": "..."}
    """
    
    # Parse infra requirements - already InfraReq objects or dicts
    infra_reqs = []
    for req in infra_requirements:
        if isinstance(req, dict):
            infra_reqs.append(InfraReq(**req))
        else:
            # Already an InfraReq object
            infra_reqs.append(req)
    
    # Generate main.tf content
    main_tf = _generate_main_tf(infra_reqs)
    
    # Generate variables.tf content
    variables_tf = _generate_variables_tf(infra_reqs)
    
    # Generate outputs.tf content
    outputs_tf = _generate_outputs_tf(infra_reqs)
    
    return {
        "main.tf": main_tf,
        "variables.tf": variables_tf,
        "outputs.tf": outputs_tf
    }


def _generate_main_tf(infra_reqs: List[InfraReq]) -> str:
    """Generate main.tf from infrastructure requirements"""
    
    lines = [
        '# Auto-generated Terraform configuration',
        '# Generated from Plan-Based Architecture',
        '',
        'terraform {',
        '  required_version = ">= 1.0"',
        '  required_providers {',
        '    aws = {',
        '      source  = "hashicorp/aws"',
        '      version = "~> 5.0"',
        '    }',
        '    tls = {',
        '      source  = "hashicorp/tls"',
        '      version = "~> 4.0"',
        '    }',
        '    random = {',
        '      source  = "hashicorp/random"',
        '      version = "~> 3.0"',
        '    }',
        '  }',
        '}',
        '',
        'provider "aws" {',
        '  region = var.aws_region',
        '}',
        '',
        '# Get availability zones',
        'data "aws_availability_zones" "available" {',
        '  state = "available"',
        '}',
        '',
        '# Use default VPC (always exists)',
        'data "aws_vpc" "default" {',
        '  default = true',
        '}',
        '',
        '# Get default subnets',
        'data "aws_subnets" "default" {',
        '  filter {',
        '    name   = "vpc-id"',
        '    values = [data.aws_vpc.default.id]',
        '  }',
        '}',
        '',
        '# Generate unique suffix for resources',
        'resource "random_string" "suffix" {',
        '  length  = 8',
        '  special = false',
        '}',
        '',
    ]
    
    # Track EC2 instances and aggregate count
    ec2_instances = []
    total_ec2_count = 0
    ec2_os = None
    ec2_instance_type = None
    ec2_tags = {}
    
    for req in infra_reqs:
        if req.type == "ec2":
            ec2_instances.append(req)
            total_ec2_count += req.count
            ec2_os = ec2_os or req.os or "ubuntu"
            ec2_instance_type = ec2_instance_type or req.instance_type or "t3.micro"
            ec2_tags.update(req.tags or {})
    
    # Generate EC2 resources ONCE if any exist (SSM-first multi-OS)
    if ec2_instances:
        # Resolve AMI for requested OS (default: amazonlinux2)
        os_family = "linux"  # Default
        distro = ec2_os or "amazonlinux2"
        
        # Normalize distro name
        distro_lower = distro.lower()
        if "ubuntu" in distro_lower:
            distro = "ubuntu"
        elif "debian" in distro_lower:
            distro = "debian"
        elif "windows" in distro_lower:
            os_family = "windows"
            distro = "windows"
        else:
            distro = "amazonlinux2"
        
        # Resolve AMI + user_data (region eu-north-1 hardcoded for now)
        ami_info = resolve_ami_for_create(
            os_family=os_family,
            distro=distro,
            version=None,  # Use latest
            region="eu-north-1",
            aws_access_key=None,  # Will use env/instance profile
            aws_secret_key=None
        )
        
        ami_id = ami_info["ami_id"]
        user_data = ami_info["user_data"]
        
        default_tags = {
            "managed_by": "dac",
            "env": "default",
            "owner": "dac",
            "created_via": "intent",
        }
        default_tags.update(ec2_tags or {})

        # IAM role/profile for SSM
        lines.extend([
            '# IAM assume-role policy for EC2 SSM',
            'data "aws_iam_policy_document" "ssm_assume_role" {',
            '  statement {',
            '    actions = ["sts:AssumeRole"]',
            '    principals {',
            '      type        = "Service"',
            '      identifiers = ["ec2.amazonaws.com"]',
            '    }',
            '  }',
            '}',
            '',
            '# IAM role + instance profile for SSM Core',
            'resource "aws_iam_role" "ssm_core" {',
            '  name               = "dac-ssm-core-${random_string.suffix.result}"',
            '  assume_role_policy = data.aws_iam_policy_document.ssm_assume_role.json',
            '  tags = {',
            '    managed_by  = "dac"',
            '    created_via = "intent"',
            '  }',
            '}',
            '',
            'resource "aws_iam_instance_profile" "ssm_core" {',
            '  name = "dac-ssm-profile-${random_string.suffix.result}"',
            '  role = aws_iam_role.ssm_core.name',
            '}',
            '',
            'resource "aws_iam_role_policy_attachment" "ssm_core" {',
            '  role       = aws_iam_role.ssm_core.name',
            '  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"',
            '}',
            '',
        ])
        
        # EC2 instance resource
        lines.extend([
            f'# EC2 Instance(s) - SSM-ready ({distro})',
            f'resource "aws_instance" "main" {{',
            f'  count                      = {total_ec2_count}',
            f'  ami                        = "{ami_id}"',
            f'  instance_type              = "{ec2_instance_type}"',
            f'  subnet_id                  = data.aws_subnets.default.ids[0]',
            f'  vpc_security_group_ids     = [aws_security_group.web_sg.id]',
            f'  associate_public_ip_address = true',
            f'  iam_instance_profile       = aws_iam_instance_profile.ssm_core.name',
        ])
        
        # Inject user_data if required (SSM agent install)
        if user_data:
            # Escape for Terraform HCL (use heredoc)
            lines.append('')
            lines.append('  user_data = <<-EOF')
            for line in user_data.strip().split('\n'):
                lines.append('    ' + line)
            lines.append('  EOF')
        
        lines.extend([
            '',
            f'  tags = {{',
            f'    Name        = "instance-${{count.index + 1}}"',
            f'    managed_by  = "{default_tags.get("managed_by", "dac")}"',
            f'    env         = "{default_tags.get("env", "default")}"',
            f'    owner       = "{default_tags.get("owner", "dac")}"',
            f'    created_via = "{default_tags.get("created_via", "intent")}"',
            f'  }}',
            f'}}',
            f'',
        ])
    
    # Security group for HTTP/S (no automatic SSH)
    lines.extend([
        f'# Security Group - web_sg (in default VPC)',
        f'resource "aws_security_group" "web_sg" {{',
        f'  name        = "dac-web-sg-${{random_string.suffix.result}}"',
        f'  description = "Allow web traffic; SSM uses outbound 443"',
        f'  vpc_id      = data.aws_vpc.default.id',
        f'',
        f'  ingress {{',
        f'    from_port   = 80',
        f'    to_port     = 80',
        f'    protocol    = "tcp"',
        f'    cidr_blocks = ["0.0.0.0/0"]',
        f'  }}',
        f'  ingress {{',
        f'    from_port   = 443',
        f'    to_port     = 443',
        f'    protocol    = "tcp"',
        f'    cidr_blocks = ["0.0.0.0/0"]',
        f'  }}',
        f'',
        f'  egress {{',
        f'    from_port   = 0',
        f'    to_port     = 0',
        f'    protocol    = "-1"',
        f'    cidr_blocks = ["0.0.0.0/0"]',
        f'  }}',
        f'',
        f'  tags = {{',
        f'    Name        = "dac-web-sg"',
        f'    managed_by  = "dac"',
        f'    created_via = "intent"',
        f'  }}',
        f'}}',
        f'',
    ])
    
    return '\n'.join(lines)


def _generate_variables_tf(infra_reqs: List[InfraReq]) -> str:
    """Generate variables.tf from infrastructure requirements"""
    
    lines = [
        '# Variable definitions',
        '',
        'variable "aws_region" {',
        '  description = "AWS region"',
        '  type        = string',
        '  default     = "eu-north-1"',
        '}',
        '',
    ]
    
    return '\n'.join(lines)


def _generate_outputs_tf(infra_reqs: List[InfraReq]) -> str:
    """Generate outputs.tf from infrastructure requirements"""
    
    lines = [
        '# Output values for Ansible inventory generation',
        '',
        'output "instance_ips" {',
        '  description = "Public IPs of created instances"',
        '  value       = aws_instance.main[*].public_ip',
        '}',
        '',
        'output "instance_ids" {',
        '  description = "Instance IDs"',
        '  value       = aws_instance.main[*].id',
        '}',
        '',
        'output "security_group_id" {',
        '  description = "Security group ID"',
        '  value       = aws_security_group.web_sg.id',
        '}',
        '',
    ]
    
    return '\n'.join(lines)


def _get_ami_filter_for_os(os_type: str) -> str:
    """Get AMI filter pattern for OS type"""
    
    os_lower = os_type.lower()
    
    if "ubuntu" in os_lower:
        return '["ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"]'
    elif "debian" in os_lower:
        return '["debian-12-amd64-*"]'
    elif "amazon" in os_lower or "amzn" in os_lower:
        return '["amzn2-ami-hvm-*"]'
    elif "rhel" in os_lower or "redhat" in os_lower:
        return '["RHEL-9*"]'
    elif "centos" in os_lower:
        return '["CentOS-7*"]'
    else:
        return '["ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"]'


def extract_ansible_from_requirements(config_requirements: List) -> Dict[str, str]:
    """
    Convert plan.config_requirements to Ansible playbook
    
    Input: [
        ConfigReq(type="docker", ...) objects or dicts
    ]
    
    Output: {"configure.yml": "..."}
    """
    
    # Parse config requirements - already ConfigReq objects or dicts
    config_reqs = []
    for req in config_requirements:
        if isinstance(req, dict):
            config_reqs.append(ConfigReq(**req))
        else:
            # Already a ConfigReq object
            config_reqs.append(req)
    
    # Generate playbook content
    playbook_content = _generate_ansible_playbook(config_reqs)
    
    return {
        "configure.yml": playbook_content
    }


def _generate_ansible_playbook(config_reqs: List[ConfigReq]) -> str:
    """Generate Ansible playbook from configuration requirements"""
    
    lines = [
        '---',
        '# Auto-generated Ansible playbook',
        '# Generated from Plan-Based Architecture',
        '',
        '- name: Configure infrastructure',
        '  hosts: all',
        '  become: true',
        '  gather_facts: yes',
        '  # TEMPORARY: retries for EC2 boot completion',
        '  # Remove/reduce these if instances are pre-warmed or you prefer failures',
        '  vars:',
        '    ansible_connection_retries: 10',
        '',
        '  tasks:',
        '    - name: Wait for system to be ready',
        '      wait_for_connection:',
        '        delay: 5',
        '        timeout: 600',
        '',
        '    - name: Update package cache',
        '      apt:',
        '        update_cache: yes',
        '      when: ansible_os_family == "Debian"',
        '',
    ]
    
    for req in config_reqs:
        if req.type == "docker":
            lines.extend([
                '    - name: Install Docker',
                '      apt:',
                '        name: docker.io',
                '        state: present',
                '      when: ansible_os_family == "Debian"',
                '',
                '    - name: Start Docker service',
                '      service:',
                '        name: docker',
                '        state: started',
                '        enabled: yes',
                '',
            ])
        
        elif req.type == "nginx" or req.type == "service" and req.properties.get("name") == "nginx":
            lines.extend([
                '    - name: Install Nginx',
                '      apt:',
                '        name: nginx',
                '        state: present',
                '      when: ansible_os_family == "Debian"',
                '',
                '    - name: Start Nginx service',
                '      service:',
                '        name: nginx',
                '        state: started',
                '        enabled: yes',
                '',
            ])
        
        elif req.type == "postgres" or req.type == "postgres_server":
            lines.extend([
                '    - name: Install PostgreSQL',
                '      apt:',
                '        name:',
                '          - postgresql',
                '          - postgresql-contrib',
                '        state: present',
                '      when: ansible_os_family == "Debian"',
                '',
                '    - name: Start PostgreSQL service',
                '      service:',
                '        name: postgresql',
                '        state: started',
                '        enabled: yes',
                '',
            ])
        
        elif req.type == "package":
            # Generic package installation
            pkg_name = req.properties.get("package", "build-essential") if req.properties else "build-essential"
            lines.extend([
                f'    - name: Install {pkg_name}',
                f'      apt:',
                f'        name: {pkg_name}',
                f'        state: {req.state}',
                f'      when: ansible_os_family == "Debian"',
                f'',
            ])

    # Ensure deployer user with passwordless sudo, nginx page, and UFW rules
    lines.extend([
        '',
        '    - name: Ensure deployer user exists',
        '      user:',
        '        name: deployer',
        '        state: present',
        '',
        '    - name: Allow deployer passwordless sudo',
        '      copy:',
        '        dest: /etc/sudoers.d/deployer',
        '        content: "deployer ALL=(ALL) NOPASSWD:ALL\n"',
        '        mode: "0440"',
        '',
        '    - name: Install Nginx',
        '      apt:',
        '        name: nginx',
        '        state: present',
        '      when: ansible_os_family == "Debian"',
        '',
        '    - name: Start Nginx service',
        '      service:',
        '        name: nginx',
        '        state: started',
        '        enabled: yes',
        '',
        '    - name: Deploy simple HTML page',
        '      copy:',
        '        dest: /var/www/html/index.html',
        '        content: "<html><body><h1>Hostname: {{ ansible_hostname }}</h1></body></html>"',
        '        mode: "0644"',
        '',
        '    - name: Install UFW',
        '      apt:',
        '        name: ufw',
        '        state: present',
        '      when: ansible_os_family == "Debian"',
        '',
        '    - name: Allow SSH 22',
        '      ufw:',
        '        rule: allow',
        '        port: "22"',
        '',
        '    - name: Allow HTTP 80',
        '      ufw:',
        '        rule: allow',
        '        port: "80"',
        '',
        '    - name: Enable UFW',
        '      ufw:',
        '        state: enabled',
        '        policy: allow',
    ])
    
    return '\n'.join(lines)


def generate_inventory_from_terraform_outputs(
    terraform_outputs: Dict[str, Any],
    ssh_user: str = "ubuntu",
    group_name: str = "created_instances"
) -> str:
    """
    Generate Ansible inventory from Terraform outputs
    
    Input: {
        "instance_ips": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
        "ssh_key_name": "deployer-key-abc123",
        ...
    }
    
    Output: Ansible inventory INI format
    """
    
    lines = [
        f'# Auto-generated Ansible inventory',
        f'# Generated from Terraform outputs',
        f'',
        f'[{group_name}]',
    ]
    
    instance_ips = terraform_outputs.get("instance_ips", [])
    ssh_key_name = terraform_outputs.get("ssh_key_name", "deployer-key")
    ssh_key_path = terraform_outputs.get("ssh_key_path") or f'ansible/keys/{ssh_key_name}.pem'
    
    for idx, ip in enumerate(instance_ips, start=1):
        lines.append(
            f'instance{idx} ansible_host={ip} '
            f'ansible_user={ssh_user} '
            f'ansible_ssh_private_key_file={ssh_key_path}'
        )
    
    lines.extend([
        '',
        '[created_instances:vars]',
        'ansible_python_interpreter=/usr/bin/python3',
        'ansible_ssh_common_args=-o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null',
        '',
    ])
    
    return '\n'.join(lines)


def generate_verification_tests(verify_requirements: List) -> Dict[str, str]:
    """
    Generate verification tests from verification requirements
    
    Input: [
        VerifyReq(type="http", ...) objects or dicts
    ]
    
    Output: {"verify.sh": "..."}
    """
    
    verify_reqs = []
    for req in verify_requirements:
        if isinstance(req, dict):
            verify_reqs.append(VerifyReq(**req))
        else:
            # Already a VerifyReq object
            verify_reqs.append(req)
    
    script_content = _generate_verification_script(verify_reqs)
    
    return {
        "verify.sh": script_content
    }


def _generate_verification_script(verify_reqs: List[VerifyReq]) -> str:
    """Generate shell script for verification"""
    
    lines = [
        '#!/bin/bash',
        '# Auto-generated verification script',
        '',
        'set -e',
        '',
        'echo "Starting verification tests..."',
        '',
    ]
    
    for req in verify_reqs:
        if req.type == "http":
            port = req.port or 80
            lines.extend([
                f'echo "Testing HTTP on port {port}..."',
                f'for ip in "$@"; do',
                f'  curl -I http://$ip:{port}/ && echo " HTTP {port} is responding on $ip" || echo " HTTP {port} FAILED on $ip"',
                f'done',
                f'',
            ])
        
        elif req.type == "ssh":
            port = req.port or 22
            lines.extend([
                f'echo "Testing SSH on port {port}..."',
                f'for ip in "$@"; do',
                f'  nc -zv -w5 $ip {port} && echo " SSH port {port} is open on $ip" || echo " SSH port {port} FAILED on $ip"',
                f'done',
                f'',
            ])
    
    lines.extend([
        'echo "Verification complete!"',
        '',
    ])
    
    return '\n'.join(lines)
