import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Alert,
  IconButton,
  Tooltip,
  Divider,
  alpha,
} from "@mui/material";
import { Visibility, VisibilityOff, Save, Delete } from "@mui/icons-material";
import { useState, useEffect } from "react";

interface AWSCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  region: string;
}

interface AWSCredentialsFormProps {
  onSave: (credentials: AWSCredentials) => Promise<void>;
  onDelete: () => Promise<void>;
  initialCredentials?: AWSCredentials | null;
}

export default function AWSCredentialsForm({
  onSave,
  onDelete,
  initialCredentials,
}: AWSCredentialsFormProps) {
  const [credentials, setCredentials] = useState<AWSCredentials>({
    accessKeyId: "",
    secretAccessKey: "",
    region: "us-east-1",
  });

  const [showSecretKey, setShowSecretKey] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (initialCredentials) {
      setCredentials(initialCredentials);
    }
  }, [initialCredentials]);

  const handleChange = (field: keyof AWSCredentials) => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setCredentials(prev => ({
      ...prev,
      [field]: e.target.value,
    }));
    setError("");
    setSuccess("");
  };

  const handleSave = async () => {
    if (!credentials.accessKeyId.trim() || !credentials.secretAccessKey.trim()) {
      setError("L'Access Key ID et la Secret Access Key sont requis");
      return;
    }

    if (!credentials.region.trim()) {
      setError("La région est requise");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      await onSave(credentials);
      setSuccess("Identifiants AWS sauvegardés avec succès !");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la sauvegarde des identifiants");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Êtes-vous sûr de vouloir supprimer vos identifiants AWS ?")) {
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      await onDelete();
      setCredentials({
        accessKeyId: "",
        secretAccessKey: "",
        region: "us-east-1",
      });
      setSuccess("Identifiants AWS supprimés avec succès !");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la suppression des identifiants");
    } finally {
      setLoading(false);
    }
  };

  const hasCredentials = initialCredentials?.accessKeyId;

  return (
    <Paper
      elevation={0}
      sx={{
        p: 4,
        bgcolor: alpha('#1e293b', 0.8),
        backdropFilter: 'blur(20px)',
        border: '1px solid',
        borderColor: alpha('#475569', 0.3),
        borderRadius: 3,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
        <Box
          sx={{
            width: 48,
            height: 48,
            borderRadius: 2,
            background: 'linear-gradient(135deg, #ff9500 0%, #ff6b35 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '1.5rem',
          }}
        >
          
        </Box>
        <Box>
          <Typography variant="h6" fontWeight={600} color="text.primary">
            Identifiants AWS
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Configurez vos clés d'accès AWS pour la gestion de l'infrastructure
          </Typography>
        </Box>
      </Box>

      <Divider sx={{ mb: 3, borderColor: alpha('#475569', 0.3) }} />

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <TextField
          label="Access Key ID"
          value={credentials.accessKeyId}
          onChange={handleChange('accessKeyId')}
          fullWidth
          variant="outlined"
          placeholder="AKIA..."
          sx={{
            '& .MuiOutlinedInput-root': {
              bgcolor: alpha('#334155', 0.3),
              '& fieldset': {
                borderColor: alpha('#475569', 0.5),
              },
              '&:hover fieldset': {
                borderColor: 'primary.main',
              },
              '&.Mui-focused fieldset': {
                borderColor: 'primary.main',
              },
            },
          }}
        />

        <TextField
          label="Clé d'accès secrète"
          type={showSecretKey ? 'text' : 'password'}
          value={credentials.secretAccessKey}
          onChange={handleChange('secretAccessKey')}
          fullWidth
          variant="outlined"
          placeholder="Entrez votre clé d'accès secrète"
          InputProps={{
            endAdornment: (
              <Tooltip title={showSecretKey ? 'Masquer' : 'Afficher'}>
                <IconButton
                  onClick={() => setShowSecretKey(!showSecretKey)}
                  edge="end"
                  sx={{ color: 'text.secondary' }}
                >
                  {showSecretKey ? <VisibilityOff /> : <Visibility />}
                </IconButton>
              </Tooltip>
            ),
          }}
          sx={{
            '& .MuiOutlinedInput-root': {
              bgcolor: alpha('#334155', 0.3),
              '& fieldset': {
                borderColor: alpha('#475569', 0.5),
              },
              '&:hover fieldset': {
                borderColor: 'primary.main',
              },
              '&.Mui-focused fieldset': {
                borderColor: 'primary.main',
              },
            },
          }}
        />

        <TextField
          label="Région par défaut"
          value={credentials.region}
          onChange={handleChange('region')}
          fullWidth
          variant="outlined"
          placeholder="us-east-1"
          sx={{
            '& .MuiOutlinedInput-root': {
              bgcolor: alpha('#334155', 0.3),
              '& fieldset': {
                borderColor: alpha('#475569', 0.5),
              },
              '&:hover fieldset': {
                borderColor: 'primary.main',
              },
              '&.Mui-focused fieldset': {
                borderColor: 'primary.main',
              },
            },
          }}
        />

        {error && (
          <Alert severity="error" sx={{ borderRadius: 2 }}>
            {error}
          </Alert>
        )}

        {success && (
          <Alert severity="success" sx={{ borderRadius: 2 }}>
            {success}
          </Alert>
        )}

        <Box sx={{ display: 'flex', gap: 2, pt: 2 }}>
          <Button
            variant="contained"
            startIcon={<Save />}
            onClick={handleSave}
            disabled={loading}
            sx={{
              flex: 1,
              py: 1.5,
              fontWeight: 600,
              borderRadius: 2,
              textTransform: 'none',
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
              '&:hover': {
                background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
                transform: 'translateY(-1px)',
              },
              '&:disabled': {
                background: alpha('#6366f1', 0.3),
              },
            }}
          >
            {loading ? 'Sauvegarde...' : 'Sauvegarder les identifiants'}
          </Button>

          {hasCredentials && (
            <Button
              variant="outlined"
              startIcon={<Delete />}
              onClick={handleDelete}
              disabled={loading}
              sx={{
                borderColor: 'error.main',
                color: 'error.main',
                py: 1.5,
                px: 3,
                fontWeight: 600,
                borderRadius: 2,
                textTransform: 'none',
                '&:hover': {
                  borderColor: 'error.dark',
                  bgcolor: alpha('#ef4444', 0.1),
                },
              }}
            >
              Supprimer
            </Button>
          )}
        </Box>
      </Box>

      <Box
        sx={{
          mt: 3,
          p: 2,
          bgcolor: alpha('#059669', 0.1),
          border: '1px solid',
          borderColor: alpha('#10b981', 0.3),
          borderRadius: 2,
        }}
      >
        <Typography variant="body2" color="secondary.main" fontWeight={500} sx={{ mb: 1 }}>
           Note de sécurité
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
          Vos identifiants AWS sont chiffrés et stockés de manière sécurisée. Ils seront utilisés automatiquement 
          dans les conversations de chat pour les tâches de gestion d'infrastructure.
        </Typography>
      </Box>
    </Paper>
  );
}