import { useState } from "react";
import { Box, Button, TextField, Typography, Alert } from "@mui/material";

interface CredentialsFormProps {
  onSubmit: (credentials: string) => void;
  provider: string;
}

export default function CredentialsForm({ onSubmit, provider }: CredentialsFormProps) {
  const [json, setJson] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = () => {
    try {
      const parsed = JSON.parse(json);
      if (!parsed || typeof parsed !== "object") {
        setError("Le JSON doit représenter un objet valide.");
        return;
      }
      setError("");
      onSubmit(json);
    } catch (e) {
      setError("JSON invalide. Veuillez vérifier la syntaxe.");
    }
  };

  return (
    <Box display="flex" flexDirection="column" gap={2}>
      <Typography variant="h6" color="white">
         Credentials pour {provider?.toUpperCase() || "PROVIDER"}
      </Typography>

      <TextField
        label="Clé JSON"
        value={json}
        onChange={(e) => setJson(e.target.value)}
        multiline
        rows={6}
        fullWidth
        variant="outlined"
        sx={{ bgcolor: "white" }}
      />

      {error && <Alert severity="error">{error}</Alert>}

      <Button
        variant="contained"
        onClick={handleSubmit}
        disabled={json.trim() === ""}
        sx={{ fontWeight: "bold" }}
      >
        Envoyer
      </Button>
    </Box>
  );
}
