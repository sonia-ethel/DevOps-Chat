// src/components/Auth/AuthModal.tsx
import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  Tabs,
  Tab,
  Box,
  Avatar,
  Typography,
  alpha,
  Slide,
  Button,
  Stack,
  Divider,
} from "@mui/material";
import { Code, Security } from "@mui/icons-material";
import { forwardRef } from "react";

const Transition = forwardRef(function Transition(props: any, ref: any) {
  return <Slide direction="up" ref={ref} {...props} />;
});
import { useNavigate, useSearchParams } from "react-router-dom";
import LoginForm from "./LoginForm";
import RegisterForm from "./RegisterForm";

interface AuthModalProps {
  open?: boolean;
  onClose?: () => void;
  selectedTier?: string;
  onSuccess?: () => void;
}

const AuthModal: React.FC<AuthModalProps> = ({
  open = true,
  onClose,
  selectedTier = "free",
  onSuccess,
}) => {
  const [tab, setTab] = useState(0);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Si on a été redirigé depuis /chat, on récupère la destination
  const nextPath = searchParams.get("next") || "/chat";

  // Dès qu'un token existe (login réussi), on redirige automatiquement
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      onSuccess?.();
      // Redirect to /chat by default or to the nextPath query param
      const redirectTo = nextPath === "/" ? "/chat" : nextPath;
      navigate(redirectTo, { replace: true });
    }
    // Écoute les changements de storage (au cas d'autres onglets)
    const onStorage = (e: StorageEvent) => {
      if (e.key === "access_token" && e.newValue) {
        onSuccess?.();
        const redirectTo = nextPath === "/" ? "/chat" : nextPath;
        navigate(redirectTo, { replace: true });
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [navigate, nextPath]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      TransitionComponent={Transition}
      PaperProps={{
        sx: {
          bgcolor: alpha("#1e293b", 0.95),
          backdropFilter: "blur(20px)",
          borderRadius: 3,
          border: "1px solid",
          borderColor: alpha("#475569", 0.3),
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
        },
      }}
      BackdropProps={{
        sx: {
          bgcolor: alpha("#0f172a", 0.8),
          backdropFilter: "blur(4px)",
        },
      }}
    >
      <DialogTitle sx={{ textAlign: "center", pb: 1 }}>
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 2,
          }}
        >
          <Avatar
            sx={{
              width: 64,
              height: 64,
              background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
              boxShadow: "0 8px 32px rgba(99, 102, 241, 0.3)",
            }}
          >
            <Code fontSize="large" />
          </Avatar>
          <Box>
            <Typography variant="h4" fontWeight={700} color="text.primary">
              DevOps Assistant
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {tab === 0 ? "Welcome back" : "Join the platform"}
            </Typography>
          </Box>
        </Box>
      </DialogTitle>

      <Box sx={{ px: 3 }}>
        <Tabs
          value={tab}
          onChange={(_, newValue) => setTab(newValue)}
          variant="fullWidth"
          sx={{
            borderBottom: 1,
            borderColor: alpha("#475569", 0.3),
            "& .MuiTab-root": {
              fontWeight: 500,
              color: "text.secondary",
              "&.Mui-selected": {
                color: "primary.main",
              },
            },
            "& .MuiTabs-indicator": {
              bgcolor: "primary.main",
              height: 3,
              borderRadius: "2px 2px 0 0",
            },
          }}
        >
          <Tab label="Sign In" icon={<Security />} iconPosition="start" />
          <Tab label="Sign Up" />
        </Tabs>
      </Box>

      <DialogContent sx={{ px: 4, pt: 3, pb: 4 }}>
        <Box>
          {tab === 0 ? (
            <LoginForm />
          ) : (
            <RegisterForm selectedTier={selectedTier} />
          )}
        </Box>

        {tab === 1 && (
          <Box sx={{ mt: 3 }}>
            <Divider sx={{ mb: 3, color: "text.secondary" }}>
              <Typography variant="body2">Ou</Typography>
            </Divider>

            <Stack spacing={2}>
              <Button
                variant="outlined"
                fullWidth
                onClick={() => navigate("/register")}
                sx={{
                  py: 1.5,
                  borderRadius: 2,
                  textTransform: "none",
                  fontWeight: 600,
                }}
              >
                Créer un compte avec sélection de plan
              </Button>

              <Typography variant="body2" color="text.secondary" align="center">
                Choisissez votre plan et bénéficiez de toutes les
                fonctionnalités
              </Typography>
            </Stack>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default AuthModal;
