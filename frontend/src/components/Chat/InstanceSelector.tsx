import {
  Checkbox,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Typography,
  Button,
  Stack,
  Box,
  Chip,
  Paper,
} from "@mui/material";
import { useState } from "react";
import axiosClient from "../../api/axiosClient";

interface Instance {
  id: number;
  name: string;
  public_ip: string;
  provider: string;
  region: string;
  status: string;
  ssh_user: string;
  ip?: string;
  private_ip?: string;
  connection_method?: string; //  ÉTAPE 1-5: ssh ou ssm
  ssm_managed?: boolean; //  ÉTAPE 1-5: true si SSM possible
  instance_id?: string; // AWS instance_id (i-xxx)
}

interface InstanceSelectorProps {
  instances: Instance[];
  onConfirm: (selected: number[]) => void;
  originalText?: string;
  onCancel?: () => void;
  state?: string; // ÉTAPE 4: état pour déterminer l'action
  sessionId?: number; // ÉTAPE 4: pour payload
  chatId?: number; // ÉTAPE 4: pour payload
  onResponse?: (data: any) => void; // OK réponse backend pour mise à jour UI immédiate
}

export default function InstanceSelector({
  instances,
  onConfirm,
  originalText,
  onCancel,
  state,
  sessionId,
  chatId,
  onResponse,
}: InstanceSelectorProps) {
  const [selected, setSelected] = useState<number[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const getInstanceId = (inst: Instance): number | null => {
    if (typeof inst.id === "number" && Number.isFinite(inst.id)) return inst.id;
    const fromString = Number((inst as any).id);
    if (Number.isFinite(fromString) && fromString > 0) return fromString;
    const fromInstanceId = Number(inst.instance_id);
    if (Number.isFinite(fromInstanceId) && fromInstanceId > 0)
      return fromInstanceId;
    return null;
  };

  const hasSSM = instances.some((i) => i.ssm_managed);

  // ÉTAPE 4: Mapper le state à l'action
  const getActionForState = (st?: string): string => {
    switch (st) {
      case "awaiting_instance_selection":
        return "confirm_instances";
      case "awaiting_audit_instance_selection":
        return "confirm_audit_instances";
      case "awaiting_monitoring_instance_selection":
        return "confirm_monitoring_instances";
      default:
        return "confirm_instances"; // fallback
    }
  };

  // ÉTAPE 4: Envoyer le payload au backend
  const handleConfirm = async () => {
    if (selected.length === 0) return;

    // Appeler onConfirm local d'abord (pour compatibilité)
    onConfirm(selected);

    // ÉTAPE A: Envoyer le payload à /chat_creation/chat_message avec action
    if (sessionId !== undefined && chatId !== undefined && state) {
      try {
        setIsLoading(true);
        const action = getActionForState(state);

        const payload = {
          session_id: sessionId,
          chat_id: chatId,
          sender: "user",
          text: "", // ÉTAPE A: Pas de JSON, pas de texte (action UI pure)
          action, // Action déterminée par le state
          selected_instances: selected, // IDs DB (Instance.id)
        };

        console.log("[InstanceSelector] Sending payload:", payload);

        const res = await axiosClient.post(
          "/chat_creation/chat_message",
          payload,
        );

        if (onResponse) {
          onResponse(res.data);
        }

        console.log("[InstanceSelector] Confirmation sent successfully");
      } catch (err) {
        console.error("[InstanceSelector] Error sending confirmation:", err);

        // Extraire le message d'erreur détaillé
        const errorDetail =
          (err as any)?.response?.data?.detail ||
          (err as any)?.response?.data?.message ||
          (err as any)?.message ||
          "Erreur inconnue";

        // Afficher l'erreur dans la réponse callback si disponible
        if (onResponse) {
          onResponse({
            status: "error",
            error: errorDetail,
            message: `ERR Erreur lors de l'envoi de la sélection: ${errorDetail}`,
          });
        }

        // Ne pas bloquer l'UI, mais log l'erreur
      } finally {
        setIsLoading(false);
      }
    }
  };

  const toggle = (id: number | null) => {
    if (!id || !Number.isFinite(id)) return;
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id],
    );
  };

  const toggleAll = () => {
    const allIds = instances
      .map(getInstanceId)
      .filter((id): id is number => typeof id === "number");
    if (selected.length === allIds.length) {
      setSelected([]);
    } else {
      setSelected(allIds);
    }
  };

  const statusColors: Record<string, string> = {
    running: "#4caf50",
    stopped: "#f44336",
    pending: "#ff9800",
    unknown: "#9e9e9e",
  };

  // ÉTAPE D: Déterminer le type d'action et les labels dynamiques
  const getIntentInfo = (st?: string) => {
    switch (st) {
      case "awaiting_audit_instance_selection":
        return {
          title: "Sélectionne les VM à auditer",
          description: "Audit de santé opérationnelle et sécurité",
          ctaText: (count: number) =>
            `Auditer ${count > 1 ? count + " VMs" : "1 VM"}`,
        };
      case "awaiting_monitoring_instance_selection":
        return {
          title: "Sélectionne les VM à monitorer",
          description: "Surveillance des performances et alertes",
          ctaText: (count: number) =>
            `Monitorer ${count > 1 ? count + " VMs" : "1 VM"}`,
        };
      case "awaiting_instance_selection":
      default:
        return {
          title: "Sélectionne les VM à configurer",
          description: "Configuration des systèmes et applications",
          ctaText: (count: number) =>
            `Configurer ${count > 1 ? count + " VMs" : "1 VM"}`,
        };
    }
  };

  const intentInfo = getIntentInfo(state);

  return (
    <Stack spacing={3} sx={{ width: "100%", maxWidth: 600 }}>
      <Box>
        <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
          {intentInfo.title}
        </Typography>
        <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
          {intentInfo.description}
        </Typography>
        {originalText && (
          <Typography
            variant="body2"
            color="textSecondary"
            sx={{ fontStyle: "italic" }}
          >
            Demande: <strong>"{originalText}"</strong>
          </Typography>
        )}
        {!hasSSM && (
          <Paper
            variant="outlined"
            sx={{ mt: 1.5, p: 2, bgcolor: "#f5f8ff", borderColor: "#c5d2f5" }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
              SSM-first mode activé
            </Typography>
            <Typography
              variant="body2"
              sx={{ whiteSpace: "pre-line", color: "#1f2a44" }}
            >
              DAC exécute les actions système via AWS Systems Manager (SSM) afin
              d’éviter SSH et les clés privées. Aucune instance SSM Online n’a
              été détectée. Pour rendre une VM gérable : – attachez un rôle IAM
              AmazonSSMManagedInstanceCore – assurez la connectivité SSM (NAT ou
              VPC Endpoints) – puis relancez la synchronisation.
            </Typography>
          </Paper>
        )}
        {/*  Message clair du nombre de VMs */}
        {selected.length > 0 && (
          <Typography
            variant="body2"
            sx={{
              mt: 1,
              p: 1,
              bgcolor: "info.lighter",
              borderRadius: 1,
              color: "info.darker",
              fontWeight: 500,
            }}
          >
            Cette configuration sera appliquée sur{" "}
            <strong>{selected.length}</strong>{" "}
            {selected.length === 1 ? "VM" : "VMs"}
          </Typography>
        )}
      </Box>

      <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
        <Button
          size="small"
          variant="outlined"
          onClick={toggleAll}
          sx={{ flex: 1 }}
        >
          {selected.length === instances.length
            ? " Désélectionner tout"
            : " Sélectionner tout"}
        </Button>
        <Chip
          label={`${selected.length} / ${instances.length}`}
          color={selected.length > 0 ? "primary" : "default"}
          variant="outlined"
        />
      </Box>

      <Paper variant="outlined" sx={{ maxHeight: 400, overflow: "auto" }}>
        <List disablePadding>
          {instances.length === 0 ? (
            <ListItem>
              <Typography variant="body2" color="textSecondary">
                Aucune instance disponible.
              </Typography>
            </ListItem>
          ) : (
            instances.map((inst) => {
              const instId = getInstanceId(inst);
              const isSelected = instId ? selected.includes(instId) : false;
              return (
                <ListItem
                  key={instId ?? inst.instance_id ?? inst.name}
                  onClick={() => toggle(instId)}
                  component="div"
                  sx={{
                    cursor: "pointer",
                    bgcolor: isSelected ? "action.hover" : "transparent",
                    borderLeft: isSelected
                      ? "4px solid"
                      : "4px solid transparent",
                    borderLeftColor: "primary.main",
                    transition: "all 0.2s",
                    "&:hover": {
                      bgcolor: "action.hover",
                    },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 40 }}>
                    <Checkbox
                      checked={isSelected}
                      onChange={() => toggle(instId)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </ListItemIcon>
                  <Box sx={{ width: "100%" }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <strong>{inst.name}</strong>
                      <Chip
                        label={inst.status}
                        size="small"
                        sx={{
                          backgroundColor:
                            statusColors[inst.status] || statusColors.unknown,
                          color: "white",
                          height: 20,
                          fontSize: "0.7rem",
                        }}
                      />
                      {/*  Badge SSM (recommandé) ou SSH */}
                      <Chip
                        label={inst.ssm_managed ? "SSM (recommandé)" : "SSH"}
                        size="small"
                        variant="outlined"
                        sx={{
                          backgroundColor: inst.ssm_managed
                            ? "#e3f2fd"
                            : "transparent",
                          borderColor: inst.ssm_managed ? "#1976d2" : "#ccc",
                          color: inst.ssm_managed ? "#1976d2" : "#666",
                          height: 20,
                          fontSize: "0.7rem",
                          fontWeight: 600,
                        }}
                      />
                    </Box>
                    <Box
                      sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 2 }}
                    >
                      <Typography variant="caption">
                         <code>{inst.public_ip}</code>
                      </Typography>
                      <Typography variant="caption">
                         {inst.provider.toUpperCase()}
                      </Typography>
                      <Typography variant="caption">
                         {inst.region}
                      </Typography>
                      <Typography variant="caption">
                         {inst.ssh_user}
                      </Typography>
                    </Box>
                  </Box>
                </ListItem>
              );
            })
          )}
        </List>
      </Paper>

      <Stack direction="row" spacing={2} justifyContent="flex-end">
        {onCancel && (
          <Button variant="outlined" onClick={onCancel} disabled={isLoading}>
            Annuler
          </Button>
        )}
        <Button
          variant="contained"
          color="success"
          onClick={handleConfirm}
          disabled={selected.length === 0 || isLoading}
        >
          {isLoading ? "Envoi..." : intentInfo.ctaText(selected.length)}
        </Button>
      </Stack>
    </Stack>
  );
}
