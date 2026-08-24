// src/components/Auth/RegisterForm.tsx

import { useState } from "react";
import axios from "../../api/axiosClient";
import { TextField, Button, Alert, Stack } from "@mui/material";

interface RegisterFormProps {
  selectedTier?: string;
}

const RegisterForm: React.FC<RegisterFormProps> = ({ selectedTier = "free" }) => {
  // TODO: Use selectedTier for subscription tier selection
  console.log("Selected tier:", selectedTier);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!email || !password) {
      setError("Veuillez remplir tous les champs.");
      return;
    }

    try {
      await axios.post("/auth/register", { email, password });

      setSuccess(" Compte créé avec succès. Vous pouvez vous connecter.");
      setEmail("");
      setPassword("");
      
      // Note: L'onboarding sera déclenché après la connexion, pas à l'inscription
    } catch (error: unknown) {
      console.error("Registration error:", error);
      setError(
        "Erreur lors de l'inscription. Peut-être un email déjà utilisé."
      );
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Stack spacing={2}>
        {error && <Alert severity="error">{error}</Alert>}
        {success && <Alert severity="success">{success}</Alert>}
        <TextField
          label="Email"
          type="email"
          fullWidth
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          label="Mot de passe"
          type="password"
          fullWidth
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" variant="contained" fullWidth>
          Créer un compte
        </Button>
      </Stack>
    </form>
  );
};

export default RegisterForm;
