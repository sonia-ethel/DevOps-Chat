import { Box, Typography, Stack, alpha } from "@mui/material";
import { ChatBubbleOutline } from "@mui/icons-material";

interface EmptyStateProps {
  onCreateNew?: () => void;
}

/**
 * EmptyState: Affiche un état vide élégant quand le chat n'a aucun message
 */
export default function EmptyState({ onCreateNew }: EmptyStateProps) {
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
      <Box
        sx={{
          width: 120,
          height: 120,
          borderRadius: "50%",
          backgroundColor: (theme) => alpha(theme.palette.primary.main, 0.1),
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          mb: 3,
        }}
      >
        <ChatBubbleOutline
          sx={{
            fontSize: 60,
            color: "primary.main",
            opacity: 0.6,
          }}
        />
      </Box>

      <Typography
        variant="h5"
        sx={{
          fontWeight: 600,
          mb: 1,
          color: "text.primary",
        }}
      >
        Aucun message pour l'instant
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
        Commencez la conversation en décrivant ce que vous souhaitez accomplir.
        L'assistant DevOps vous guidera étape par étape.
      </Typography>

      <Stack direction="column" spacing={1} alignItems="center">
        <Typography variant="caption" color="text.secondary">
           Exemples de demandes :
        </Typography>
        <Stack spacing={0.5} sx={{ opacity: 0.7 }}>
          <Typography variant="caption" color="text.secondary">
            • "Créer 3 instances Ubuntu sur AWS"
          </Typography>
          <Typography variant="caption" color="text.secondary">
            • "Déployer une application web avec load balancer"
          </Typography>
          <Typography variant="caption" color="text.secondary">
            • "Auditer mes serveurs existants"
          </Typography>
        </Stack>
      </Stack>

      {/* Button removed - creation happens via sidebar "Nouveau Chat" or "+" button */}
    </Box>
  );
}
