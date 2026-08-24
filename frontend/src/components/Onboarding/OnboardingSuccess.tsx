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
  Grow,
} from "@mui/material";
import {
  Celebration,
  Chat,
  CloudQueue,
  AutoAwesome,
  ArrowForward,
  CheckCircle,
} from "@mui/icons-material";

interface OnboardingSuccessProps {
  onComplete: () => void;
}

export default function OnboardingSuccess({
  onComplete,
}: OnboardingSuccessProps) {
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
        {/* Success Animation */}
        <Grow in timeout={1000}>
          <Avatar
            sx={{
              width: 100,
              height: 100,
              mb: 3,
              background: "linear-gradient(135deg, #10b981 0%, #34d399 100%)",
              boxShadow: "0 12px 48px rgba(16, 185, 129, 0.4)",
              "& svg": { fontSize: "3rem" },
            }}
          >
            <Celebration />
          </Avatar>
        </Grow>

        {/* Header */}
        <Box sx={{ textAlign: "center", mb: 4 }}>
          <Typography
            variant="h3"
            fontWeight={700}
            color="text.primary"
            gutterBottom
          >
             Félicitations !
          </Typography>

          <Typography
            variant="h6"
            color="text.secondary"
            sx={{ maxWidth: 480, mx: "auto", lineHeight: 1.6 }}
          >
            Votre configuration AWS est terminée. Vous pouvez maintenant
            utiliser pleinement votre assistant DevOps !
          </Typography>
        </Box>

        {/* Next Steps */}
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
            Prochaines étapes :
          </Typography>

          <List sx={{ p: 0 }}>
            <ListItem sx={{ px: 0, py: 1 }}>
              <ListItemIcon>
                <CheckCircle sx={{ color: "success.main" }} />
              </ListItemIcon>
              <ListItemText
                primary="Configuration AWS terminée"
                secondary="Vos credentials sont sécurisés et prêts à être utilisés"
                primaryTypographyProps={{
                  fontWeight: 500,
                  color: "success.main",
                }}
              />
            </ListItem>

            <ListItem sx={{ px: 0, py: 1 }}>
              <ListItemIcon>
                <Chat sx={{ color: "primary.main" }} />
              </ListItemIcon>
              <ListItemText
                primary="Commencer une conversation"
                secondary="Demandez à l'assistant de créer des ressources, déployer une infrastructure..."
                primaryTypographyProps={{ fontWeight: 500 }}
              />
            </ListItem>

            <ListItem sx={{ px: 0, py: 1 }}>
              <ListItemIcon>
                <CloudQueue sx={{ color: "secondary.main" }} />
              </ListItemIcon>
              <ListItemText
                primary="Explorer les fonctionnalités"
                secondary="Terraform, Ansible, audits de sécurité et plus encore"
                primaryTypographyProps={{ fontWeight: 500 }}
              />
            </ListItem>
          </List>
        </Paper>

        {/* Tips */}
        <Paper
          elevation={0}
          sx={{
            width: "100%",
            p: 3,
            mb: 4,
            bgcolor: alpha("#6366f1", 0.1),
            border: "1px solid",
            borderColor: alpha("#6366f1", 0.3),
            borderRadius: 3,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
            <AutoAwesome sx={{ color: "primary.main", mr: 1 }} />
            <Typography variant="h6" fontWeight={600} color="primary.main">
              Conseils pour commencer
            </Typography>
          </Box>

          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ lineHeight: 1.6, mb: 1 }}
          >
            • <strong>Commencez simple :</strong> "Crée-moi une instance EC2
            avec Ubuntu"
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ lineHeight: 1.6, mb: 1 }}
          >
            • <strong>Soyez précis :</strong> "Déploie 3 instances EC2 avec load
            balancer"
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ lineHeight: 1.6 }}
          >
            • <strong>Demandez de l'aide :</strong> "Comment faire un audit de
            sécurité ?"
          </Typography>
        </Paper>

        {/* CTA Button */}
        <Button
          variant="contained"
          size="large"
          endIcon={<ArrowForward />}
          onClick={onComplete}
          sx={{
            py: 2,
            px: 5,
            fontSize: "1.2rem",
            fontWeight: 700,
            borderRadius: 3,
            background: "linear-gradient(135deg, #10b981 0%, #34d399 100%)",
            boxShadow: "0 8px 32px rgba(16, 185, 129, 0.3)",
            "&:hover": {
              background: "linear-gradient(135deg, #059669 0%, #10b981 100%)",
              transform: "translateY(-2px)",
              boxShadow: "0 12px 40px rgba(16, 185, 129, 0.4)",
            },
            transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
          }}
        >
          Accéder au chat
        </Button>

        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mt: 2, textAlign: "center" }}
        >
          Vous pouvez modifier vos credentials AWS à tout moment dans les
          paramètres
        </Typography>
      </Box>
    </Fade>
  );
}
