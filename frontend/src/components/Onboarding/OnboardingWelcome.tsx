import {
  Box,
  Typography,
  Button,
  Paper,
  alpha,
  Avatar,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Fade,
} from "@mui/material";
import {
  CloudQueue,
  Security,
  Speed,
  AutoAwesome,
  ArrowForward,
} from "@mui/icons-material";

interface OnboardingWelcomeProps {
  onNext: () => void;
  onExplore?: () => void;
}

export default function OnboardingWelcome({
  onNext,
  onExplore,
}: OnboardingWelcomeProps) {
  return (
    <Fade in timeout={600}>
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          maxWidth: 600,
          mx: "auto",
          p: 4,
        }}
      >
        {/* Header */}
        <Box sx={{ textAlign: "center", mb: 4 }}>
          <Avatar
            sx={{
              width: 80,
              height: 80,
              mx: "auto",
              mb: 3,
              background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
              boxShadow: "0 8px 32px rgba(99, 102, 241, 0.3)",
            }}
          >
            <AutoAwesome sx={{ fontSize: "2.5rem" }} />
          </Avatar>

          <Typography
            variant="h3"
            fontWeight={700}
            color="text.primary"
            gutterBottom
          >
            Bienvenue sur DevOps Assistant !
          </Typography>

          <Typography
            variant="h6"
            color="text.secondary"
            sx={{ maxWidth: 480, mx: "auto", lineHeight: 1.6 }}
          >
            Votre assistant intelligent pour automatiser et gérer votre
            infrastructure cloud.
          </Typography>
        </Box>

        {/* Features */}
        <Paper
          elevation={0}
          sx={{
            width: "100%",
            p: 3,
            mb: 4,
            bgcolor: alpha("#1e293b", 0.8),
            backdropFilter: "blur(20px)",
            border: "1px solid",
            borderColor: alpha("#475569", 0.3),
            borderRadius: 3,
          }}
        >
          <Typography
            variant="h6"
            fontWeight={600}
            color="text.primary"
            sx={{ mb: 2 }}
          >
            Ce que vous pouvez faire :
          </Typography>

          <List sx={{ p: 0 }}>
            <ListItem sx={{ px: 0, py: 1 }}>
              <ListItemIcon>
                <AutoAwesome sx={{ color: "primary.main" }} />
              </ListItemIcon>
              <ListItemText
                primary="Assistant DevOps conversationnel"
                secondary="Discutez avec l'IA pour définir et gérer votre infrastructure"
                primaryTypographyProps={{ fontWeight: 500 }}
              />
            </ListItem>

            <ListItem sx={{ px: 0, py: 1 }}>
              <ListItemIcon>
                <CloudQueue sx={{ color: "secondary.main" }} />
              </ListItemIcon>
              <ListItemText
                primary="Déploiement automatisé sur AWS"
                secondary="Terraform + Ansible pour créer vos ressources cloud"
                primaryTypographyProps={{ fontWeight: 500 }}
              />
            </ListItem>

            <ListItem sx={{ px: 0, py: 1 }}>
              <ListItemIcon>
                <Security sx={{ color: "success.main" }} />
              </ListItemIcon>
              <ListItemText
                primary="Audit automatisé via Ansible"
                secondary="Vérification de la conformité et des bonnes pratiques"
                primaryTypographyProps={{ fontWeight: 500 }}
              />
            </ListItem>

            <ListItem sx={{ px: 0, py: 1 }}>
              <ListItemIcon>
                <Speed sx={{ color: "warning.main" }} />
              </ListItemIcon>
              <ListItemText
                primary="Gestion sécurisée des credentials"
                secondary="Vos clés AWS sont chiffrées et utilisées uniquement pour vos actions"
                primaryTypographyProps={{ fontWeight: 500 }}
              />
            </ListItem>
          </List>
        </Paper>

        {/* AWS Configuration Notice */}
        <Paper
          elevation={0}
          sx={{
            width: "100%",
            p: 3,
            mb: 4,
            bgcolor: alpha("#059669", 0.1),
            border: "1px solid",
            borderColor: alpha("#10b981", 0.3),
            borderRadius: 3,
          }}
        >
          <Typography
            variant="h6"
            fontWeight={600}
            color="secondary.main"
            sx={{ mb: 1 }}
          >
             Configuration AWS requise
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ lineHeight: 1.6 }}
          >
            Pour utiliser pleinement la plateforme, nous avons besoin de vos
            credentials AWS. Ces informations sont <strong>chiffrées</strong> et
            utilisées uniquement pour exécuter les actions que vous demandez.
          </Typography>
        </Paper>

        {/* Action Buttons */}
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            gap: 2,
            width: "100%",
          }}
        >
          <Button
            variant="contained"
            size="large"
            endIcon={<ArrowForward />}
            onClick={onNext}
            sx={{
              py: 1.5,
              px: 4,
              fontSize: "1.1rem",
              fontWeight: 600,
              borderRadius: 3,
              background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
              "&:hover": {
                background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)",
                transform: "translateY(-2px)",
                boxShadow: "0 12px 40px rgba(99, 102, 241, 0.4)",
              },
              transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
            }}
          >
            Configurer AWS maintenant
          </Button>

          {onExplore && (
            <Button
              variant="outlined"
              size="large"
              onClick={onExplore}
              sx={{
                py: 1.5,
                px: 4,
                fontSize: "1rem",
                fontWeight: 600,
                borderRadius: 3,
                borderColor: alpha("#6366f1", 0.5),
                color: "primary.main",
                "&:hover": {
                  borderColor: "primary.main",
                  bgcolor: alpha("#6366f1", 0.05),
                },
              }}
            >
              Découvrir l'assistant sans déploiement
            </Button>
          )}
        </Box>

        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mt: 2, textAlign: "center" }}
        >
          {onExplore
            ? "Vous pourrez configurer AWS plus tard"
            : "Cela ne prendra que quelques minutes"}
        </Typography>
      </Box>
    </Fade>
  );
}
