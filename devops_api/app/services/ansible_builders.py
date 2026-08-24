# app/services/ansible_builders.py
from app.utils.file_utils import create_and_store_playbook

SYSTEM_SERVICE_YML = """---
- hosts: all
  gather_facts: true
  become: true
  tasks:
    - name: Debian/Ubuntu | Update apt cache
      ansible.builtin.apt:
        update_cache: true
      when: ansible_os_family == "Debian"

    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present

    - name: Ensure nginx is running
      ansible.builtin.service:
        name: nginx
        state: started
        enabled: true
"""

def build_system_service(user_id: int, session_id: int) -> dict:
    filename = f"system_service_{session_id}.yml"
    pb = create_and_store_playbook(
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        content=SYSTEM_SERVICE_YML
    )
    return {"file_id": pb.id, "path": pb.file_path}
