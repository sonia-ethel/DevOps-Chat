// src/states/chatStates.ts

export type ChatState =
  | "awaiting_provider"
  | "awaiting_credentials"
  | "awaiting_confirmation"
  | "awaiting_smart_confirmation"
  | "awaiting_intent"
  | "awaiting_inventory"
  | "awaiting_instance_selection"
  | "awaiting_instances"
  | "awaiting_execution"
  | "awaiting_audit_tool"
  | "deletion_mode"
  | "free_chat"
  | "ready"
  | "executing"
  | "deployed"
  | "completed"
  | "error";

export const CHAT_STATE_LABELS: Record<ChatState, string> = {
  awaiting_provider: "Choix du provider",
  awaiting_credentials: "Configuration des identifiants",
  awaiting_intent: "En attente d'instructions",
  awaiting_confirmation: "Confirmation utilisateur",
  awaiting_smart_confirmation: "Confirmation de déploiement",
  awaiting_inventory: "Sélection des instances",
  awaiting_instance_selection: "Sélection des instances",
  awaiting_instances: "Sélection des instances",
  awaiting_execution: "Prêt pour l'exécution",
  awaiting_audit_tool: "Choix de l'outil d'audit",
  deletion_mode: "Mode suppression",
  free_chat: "Chat libre",
  ready: "Prêt à exécuter",
  executing: "Déploiement en cours",
  deployed: "Déployé avec succès",
  completed: "Opération terminée",
  error: "Erreur détectée",
};

//  Couleurs associées aux états pour l'interface
export const CHAT_STATE_COLORS: Record<ChatState, string> = {
  awaiting_provider: "#f59e0b", // amber
  awaiting_credentials: "#f59e0b", // amber
  awaiting_intent: "#10b981", // emerald
  awaiting_confirmation: "#3b82f6", // blue
  awaiting_smart_confirmation: "#6366f1", // indigo
  awaiting_inventory: "#8b5cf6", // violet
  awaiting_instance_selection: "#8b5cf6", // violet
  awaiting_instances: "#8b5cf6", // violet
  awaiting_execution: "#06b6d4", // cyan
  awaiting_audit_tool: "#f97316", // orange
  deletion_mode: "#dc2626", // red
  free_chat: "#22c55e", // green
  ready: "#06b6d4", // cyan
  executing: "#f59e0b", // amber (loading)
  deployed: "#10b981", // emerald
  completed: "#10b981", // emerald
  error: "#ef4444", // red
};
