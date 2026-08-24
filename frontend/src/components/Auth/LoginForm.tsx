// src/components/Auth/LoginForm.tsx

import { useState } from "react";
import axios from "../../api/axiosClient";
import { TextField, Button, Alert, Stack, alpha, CircularProgress, InputAdornment, IconButton } from "@mui/material";
import { Email, Lock, Visibility, VisibilityOff } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { useOnboarding } from "../../contexts/OnboardingContext";

interface LoginResponse {
  access_token: string;
  token_type: string;
}

const LoginForm: React.FC = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();
  const { checkOnboardingStatus } = useOnboarding();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    const params = new URLSearchParams();
    params.append("grant_type", "password");
    params.append("username", email);
    params.append("password", password);
    params.append("scope", "");
    params.append("client_id", "");
    params.append("client_secret", "");

    try {
      const response = await axios.post<LoginResponse>("/auth/login", params, {
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
      });

      login(response.data.access_token);
      
      // Vérifier le statut d'onboarding après connexion réussie
      await checkOnboardingStatus();
      
      navigate("/chat");
    } catch (err: any) {
      console.error("Login error:", err.response?.data || err.message);
      setError("Invalid email or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Stack spacing={3}>
        {error && (
          <Alert 
            severity="error" 
            sx={{ 
              bgcolor: alpha('#ef4444', 0.1),
              color: 'error.main',
              border: '1px solid',
              borderColor: alpha('#ef4444', 0.3),
              borderRadius: 2,
            }}
          >
            {error}
          </Alert>
        )}
        
        <TextField
          label="Email Address"
          type="email"
          fullWidth
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={loading}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Email color="action" />
              </InputAdornment>
            ),
          }}
          sx={{
            '& .MuiOutlinedInput-root': {
              bgcolor: alpha('#334155', 0.2),
            },
          }}
        />
        
        <TextField
          label="Password"
          type={showPassword ? 'text' : 'password'}
          fullWidth
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={loading}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Lock color="action" />
              </InputAdornment>
            ),
            endAdornment: (
              <InputAdornment position="end">
                <IconButton
                  onClick={() => setShowPassword(!showPassword)}
                  edge="end"
                  disabled={loading}
                >
                  {showPassword ? <VisibilityOff /> : <Visibility />}
                </IconButton>
              </InputAdornment>
            ),
          }}
          sx={{
            '& .MuiOutlinedInput-root': {
              bgcolor: alpha('#334155', 0.2),
            },
          }}
        />
        
        <Button 
          type="submit" 
          variant="contained" 
          fullWidth
          disabled={loading}
          sx={{
            py: 1.5,
            fontSize: '1rem',
            fontWeight: 600,
            background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
            '&:hover': {
              background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
              transform: 'translateY(-1px)',
              boxShadow: '0 8px 25px rgba(99, 102, 241, 0.3)',
            },
            '&:disabled': {
              background: alpha('#6366f1', 0.3),
            },
            transition: 'all 0.2s ease-in-out',
          }}
        >
          {loading ? (
            <>
              <CircularProgress size={20} sx={{ mr: 1, color: 'inherit' }} />
              Signing in...
            </>
          ) : (
            'Sign In'
          )}
        </Button>
      </Stack>
    </form>
  );
};

export default LoginForm;
