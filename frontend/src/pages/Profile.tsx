import {
  Box,
  Typography,
  Container,
  Paper,
  Avatar,
  alpha,
  IconButton,
  Tooltip,
} from "@mui/material";
import { Settings, Person, ArrowBack } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import AWSCredentialsForm from "../components/Settings/AWSCredentialsForm";
import { useState, useEffect } from "react";
import {
  saveAWSCredentials,
  getAWSCredentials,
  deleteAWSCredentials,
} from "../api/axiosClient";
import { useOnboarding } from "../contexts/OnboardingContext";

interface AWSCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  region: string;
}

export default function Profile() {
  const [awsCredentials, setAwsCredentials] = useState<AWSCredentials | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { refreshOnboardingStatus } = useOnboarding();

  useEffect(() => {
    loadAwsCredentials();
  }, []);

  const loadAwsCredentials = async () => {
    try {
      const response = await getAWSCredentials();
      setAwsCredentials(response);
    } catch (error) {
      if ((error as any)?.response?.status === 404) {
        setAwsCredentials(null);
      } else {
        console.error("Failed to load AWS credentials:", error);
        setAwsCredentials(null);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSaveCredentials = async (credentials: AWSCredentials) => {
    try {
      await saveAWSCredentials(credentials);
      setAwsCredentials(credentials);

      // Rafraîchir le statut d'onboarding maintenant que les credentials existent
      await refreshOnboardingStatus();
    } catch (error) {
      console.error("Failed to save AWS credentials:", error);
      throw error;
    }
  };

  const handleDeleteCredentials = async () => {
    try {
      await deleteAWSCredentials();
      setAwsCredentials(null);

      // Rafraîchir le statut d'onboarding car les credentials n'existent plus
      await refreshOnboardingStatus();
    } catch (error) {
      console.error("Failed to delete AWS credentials:", error);
      throw error;
    }
  };

  if (loading) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Typography>Chargement...</Typography>
      </Container>
    );
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #0f172a 0%, #1e293b 100%)",
        py: 4,
      }}
    >
      <Container maxWidth="md">
        {/* Header avec navigation */}
        <Paper
          elevation={0}
          sx={{
            p: 4,
            mb: 4,
            bgcolor: alpha("#1e293b", 0.8),
            backdropFilter: "blur(20px)",
            border: "1px solid",
            borderColor: alpha("#475569", 0.3),
            borderRadius: 3,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 3 }}>
            <Tooltip title="Retour aux chats">
              <IconButton
                onClick={() => navigate("/chat")}
                sx={{
                  color: "text.secondary",
                  bgcolor: alpha("#475569", 0.1),
                  "&:hover": {
                    color: "primary.main",
                    bgcolor: alpha("#6366f1", 0.1),
                    transform: "scale(1.05)",
                  },
                  transition: "all 0.2s ease-in-out",
                  mr: 1,
                }}
              >
                <ArrowBack />
              </IconButton>
            </Tooltip>
            <Avatar
              sx={{
                width: 72,
                height: 72,
                background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
                fontSize: "2rem",
              }}
            >
              <Person sx={{ fontSize: "2rem" }} />
            </Avatar>
            <Box>
              <Typography
                variant="h4"
                fontWeight={700}
                color="text.primary"
                sx={{ mb: 1 }}
              >
                Paramètres utilisateur
              </Typography>
              <Typography variant="body1" color="text.secondary">
                Configurez vos préférences de compte et intégrations
              </Typography>
            </Box>
          </Box>
        </Paper>

        {/* Settings Sections */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {/* Cloud Credentials Section */}
          <Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
              <Settings sx={{ color: "primary.main", fontSize: "1.5rem" }} />
              <Typography variant="h5" fontWeight={600} color="text.primary">
                Intégrations Cloud
              </Typography>
            </Box>

            <AWSCredentialsForm
              onSave={handleSaveCredentials}
              onDelete={handleDeleteCredentials}
              initialCredentials={awsCredentials}
            />
          </Box>

          {/* Future sections can be added here */}
          <Paper
            elevation={0}
            sx={{
              p: 4,
              bgcolor: alpha("#1e293b", 0.8),
              backdropFilter: "blur(20px)",
              border: "1px solid",
              borderColor: alpha("#475569", 0.3),
              borderRadius: 3,
              opacity: 0.6,
            }}
          >
            <Typography variant="h6" color="text.secondary" sx={{ mb: 2 }}>
              Intégrations supplémentaires
            </Typography>
            <Typography variant="body2" color="text.secondary">
              D'autres intégrations de fournisseurs cloud arrivent bientôt...
            </Typography>
          </Paper>
        </Box>
      </Container>
    </Box>
  );
}
