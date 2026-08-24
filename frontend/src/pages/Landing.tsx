import React from "react";
import {
  Box,
  Container,
  Typography,
  Button,
  Card,
  CardContent,
  Stack,
  Chip,
  Avatar,
  alpha,
  useTheme,
  IconButton,
  Fade,
} from "@mui/material";
import {
  CloudQueue,
  Code,
  Security,
  Speed,
  AutoAwesome,
  CheckCircle,
  ArrowForward,
  GitHub,
  LinkedIn,
  Twitter,
} from "@mui/icons-material";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const Landing: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { token } = useAuth();

  const features = [
    {
      icon: <AutoAwesome />,
      title: "IA Conversationnelle",
      description:
        "Décrivez votre infrastructure en langage naturel, notre IA génère le code automatiquement",
    },
    {
      icon: <Code />,
      title: "Multi-Technologies",
      description:
        "Support complet de Terraform et Ansible pour tous vos besoins DevOps",
    },
    {
      icon: <CloudQueue />,
      title: "Multi-Cloud",
      description:
        "Déployez sur AWS, Azure et GCP depuis une interface unifiée",
    },
    {
      icon: <Speed />,
      title: "Déploiement Rapide",
      description:
        "De la conversation au déploiement en quelques minutes seulement",
    },
    {
      icon: <Security />,
      title: "Sécurisé par Design",
      description:
        "Chiffrement des clés SSH, authentification JWT, conformité entreprise",
    },
  ];

  const handleGetStarted = () => {
    if (token) {
      // Already logged in, go directly to chat
      navigate("/chat");
    } else {
      // Not logged in, redirect to login page
      navigate("/auth");
    }
  };

  const handleConfigureAWS = () => {
    if (token) {
      navigate("/onboarding/aws");
    } else {
      navigate("/auth");
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      {/* Hero Section */}
      <Container maxWidth="lg" sx={{ pt: 8, pb: 6 }}>
        <Fade in timeout={1000}>
          <Box textAlign="center" mb={8}>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8 }}
            >
              <Avatar
                sx={{
                  width: 120,
                  height: 120,
                  mx: "auto",
                  mb: 4,
                  background:
                    "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
                  boxShadow: "0 20px 60px rgba(99, 102, 241, 0.3)",
                }}
              >
                <Code sx={{ fontSize: 60 }} />
              </Avatar>

              <Typography
                variant="h1"
                sx={{
                  fontSize: { xs: "2.5rem", md: "4rem" },
                  fontWeight: 900,
                  background:
                    "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
                  backgroundClip: "text",
                  WebkitBackgroundClip: "text",
                  color: "transparent",
                  mb: 2,
                }}
              >
                DevOps-as-a-Chat
              </Typography>

              <Typography
                variant="h4"
                color="text.secondary"
                sx={{ mb: 4, maxWidth: 800, mx: "auto" }}
              >
                Créez et déployez vos infrastructures cloud par simple
                conversation
              </Typography>

              <Typography
                variant="h6"
                color="text.secondary"
                sx={{ mb: 6, maxWidth: 600, mx: "auto", fontWeight: 400 }}
              >
                Automatisez vos déploiements AWS avec l'intelligence
                artificielle. Terraform et Ansible, tout par chat intelligent.
              </Typography>

              <Stack direction="row" spacing={2} justifyContent="center">
                <Button
                  variant="contained"
                  size="large"
                  endIcon={<ArrowForward />}
                  onClick={handleGetStarted}
                  sx={{
                    py: 2,
                    px: 4,
                    fontSize: "1.1rem",
                    background:
                      "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
                    boxShadow: "0 8px 32px rgba(99, 102, 241, 0.3)",
                    "&:hover": {
                      boxShadow: "0 12px 40px rgba(99, 102, 241, 0.4)",
                      transform: "translateY(-2px)",
                    },
                    transition: "all 0.3s ease",
                  }}
                >
                  Commencer
                </Button>
                <Button
                  variant="outlined"
                  size="large"
                  endIcon={<CloudQueue />}
                  onClick={handleConfigureAWS}
                  sx={{
                    py: 2,
                    px: 4,
                    fontSize: "1.1rem",
                    borderColor: "primary.main",
                    color: "primary.main",
                    "&:hover": {
                      borderColor: "primary.dark",
                      backgroundColor: alpha(theme.palette.primary.main, 0.05),
                    },
                    transition: "all 0.3s ease",
                  }}
                >
                  Configurer AWS
                </Button>
              </Stack>
            </motion.div>
          </Box>
        </Fade>

        {/* Features Grid */}
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              md: "repeat(3, 1fr)",
            },
            gap: 4,
            mb: 8,
          }}
        >
          {features.map((feature, index) => (
            <Box key={index}>
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
              >
                <Card
                  sx={{
                    height: "100%",
                    bgcolor: alpha(theme.palette.background.paper, 0.8),
                    backdropFilter: "blur(20px)",
                    border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
                    "&:hover": {
                      transform: "translateY(-4px)",
                      boxShadow: "0 20px 40px rgba(0,0,0,0.1)",
                    },
                    transition: "all 0.3s ease",
                  }}
                >
                  <CardContent sx={{ p: 3 }}>
                    <Box
                      sx={{
                        width: 64,
                        height: 64,
                        borderRadius: 2,
                        background:
                          "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        mb: 2,
                      }}
                    >
                      {React.cloneElement(feature.icon, {
                        sx: { color: "white", fontSize: 30 },
                      })}
                    </Box>
                    <Typography variant="h6" gutterBottom fontWeight={600}>
                      {feature.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {feature.description}
                    </Typography>
                  </CardContent>
                </Card>
              </motion.div>
            </Box>
          ))}
        </Box>
      </Container>

      {/* Footer */}
      <Box
        sx={{
          bgcolor: alpha(theme.palette.background.paper, 0.5),
          py: 4,
          mt: 8,
          borderTop: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
        }}
      >
        <Container maxWidth="lg">
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <Box>
              <Typography variant="body2" color="text.secondary">
                © 2025 DevOps-as-a-Chat. Créé par Arnaud (Patrick) Toure
              </Typography>
            </Box>
            <Box>
              <Stack direction="row" spacing={1}>
                <IconButton size="small" color="primary">
                  <GitHub />
                </IconButton>
                <IconButton size="small" color="primary">
                  <LinkedIn />
                </IconButton>
                <IconButton size="small" color="primary">
                  <Twitter />
                </IconButton>
              </Stack>
            </Box>
          </Box>
        </Container>
      </Box>
    </Box>
  );
};

export default Landing;
