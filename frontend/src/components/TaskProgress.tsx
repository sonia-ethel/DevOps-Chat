// src/components/TaskProgress.tsx

import React from 'react';
import { 
  Box, 
  LinearProgress, 
  Typography, 
  Card, 
  CardContent,
  List,
  ListItem,
  ListItemText,
  Chip,
  Alert,
  Button,
  Collapse,
  IconButton,
  Stepper,
  Step,
  StepLabel,
  Skeleton,
  Fade,
  Grow
} from '@mui/material';
import { 
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Pending as PendingIcon,
  PlayArrow as PlayArrowIcon,
  ExpandLess as ExpandLessIcon,
  Refresh as RefreshIcon,
  Circle as CircleIcon
} from '@mui/icons-material';
import { useTaskPolling, type TaskLog } from '../hooks/useTaskPolling';
import { 
  AWS_DEPLOYMENT_STEPS,
  getCurrentStep,
  getCurrentStepIndex,
  getStepProgress,
  mapBackendMessageToStep
} from '../utils/deploymentSteps';

interface TaskProgressProps {
  taskId: string;
  onComplete?: (result: any) => void;
  onError?: (error: string) => void;
  showLogs?: boolean;
  compact?: boolean;
}

const TaskProgress: React.FC<TaskProgressProps> = ({
  taskId,
  onComplete,
  onError,
  showLogs = true,
  compact = false
}) => {
  const [showDetailedLogs, setShowDetailedLogs] = React.useState(true); // Logs visibles par défaut
  
  const {
    taskStatus,
    timeoutReached,
    progressPercentage,
    currentStep,
    logs,
    refreshStatus,
    // Nouveaux états pour l'amélioration UX
    connectionState
  } = useTaskPolling(taskId, {
    onComplete,
    onError,
    onStatusChange: (status) => {
      console.log('Task status updated:', status);
    }
  });


  // Fonction pour obtenir l'icône selon le statut global
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending':
        return <PendingIcon color="warning" />;
      case 'running':
        return <PlayArrowIcon color="primary" />;
      case 'completed':
        return <CheckCircleIcon color="success" />;
      case 'failed':
        return <ErrorIcon color="error" />;
      case 'cancelled':
        return <ErrorIcon color="disabled" />;
      default:
        return <PendingIcon />;
    }
  };

  // Fonction pour obtenir la couleur selon le statut
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending':
        return 'warning';
      case 'running':
        return 'primary';
      case 'completed':
        return 'success';
      case 'failed':
        return 'error';
      case 'cancelled':
        return 'default';
      default:
        return 'default';
    }
  };

  // Fonction pour formater le timestamp
  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString('fr-FR');
  };

  // Fonction pour obtenir la couleur du log selon le niveau
  const getLogColor = (level: string) => {
    switch (level) {
      case 'error':
        return '#f44336';
      case 'warning':
        return '#ff9800';
      case 'success':
        return '#4caf50';
      default:
        return '#2196f3';
    }
  };

  // Composant pour l'état de chargement initial uniquement
  const LoadingState = () => {
    // Simple skeleton loading - pas d'indicateurs de connexion
    return (
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={2} mb={2}>
            <Skeleton variant="circular" width={40} height={40} />
            <Box flex={1}>
              <Skeleton variant="text" width="60%" height={28} />
              <Skeleton variant="text" width="40%" height={20} />
            </Box>
          </Box>
          <Skeleton variant="rectangular" height={8} sx={{ borderRadius: 1 }} />
        </CardContent>
      </Card>
    );
  };

  // Show loading state only on very first load
  if (!taskStatus) {
    return <LoadingState />;
  }

  if (compact) {
    return (
      <Box display="flex" alignItems="center" gap={1} py={1}>
        {getStatusIcon(taskStatus.status || '')}
        <Box flex={1}>
          <Typography variant="body2">{currentStep}</Typography>
          <LinearProgress 
            variant="determinate" 
            value={progressPercentage} 
            color={getStatusColor(taskStatus.status || '') as any}
            sx={{ mt: 0.5 }}
          />
        </Box>
        <Typography variant="caption" color="textSecondary">
          {Math.round(progressPercentage)}%
        </Typography>
      </Box>
    );
  }

  return (
    <Card 
      variant="outlined" 
      sx={{ 
        mb: 2,
        transition: 'all 0.3s ease-in-out',
        '&:hover': {
          boxShadow: 2
        },
        '@keyframes pulse': {
          '0%': { opacity: 1 },
          '50%': { opacity: 0.8 },
          '100%': { opacity: 1 }
        },
        '@keyframes slideIn': {
          '0%': { opacity: 0, transform: 'translateY(10px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' }
        },
        animation: 'slideIn 0.4s ease-out'
      }}
    >
      <CardContent>
        {/* Connection status banner removed - users shouldn't see connection issues */}

        {/* Enhanced Header avec statut */}
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
          <Box display="flex" alignItems="center" gap={2}>
            {getStatusIcon(taskStatus.status || '')}
            <Box>
              <Typography variant="h6" fontWeight={700}>
                Tâche {taskStatus.task_type}
              </Typography>
              <Box display="flex" alignItems="center" gap={1} mt={0.5}>
                <Chip 
                  label={taskStatus.status?.toUpperCase() || 'UNKNOWN'} 
                  color={getStatusColor(taskStatus.status || '') as any}
                  size="small"
                />
                {taskStatus.status === 'running' && (
                  <Typography variant="caption" color="text.secondary">
                    • Durée estimée: 2-3 minutes
                  </Typography>
                )}
                {taskStatus.status === 'pending' && (
                  <Typography variant="caption" color="text.secondary">
                    • Démarrage imminent...
                  </Typography>
                )}
              </Box>
            </Box>
          </Box>
          
          <Box display="flex" alignItems="center" gap={1}>
            {/* Connection indicators removed - focus on task progress only */}
            <Button 
              size="small" 
              onClick={refreshStatus} 
              startIcon={<RefreshIcon />}
              sx={{ minWidth: 'auto' }}
              disabled={connectionState === 'connecting'}
            >
              Actualiser
            </Button>
          </Box>
        </Box>

        {/* Enhanced Progress Section avec Stepper AWS */}
        {taskStatus.status === 'running' && (
          <Fade in={true}>
            <Box mb={3}>
              {/* Stepper horizontal pour les étapes AWS */}
              <Stepper activeStep={getCurrentStepIndex(progressPercentage)} alternativeLabel sx={{ mb: 3 }}>
                {AWS_DEPLOYMENT_STEPS.map((step) => {
                  const isActive = progressPercentage >= step.progressRange[0] && progressPercentage <= step.progressRange[1];
                  const isCompleted = progressPercentage > step.progressRange[1];
                  const StepIcon = step.icon;
                  
                  return (
                    <Step key={step.id} completed={isCompleted}>
                      <StepLabel 
                        icon={
                          isCompleted ? (
                            <CheckCircleIcon color="success" sx={{ fontSize: 24 }} />
                          ) : isActive ? (
                            <StepIcon color="primary" sx={{ fontSize: 24 }} />
                          ) : (
                            <CircleIcon color="disabled" sx={{ fontSize: 24 }} />
                          )
                        }
                        sx={{
                          '& .MuiStepLabel-label': {
                            fontSize: '0.75rem',
                            fontWeight: isActive ? 600 : 400,
                            color: isActive ? 'primary.main' : isCompleted ? 'success.main' : 'text.secondary'
                          }
                        }}
                      >
                        {step.label}
                        {isActive && (
                          <Typography variant="caption" display="block" color="text.secondary">
                            {step.estimatedDuration}
                          </Typography>
                        )}
                      </StepLabel>
                    </Step>
                  );
                })}
              </Stepper>

              {/* Détail de l'étape courante */}
              {(() => {
                const currentStepData = getCurrentStep(progressPercentage) || mapBackendMessageToStep(currentStep, '');
                if (currentStepData) {
                  const stepProgress = getStepProgress(progressPercentage, currentStepData);
                  const StepIcon = currentStepData.icon;
                  
                  return (
                    <Grow in={true}>
                      <Card variant="outlined" sx={{ bgcolor: 'primary.50', borderColor: 'primary.200' }}>
                        <CardContent sx={{ py: 2 }}>
                          <Box display="flex" alignItems="center" gap={2} mb={2}>
                            <StepIcon color="primary" sx={{ fontSize: 28 }} />
                            <Box flex={1}>
                              <Typography variant="h6" color="primary.main" fontWeight={700}>
                                {currentStepData.label}
                              </Typography>
                              <Typography variant="body2" color="text.secondary">
                                {currentStepData.description}
                              </Typography>
                              {currentStepData.estimatedDuration && (
                                <Typography variant="caption" color="text.secondary">
                                  Durée estimée: {currentStepData.estimatedDuration}
                                </Typography>
                              )}
                            </Box>
                            <Box textAlign="right">
                              <Typography variant="h5" color="primary.main" fontWeight={700}>
                                {Math.round(progressPercentage)}%
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                Étape: {Math.round(stepProgress)}%
                              </Typography>
                            </Box>
                          </Box>
                          
                          {/* Progress bar pour l'étape courante */}
                          <Box display="flex" gap={1}>
                            <LinearProgress 
                              variant="determinate" 
                              value={progressPercentage}
                              color="primary"
                              sx={{ 
                                flex: 1,
                                height: 6, 
                                borderRadius: 3,
                                bgcolor: 'primary.100',
                                '& .MuiLinearProgress-bar': {
                                  borderRadius: 3,
                                  transition: 'transform 0.8s ease-in-out'
                                }
                              }}
                            />
                          </Box>
                          
                          {/* Message détaillé du backend */}
                          {currentStep && (
                            <Typography variant="body2" color="text.secondary" sx={{ mt: 1, fontStyle: 'italic' }}>
                              "{currentStep}"
                            </Typography>
                          )}
                        </CardContent>
                      </Card>
                    </Grow>
                  );
                }
                return null;
              })()}
            </Box>
          </Fade>
        )}

        {/* Progress simple pour les états non-running */}
        {taskStatus.status !== 'running' && (
          <Box mb={2}>
            <Box display="flex" justifyContent="space-between" mb={1}>
              <Typography variant="body2" color="textSecondary">
                {currentStep || 'En attente...'}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                {Math.round(progressPercentage)}%
              </Typography>
            </Box>
            <LinearProgress 
              variant="determinate" 
              value={progressPercentage}
              color={getStatusColor(taskStatus.status || '') as any}
              sx={{ 
                height: 8, 
                borderRadius: 4,
                '& .MuiLinearProgress-bar': {
                  transition: 'transform 0.5s ease-in-out'
                }
              }}
            />
          </Box>
        )}

        {/* Gestion d'erreurs - seulement les vraies erreurs de tâche */}
        {taskStatus.error_message && (
          <Alert severity="error" sx={{ mb: 2 }}>
            <Typography variant="body2" fontWeight={600}>
              Erreur pendant l'exécution
            </Typography>
            <Typography variant="body2">
              {taskStatus.error_message}
            </Typography>
          </Alert>
        )}

        {/* Timeout warning */}
        {timeoutReached && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Timeout atteint. La tâche continue en arrière-plan.
          </Alert>
        )}

        {/* Timestamps */}
        <Box display="flex" gap={2} mb={2}>
          {taskStatus.created_at && (
            <Typography variant="caption" color="textSecondary">
              Créée: {formatTimestamp(taskStatus.created_at)}
            </Typography>
          )}
          {taskStatus.started_at && (
            <Typography variant="caption" color="textSecondary">
              Démarrée: {formatTimestamp(taskStatus.started_at)}
            </Typography>
          )}
          {taskStatus.completed_at && (
            <Typography variant="caption" color="textSecondary">
              Terminée: {formatTimestamp(taskStatus.completed_at)}
            </Typography>
          )}
        </Box>

        {/* Enhanced Logs section */}
        {showLogs && (
          <Box>
            <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
              <Box display="flex" alignItems="center" gap={1}>
                <Typography variant="subtitle2" fontWeight={600}>
                  Journal d'exécution
                </Typography>
                {logs.length > 0 && (
                  <Chip 
                    label={`${logs.length} entrées`} 
                    size="small" 
                    variant="outlined" 
                    color="info"
                  />
                )}
              </Box>
              <IconButton 
                size="small" 
                onClick={() => setShowDetailedLogs(!showDetailedLogs)}
                sx={{ 
                  transform: showDetailedLogs ? 'rotate(0deg)' : 'rotate(180deg)',
                  transition: 'transform 0.3s ease-in-out'
                }}
              >
                <ExpandLessIcon />
              </IconButton>
            </Box>
            
            <Collapse in={showDetailedLogs}>
              <Box sx={{ 
                bgcolor: 'background.paper', 
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 2,
                overflow: 'hidden'
              }}>
                {logs.length > 0 ? (
                  <List dense sx={{ 
                    maxHeight: 250,
                    overflow: 'auto',
                    '& .MuiListItem-root:nth-of-type(odd)': {
                      bgcolor: 'rgba(0, 0, 0, 0.02)'
                    }
                  }}>
                    {logs.slice(-10).map((log: TaskLog, index) => (
                      <ListItem key={`log-${log.timestamp}-${index}`} sx={{ py: 1, px: 2 }}>
                        <ListItemText
                          primary={
                            <Box display="flex" alignItems="center" gap={1}>
                              <Box
                                width={10}
                                height={10}
                                borderRadius="50%"
                                bgcolor={getLogColor(log.level)}
                                sx={{ 
                                  boxShadow: `0 0 0 2px ${getLogColor(log.level)}33`,
                                  animation: log.level === 'success' ? 'pulse 2s infinite' : 'none'
                                }}
                              />
                              <Typography variant="body2" sx={{ flex: 1 }}>
                                {log.message}
                              </Typography>
                              {log.progress_percentage && (
                                <Chip 
                                  label={`${Math.round(log.progress_percentage)}%`} 
                                  size="small" 
                                  variant="outlined"
                                  color="primary"
                                />
                              )}
                            </Box>
                          }
                          secondary={
                            <Box display="flex" alignItems="center" gap={1} mt={0.5}>
                              <Typography variant="caption" color="text.secondary">
                                {formatTimestamp(log.timestamp)}
                              </Typography>
                              {log.step_name && (
                                <Chip 
                                  label={log.step_name} 
                                  size="small" 
                                  variant="outlined"
                                  sx={{ height: 20, fontSize: '0.7rem' }}
                                />
                              )}
                            </Box>
                          }
                        />
                      </ListItem>
                    ))}
                  </List>
                ) : (
                  <Box py={4} textAlign="center">
                    <Typography variant="body2" color="text.secondary">
                      {taskStatus?.status === 'pending' ? 
                        ' En attente du démarrage de la tâche...' : 
                        ' Aucun log disponible pour le moment'
                      }
                    </Typography>
                  </Box>
                )}
              </Box>
            </Collapse>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default TaskProgress;