# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

"""
Understanding Display - Affiche ce que DAC a compris
Réduit les "il comprend pas" par 100x
"""

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class UnderstandingDisplay:
    """Ce que DAC a compris du message utilisateur"""
    intent: str  # "configure", "create", "audit", "monitoring", "free_chat"
    action: Optional[str] = None  # "install_nginx", etc. ou None
    targets: Optional[List[str]] = None  # ["i-xxx", "i-yyy"] ou None (en attente)
    
    def to_text(self) -> str:
        """Retourne une ligne discrète pour affichage"""
        parts = [f"**Intent**: {self.intent}"]
        
        if self.action:
            parts.append(f"**Action**: {self.action}")
        
        if self.targets:
            target_str = ", ".join(self.targets[:3])
            if len(self.targets) > 3:
                target_str += f" (+{len(self.targets)-3})"
            parts.append(f"**Cibles**: {target_str}")
        elif self.intent == "configure" and self.action:
            parts.append("**Cibles**: en attente")
        
        return " | ".join(parts)
    
    def to_dict(self):
        return {
            "intent": self.intent,
            "action": self.action,
            "targets": self.targets or [],
        }
