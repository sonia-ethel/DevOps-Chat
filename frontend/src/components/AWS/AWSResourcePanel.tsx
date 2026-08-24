// src/components/AWS/AWSResourcePanel.tsx

import React, { useEffect } from 'react';
import {
  Box,
  Drawer,
  Typography,
  IconButton,
  Card,
  CardContent,
  Button,
  Chip,
  Alert,
  CircularProgress,
  Tooltip,
  Divider,
  Badge,
} from '@mui/material';
import {
  Cloud as CloudIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  Close as CloseIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import { useAWSInstances } from '../../hooks/useAWSInstances';

interface AWSResourcePanelProps {
  open: boolean;
  onClose: () => void;
  sessionId: number | null;
}

const AWSResourcePanel: React.FC<AWSResourcePanelProps> = ({
  open,
  onClose,
  sessionId,
}) => {
  //  Hook personnalisé pour la gestion des instances
  const {
    instances,
    loading,
    error,
    deleting,
    refreshInstances,
    deleteInstance,
    clearError,
  } = useAWSInstances(sessionId);

  //  Refresh quand le panel s'ouvre
  useEffect(() => {
    if (open && sessionId) {
      refreshInstances();
    }
  }, [open, sessionId, refreshInstances]);

  //  Couleur du status
  const getStatusColor = (state?: string) => {
    switch (state) {
      case 'running': return 'success';
      case 'stopped': return 'error';
      case 'pending': return 'warning';
      default: return 'default';
    }
  };

  //  Icône du status
  const getStatusIcon = (state?: string) => {
    switch (state) {
      case 'running': return '';
      case 'stopped': return '';
      case 'pending': return '';
      default: return '';
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      sx={{
        '& .MuiDrawer-paper': {
          width: 400,
          bgcolor: 'background.paper',
        },
      }}
    >
      {/*  Header */}
      <Box
        sx={{
          p: 2,
          borderBottom: '1px solid',
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          bgcolor: 'primary.main',
          color: 'primary.contrastText',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CloudIcon />
          <Typography variant="h6" fontWeight="bold">
            AWS Instances
          </Typography>
          <Badge badgeContent={instances.length} color="secondary" />
        </Box>
        <IconButton onClick={onClose} sx={{ color: 'inherit' }}>
          <CloseIcon />
        </IconButton>
      </Box>

      {/*  Actions */}
      <Box sx={{ p: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Button
          variant="contained"
          startIcon={<RefreshIcon />}
          onClick={refreshInstances}
          disabled={loading}
          fullWidth
          sx={{ mb: 1 }}
        >
          {loading ? 'Actualisation...' : 'Actualiser'}
        </Button>
        
        {error && (
          <Alert severity="error" sx={{ mt: 1 }} onClose={clearError}>
            {error}
          </Alert>
        )}
      </Box>

      {/*  Liste des instances */}
      <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
        {loading ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CircularProgress />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Chargement des instances...
            </Typography>
          </Box>
        ) : instances.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CloudIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
            <Typography variant="body1" color="text.secondary">
              Aucune instance AWS trouvée
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Créez votre première instance via le chat
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {instances.map((instance) => (
              <Card
                key={instance.instance_id}
                sx={{
                  border: '1px solid',
                  borderColor: 'divider',
                  '&:hover': {
                    boxShadow: 2,
                  },
                }}
              >
                <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                  {/* Instance ID + Status */}
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    <Typography
                      variant="body2"
                      fontFamily="monospace"
                      sx={{ 
                        flex: 1,
                        fontSize: '0.85rem',
                        fontWeight: 'medium',
                      }}
                    >
                      {getStatusIcon(instance.state)} {instance.instance_id}
                    </Typography>
                    <Chip
                      label={instance.state || 'unknown'}
                      size="small"
                      color={getStatusColor(instance.state)}
                      variant="outlined"
                    />
                  </Box>

                  {/* IP Addresses */}
                  {instance.public_ip && (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ mb: 0.5 }}
                    >
                       IP Publique: {instance.public_ip}
                    </Typography>
                  )}
                  {instance.private_ip && (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ mb: 1 }}
                    >
                       IP Privée: {instance.private_ip}
                    </Typography>
                  )}

                  {/* Provider + Source */}
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                    <Chip
                      label={instance.provider?.toUpperCase() || 'AWS'}
                      size="small"
                      variant="filled"
                      color="primary"
                    />
                    <Chip
                      label={instance.source === 'cloud_api' ? 'Live' : 'Cached'}
                      size="small"
                      variant="outlined"
                      color={instance.source === 'cloud_api' ? 'success' : 'default'}
                    />
                  </Box>

                  <Divider sx={{ my: 1 }} />

                  {/* Actions */}
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <Tooltip title="Supprimer cette instance définitivement">
                      <Button
                        variant="outlined"
                        color="error"
                        size="small"
                        startIcon={
                          deleting.has(instance.instance_id) ? (
                            <CircularProgress size={16} />
                          ) : (
                            <DeleteIcon />
                          )
                        }
                        onClick={() => deleteInstance(instance.instance_id)}
                        disabled={deleting.has(instance.instance_id)}
                        sx={{ flex: 1 }}
                      >
                        {deleting.has(instance.instance_id) ? 'Suppression...' : 'Supprimer'}
                      </Button>
                    </Tooltip>
                  </Box>
                </CardContent>
              </Card>
            ))}
          </Box>
        )}
      </Box>

      {/*  Warning Footer */}
      <Box
        sx={{
          p: 2,
          borderTop: '1px solid',
          borderColor: 'divider',
          bgcolor: 'warning.light',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <WarningIcon color="warning" fontSize="small" />
          <Typography variant="caption" color="warning.dark">
            La suppression est <strong>définitive</strong> et supprime l'instance du cloud AWS.
          </Typography>
        </Box>
      </Box>
    </Drawer>
  );
};

export default AWSResourcePanel;