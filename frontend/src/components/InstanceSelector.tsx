import React, { useState } from "react";
import {
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Typography,
  Divider,
  Chip,
} from "@mui/material";

export interface AvailableInstance {
  id: number;
  instance_id: string;
  name: string;
  public_ip?: string;
  provider?: string;
  region?: string;
  status?: string;
  ssh_user?: string;
  connection_method?: string;
  ssm_managed?: boolean;
}

interface InstanceSelectorProps {
  availableInstances: AvailableInstance[];
  onConfirm: (selectedIds: number[]) => void;
  onCancel?: () => void;
  originalText?: string;
  title?: string;
}

export const InstanceSelector: React.FC<InstanceSelectorProps> = ({
  availableInstances,
  onConfirm,
  onCancel,
  originalText,
  title = "Sélectionner des instances",
}) => {
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const handleToggle = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id)
        ? prev.filter((selectedId) => selectedId !== id)
        : [...prev, id],
    );
  };

  const handleToggleAll = () => {
    if (selectedIds.length === availableInstances.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(availableInstances.map((inst) => inst.id));
    }
  };

  const handleConfirm = () => {
    onConfirm(selectedIds);
  };

  const allChecked =
    availableInstances.length > 0 &&
    selectedIds.length === availableInstances.length;
  const someChecked =
    selectedIds.length > 0 && selectedIds.length < availableInstances.length;

  const getStatusColor = (status?: string): string => {
    const colors: Record<string, string> = {
      running: "success",
      stopped: "error",
      pending: "warning",
    };
    return colors[status || ""] || "default";
  };

  return (
    <Paper elevation={2} sx={{ p: 3, maxWidth: 700, mx: "auto" }}>
      {/* Title */}
      <Typography variant="h6" gutterBottom>
        {title}
      </Typography>

      {originalText && (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mb: 2, fontStyle: "italic" }}
        >
          Demande: "{originalText}"
        </Typography>
      )}

      {/* Select All Checkbox */}
      <FormControlLabel
        control={
          <Checkbox
            checked={allChecked}
            indeterminate={someChecked}
            onChange={handleToggleAll}
          />
        }
        label={`Tout sélectionner (${selectedIds.length}/${availableInstances.length})`}
      />

      <Divider sx={{ my: 2 }} />

      {/* Instances List */}
      <Box sx={{ maxHeight: 400, overflow: "auto", mb: 2 }}>
        {availableInstances.length === 0 ? (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ p: 2, textAlign: "center" }}
          >
            Aucune instance disponible
          </Typography>
        ) : (
          <List dense>
            {availableInstances.map((instance) => (
              <ListItem
                key={instance.id}
                disablePadding
                sx={{
                  borderRadius: 1,
                  mb: 1,
                  bgcolor: selectedIds.includes(instance.id)
                    ? "action.selected"
                    : "transparent",
                }}
              >
                <ListItemButton onClick={() => handleToggle(instance.id)}>
                  <ListItemIcon>
                    <Checkbox
                      edge="start"
                      checked={selectedIds.includes(instance.id)}
                      tabIndex={-1}
                      disableRipple
                    />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Box
                        sx={{ display: "flex", alignItems: "center", gap: 1 }}
                      >
                        <Typography variant="body1" fontWeight="500">
                          {instance.name}
                        </Typography>
                        {instance.status && (
                          <Chip
                            label={instance.status}
                            size="small"
                            color={getStatusColor(instance.status) as any}
                          />
                        )}
                        {instance.ssm_managed && (
                          <Chip
                            label="SSM"
                            size="small"
                            color="info"
                            variant="outlined"
                          />
                        )}
                      </Box>
                    }
                    secondary={
                      <Typography
                        variant="caption"
                        component="div"
                        sx={{ mt: 0.5 }}
                      >
                        <strong>ID:</strong> {instance.instance_id}
                        {instance.public_ip && (
                          <>
                            {" "}
                            • <strong>IP:</strong> {instance.public_ip}
                          </>
                        )}
                        {instance.region && (
                          <>
                            {" "}
                            • <strong>Région:</strong> {instance.region}
                          </>
                        )}
                        {instance.ssh_user && (
                          <>
                            {" "}
                            • <strong>User:</strong> {instance.ssh_user}
                          </>
                        )}
                      </Typography>
                    }
                  />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        )}
      </Box>

      {/* Action Buttons */}
      <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
        {onCancel && (
          <Button variant="outlined" color="secondary" onClick={onCancel}>
            Annuler
          </Button>
        )}
        <Button
          variant="contained"
          color="primary"
          disabled={selectedIds.length === 0}
          onClick={handleConfirm}
        >
          Confirmer ({selectedIds.length})
        </Button>
      </Box>
    </Paper>
  );
};
