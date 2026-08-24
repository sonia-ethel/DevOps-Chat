import { Alert, AlertTitle, Box, Button, Stack } from "@mui/material";
import { Warning, CloudQueue, Explore } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

interface AWSCredentialsWarningProps {
  onDismiss?: () => void;
}

/**
 * AWSCredentialsWarning: Bandeau d'avertissement pour indiquer l'absence de credentials AWS
 * Affiché dans le chat si l'utilisateur n'a pas configuré ses credentials AWS
 */
export default function AWSCredentialsWarning({
  onDismiss,
}: AWSCredentialsWarningProps) {
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  const handleConfigureAWS = () => {
    navigate("/onboarding/aws");
  };

  const handleDismiss = () => {
    setDismissed(true);
    onDismiss?.();
  };

  return (
    <Alert
      severity="info"
      icon={<Warning />}
      sx={{
        mb: 2,
        backgroundColor: "rgba(25, 118, 210, 0.08)",
        borderColor: "rgb(25, 118, 210)",
        borderLeft: "4px solid rgb(25, 118, 210)",
      }}
      onClose={handleDismiss}
    >
      <AlertTitle sx={{ fontWeight: 600, mb: 1 }}>
        Configurez vos credentials AWS
      </AlertTitle>
      <Box sx={{ mb: 1 }}>
        Vous pouvez utiliser l'assistant en mode découverte, mais les actions de
        création/déploiement nécessitent une configuration AWS.
      </Box>
      <Stack direction="row" spacing={1}>
        <Button
          size="small"
          variant="contained"
          startIcon={<CloudQueue />}
          onClick={handleConfigureAWS}
          sx={{
            backgroundColor: "rgb(25, 118, 210)",
            "&:hover": {
              backgroundColor: "rgb(21, 101, 192)",
            },
          }}
        >
          Configurer AWS
        </Button>
        <Button
          size="small"
          variant="outlined"
          startIcon={<Explore />}
          onClick={handleDismiss}
          sx={{
            borderColor: "rgb(25, 118, 210)",
            color: "rgb(25, 118, 210)",
          }}
        >
          Continuer sans
        </Button>
      </Stack>
    </Alert>
  );
}
