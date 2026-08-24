import { Box, Typography, Button, Stack, Alert } from "@mui/material";
import { Error, Refresh, Add, Login } from "@mui/icons-material";

interface ErrorStateProps {
  errorType: "not_found" | "unauthorized" | "network" | "server";
  message?: string;
  onRetry?: () => void;
  onCreateNew?: () => void;
  onLogin?: () => void;
}

/**
 * ErrorState: Affiche un état d'erreur approprié selon le type d'erreur
 */
export default function ErrorState({
  errorType,
  message,
  onRetry,
  onCreateNew,
  onLogin,
}: ErrorStateProps) {
  const getErrorContent = () => {
    switch (errorType) {
      case "not_found":
        return {
          title: "Conversation introuvable",
          description:
            "Cette conversation n'existe pas ou a été supprimée. Créez un nouveau chat pour commencer.",
          icon: <Error sx={{ fontSize: 60, color: "warning.main" }} />,
          actions: (
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={onCreateNew}
            >
              Créer un nouveau chat
            </Button>
          ),
        };

      case "unauthorized":
        return {
          title: "Session expirée",
          description:
            "Votre session a expiré. Veuillez vous reconnecter pour continuer.",
          icon: <Login sx={{ fontSize: 60, color: "error.main" }} />,
          actions: (
            <Button variant="contained" startIcon={<Login />} onClick={onLogin}>
              Se reconnecter
            </Button>
          ),
        };

      case "network":
        return {
          title: "Erreur de connexion",
          description:
            "Impossible de se connecter au serveur. Vérifiez votre connexion internet et réessayez.",
          icon: <Error sx={{ fontSize: 60, color: "error.main" }} />,
          actions: (
            <Button
              variant="contained"
              startIcon={<Refresh />}
              onClick={onRetry}
            >
              Réessayer
            </Button>
          ),
        };

      case "server":
      default:
        return {
          title: "Erreur serveur",
          description:
            message ||
            "Une erreur s'est produite sur le serveur. Veuillez réessayer dans quelques instants.",
          icon: <Error sx={{ fontSize: 60, color: "error.main" }} />,
          actions: (
            <Stack direction="row" spacing={2}>
              <Button
                variant="outlined"
                startIcon={<Refresh />}
                onClick={onRetry}
              >
                Réessayer
              </Button>
              <Button
                variant="contained"
                startIcon={<Add />}
                onClick={onCreateNew}
              >
                Nouveau chat
              </Button>
            </Stack>
          ),
        };
    }
  };

  const content = getErrorContent();

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "400px",
        py: 8,
        px: 3,
      }}
    >
      <Box sx={{ mb: 3 }}>{content.icon}</Box>

      <Typography
        variant="h5"
        sx={{
          fontWeight: 600,
          mb: 1,
          color: "text.primary",
        }}
      >
        {content.title}
      </Typography>

      <Typography
        variant="body1"
        color="text.secondary"
        sx={{
          mb: 3,
          maxWidth: 500,
          textAlign: "center",
        }}
      >
        {content.description}
      </Typography>

      {content.actions}

      {message && errorType !== "server" && (
        <Alert severity="error" sx={{ mt: 3, maxWidth: 500 }}>
          <Typography variant="caption">{message}</Typography>
        </Alert>
      )}
    </Box>
  );
}
