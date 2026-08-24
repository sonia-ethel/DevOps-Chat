import {
  Box,
  Typography,
  Paper,
  alpha,
  CircularProgress,
  Button,
  Alert,
  Fade,
  Grow,
  Avatar,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from "@mui/material";
import {
  CheckCircle,
  Error,
  Refresh,
  ArrowForward,
  ArrowBack,
  CloudDone,
  Security,
  AccountCircle,
} from "@mui/icons-material";
import { useState, useEffect } from "react";
import type { AWSCredentials, ValidationResult } from "../../utils/awsValidator";
import { validateAWSCredentials } from "../../utils/awsValidator";

interface AWSCredentialsValidatorProps {
  credentials: AWSCredentials;
  onNext: () => void;
  onBack: () => void;
  onRetry: () => void;
}

type ValidationStatus = 'validating' | 'success' | 'error' | 'idle';

export default function AWSCredentialsValidator({ 
  credentials, 
  onNext, 
  onBack, 
  onRetry 
}: AWSCredentialsValidatorProps) {
  const [status, setStatus] = useState<ValidationStatus>('idle');
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [progress, setProgress] = useState(0);

  // Démarrage automatique de la validation
  useEffect(() => {
    validateCredentials();
  }, []);

  // Animation du progress lors de la validation
  useEffect(() => {
    if (status === 'validating') {
      const timer = setInterval(() => {
        setProgress(prev => {
          if (prev >= 90) return prev;
          return prev + Math.random() * 15;
        });
      }, 200);

      return () => clearInterval(timer);
    }
  }, [status]);

  const validateCredentials = async () => {
    setStatus('validating');
    setProgress(0);
    setResult(null);

    try {
      const validationResult = await validateAWSCredentials(credentials);
      
      // Animation finale du progress
      setProgress(100);
      
      setTimeout(() => {
        setResult(validationResult);
        setStatus(validationResult.isValid ? 'success' : 'error');
      }, 500);
      
    } catch (error) {
      setProgress(100);
      setTimeout(() => {
        setResult({ 
          isValid: false, 
          error: 'Erreur de connexion lors de la validation' 
        });
        setStatus('error');
      }, 500);
    }
  };

  const handleRetry = () => {
    validateCredentials();
  };

  return (
    <Fade in timeout={600}>
      <Box
        sx={{
          maxWidth: 600,
          mx: 'auto',
          p: 4,
        }}
      >
        {/* Header */}
        <Box sx={{ textAlign: 'center', mb: 4 }}>
          <CloudDone sx={{ fontSize: '3rem', color: 'primary.main', mb: 2 }} />
          <Typography variant="h4" fontWeight={700} color="text.primary" gutterBottom>
            Validation AWS
          </Typography>
          <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 480, mx: 'auto', lineHeight: 1.6 }}>
            Test de connexion à AWS avec vos credentials...
          </Typography>
        </Box>

        <Paper
          elevation={0}
          sx={{
            p: 4,
            mb: 4,
            bgcolor: alpha('#1e293b', 0.8),
            backdropFilter: 'blur(20px)',
            border: '1px solid',
            borderColor: alpha('#475569', 0.3),
            borderRadius: 3,
          }}
        >
          {/* Validation Status */}
          <Box sx={{ textAlign: 'center', mb: 3 }}>
            {status === 'validating' && (
              <Fade in>
                <Box>
                  <Box sx={{ position: 'relative', display: 'inline-flex', mb: 2 }}>
                    <CircularProgress
                      variant="determinate"
                      value={progress}
                      size={80}
                      thickness={4}
                      sx={{
                        color: 'primary.main',
                        '& .MuiCircularProgress-circle': {
                          strokeLinecap: 'round',
                        },
                      }}
                    />
                    <Box
                      sx={{
                        top: 0,
                        left: 0,
                        bottom: 0,
                        right: 0,
                        position: 'absolute',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <Typography variant="h6" component="div" color="text.primary" fontWeight={600}>
                        {Math.round(progress)}%
                      </Typography>
                    </Box>
                  </Box>
                  <Typography variant="h6" color="text.primary" fontWeight={600} gutterBottom>
                    Test en cours...
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Vérification de vos credentials AWS
                  </Typography>
                </Box>
              </Fade>
            )}

            {status === 'success' && result && (
              <Grow in timeout={800}>
                <Box>
                  <Avatar
                    sx={{
                      width: 80,
                      height: 80,
                      mx: 'auto',
                      mb: 2,
                      bgcolor: 'success.main',
                      '& svg': { fontSize: '2.5rem' },
                    }}
                  >
                    <CheckCircle />
                  </Avatar>
                  <Typography variant="h6" color="success.main" fontWeight={600} gutterBottom>
                     Validation réussie !
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                    Connexion AWS établie avec succès
                  </Typography>

                  {/* Account Details */}
                  {result.details && (
                    <Paper
                      elevation={0}
                      sx={{
                        p: 2,
                        bgcolor: alpha('#10b981', 0.1),
                        border: '1px solid',
                        borderColor: alpha('#10b981', 0.3),
                        borderRadius: 2,
                      }}
                    >
                      <Typography variant="subtitle2" color="success.main" fontWeight={600} sx={{ mb: 1 }}>
                        Informations du compte
                      </Typography>
                      <List dense sx={{ py: 0 }}>
                        <ListItem sx={{ px: 0, py: 0.5 }}>
                          <ListItemIcon sx={{ minWidth: 36 }}>
                            <AccountCircle sx={{ fontSize: 20, color: 'success.main' }} />
                          </ListItemIcon>
                          <ListItemText
                            primary="Compte"
                            secondary={result.details.account}
                            primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                            secondaryTypographyProps={{ variant: 'body2', fontSize: '0.75rem' }}
                          />
                        </ListItem>
                        <ListItem sx={{ px: 0, py: 0.5 }}>
                          <ListItemIcon sx={{ minWidth: 36 }}>
                            <Security sx={{ fontSize: 20, color: 'success.main' }} />
                          </ListItemIcon>
                          <ListItemText
                            primary="ARN"
                            secondary={result.details.arn}
                            primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                            secondaryTypographyProps={{ variant: 'body2', fontSize: '0.75rem' }}
                          />
                        </ListItem>
                      </List>
                    </Paper>
                  )}
                </Box>
              </Grow>
            )}

            {status === 'error' && result && (
              <Grow in timeout={800}>
                <Box>
                  <Avatar
                    sx={{
                      width: 80,
                      height: 80,
                      mx: 'auto',
                      mb: 2,
                      bgcolor: 'error.main',
                      '& svg': { fontSize: '2.5rem' },
                    }}
                  >
                    <Error />
                  </Avatar>
                  <Typography variant="h6" color="error.main" fontWeight={600} gutterBottom>
                     Échec de la validation
                  </Typography>
                  
                  <Alert severity="error" sx={{ mt: 2, textAlign: 'left' }}>
                    <Typography variant="body2" fontWeight={500} gutterBottom>
                      Impossible de valider vos credentials
                    </Typography>
                    <Typography variant="body2">
                      {result.error || 'Erreur inconnue lors de la validation'}
                    </Typography>
                  </Alert>

                  <Button
                    variant="outlined"
                    startIcon={<Refresh />}
                    onClick={handleRetry}
                    sx={{
                      mt: 3,
                      borderColor: 'error.main',
                      color: 'error.main',
                      '&:hover': {
                        borderColor: 'error.dark',
                        bgcolor: alpha('#ef4444', 0.1),
                      },
                    }}
                  >
                    Réessayer la validation
                  </Button>
                </Box>
              </Grow>
            )}
          </Box>
        </Paper>

        {/* Action Buttons */}
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant="outlined"
            startIcon={<ArrowBack />}
            onClick={status === 'error' ? onRetry : onBack}
            sx={{
              borderColor: alpha('#475569', 0.5),
              color: 'text.secondary',
              '&:hover': {
                borderColor: 'text.primary',
                bgcolor: alpha('#475569', 0.1),
              },
            }}
          >
            {status === 'error' ? 'Modifier les credentials' : 'Précédent'}
          </Button>
          
          <Button
            variant="contained"
            endIcon={<ArrowForward />}
            onClick={onNext}
            disabled={status !== 'success'}
            sx={{
              flex: 1,
              py: 1.5,
              fontWeight: 600,
              background: status === 'success' 
                ? 'linear-gradient(135deg, #10b981 0%, #34d399 100%)'
                : 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
              '&:hover': {
                background: status === 'success'
                  ? 'linear-gradient(135deg, #059669 0%, #10b981 100%)'
                  : 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
              },
              '&:disabled': {
                background: alpha('#6366f1', 0.3),
              },
            }}
          >
            Continuer vers le chat
          </Button>
        </Box>
      </Box>
    </Fade>
  );
}