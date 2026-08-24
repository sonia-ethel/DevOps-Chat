import {
  Box,
  Typography,
  TextField,
  Button,
  Paper,
  alpha,
  IconButton,
  Tooltip,
  MenuItem,
  FormControlLabel,
  Switch,
  Alert,
  InputAdornment,
  Fade,
  Link,
} from "@mui/material";
import {
  Visibility,
  VisibilityOff,
  Help,
  Security,
  ArrowBack,
  ArrowForward,
} from "@mui/icons-material";
import { useState } from "react";
import {
  AWS_REGIONS,
  DEFAULT_AWS_REGION,
  getRegionByCode,
} from "../../utils/awsRegions";
import type { AWSCredentials } from "../../utils/awsValidator";

interface AWSCredentialsSetupProps {
  onNext: (credentials: AWSCredentials) => void;
  onBack: () => void;
  loading?: boolean;
}

export default function AWSCredentialsSetup({
  onNext,
  onBack,
  loading = false,
}: AWSCredentialsSetupProps) {
  const [credentials, setCredentials] = useState<AWSCredentials>({
    accessKeyId: "",
    secretAccessKey: "",
    region: DEFAULT_AWS_REGION,
    sessionToken: "",
  });

  const [showSecretKey, setShowSecretKey] = useState(false);
  const [showSessionToken, setShowSessionToken] = useState(false);
  const [useSessionToken, setUseSessionToken] = useState(false);
  const [errors, setErrors] = useState<Partial<AWSCredentials>>({});

  const handleChange =
    (field: keyof AWSCredentials) =>
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const value = event.target.value;
      setCredentials((prev) => ({ ...prev, [field]: value }));

      // Clear error when user starts typing
      if (errors[field]) {
        setErrors((prev) => ({ ...prev, [field]: undefined }));
      }
    };

  const validateForm = (): boolean => {
    const newErrors: Partial<AWSCredentials> = {};

    if (!credentials.accessKeyId.trim()) {
      newErrors.accessKeyId = "L'Access Key ID est requis";
    } else if (!/^(AKIA|ASIA)[0-9A-Z]{16}$/.test(credentials.accessKeyId)) {
      newErrors.accessKeyId = "Format invalide (ex: AKIAIOSFODNN7EXAMPLE)";
    }

    if (!credentials.secretAccessKey.trim()) {
      newErrors.secretAccessKey = "La Secret Access Key est requise";
    } else if (credentials.secretAccessKey.length !== 40) {
      newErrors.secretAccessKey = "Doit contenir exactement 40 caractères";
    }

    if (!credentials.region) {
      newErrors.region = "La région est requise";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (validateForm()) {
      const finalCredentials = { ...credentials };
      if (!useSessionToken) {
        delete finalCredentials.sessionToken;
      }
      onNext(finalCredentials);
    }
  };

  const selectedRegion = getRegionByCode(credentials.region);

  return (
    <Fade in timeout={600}>
      <Box
        sx={{
          maxWidth: 600,
          mx: "auto",
          p: 4,
        }}
      >
        {/* Header */}
        <Box sx={{ textAlign: "center", mb: 4 }}>
          <Security sx={{ fontSize: "3rem", color: "primary.main", mb: 2 }} />
          <Typography
            variant="h4"
            fontWeight={700}
            color="text.primary"
            gutterBottom
          >
            Configuration AWS
          </Typography>
          <Typography
            variant="body1"
            color="text.secondary"
            sx={{ maxWidth: 480, mx: "auto", lineHeight: 1.6 }}
          >
            Saisissez vos credentials AWS pour permettre à l'assistant de gérer
            votre infrastructure.
          </Typography>
        </Box>

        {/* Security Notice */}
        <Alert
          severity="info"
          sx={{
            mb: 3,
            bgcolor: alpha("#059669", 0.1),
            border: "1px solid",
            borderColor: alpha("#10b981", 0.3),
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 500, mb: 0.5 }}>
             Vos credentials sont sécurisés
          </Typography>
          <Typography variant="body2">
            Vos credentials sont chiffrés et utilisés uniquement pour exécuter
            les actions que vous déclenchez.
          </Typography>
        </Alert>

        <Paper
          component="form"
          onSubmit={handleSubmit}
          elevation={0}
          sx={{
            p: 4,
            bgcolor: alpha("#1e293b", 0.8),
            backdropFilter: "blur(20px)",
            border: "1px solid",
            borderColor: alpha("#475569", 0.3),
            borderRadius: 3,
          }}
        >
          {/* Access Key ID */}
          <TextField
            label="AWS Access Key ID"
            fullWidth
            required
            value={credentials.accessKeyId}
            onChange={handleChange("accessKeyId")}
            error={!!errors.accessKeyId}
            helperText={
              errors.accessKeyId || "Format attendu : AKIA... (20 caractères)"
            }
            placeholder="AKIAIOSFODNN7EXAMPLE"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <Tooltip title="Commence par AKIA pour les clés permanentes ou ASIA pour les clés temporaires">
                    <Help sx={{ fontSize: 20, color: "text.secondary" }} />
                  </Tooltip>
                </InputAdornment>
              ),
            }}
            sx={{
              mb: 3,
              "& .MuiOutlinedInput-root": {
                bgcolor: alpha("#334155", 0.3),
                "& fieldset": {
                  borderColor: alpha("#475569", 0.5),
                },
                "&:hover fieldset": {
                  borderColor: "primary.main",
                },
                "&.Mui-focused fieldset": {
                  borderColor: "primary.main",
                },
              },
            }}
          />

          {/* Secret Access Key */}
          <TextField
            label="AWS Secret Access Key"
            fullWidth
            required
            type={showSecretKey ? "text" : "password"}
            value={credentials.secretAccessKey}
            onChange={handleChange("secretAccessKey")}
            error={!!errors.secretAccessKey}
            helperText={
              errors.secretAccessKey || "40 caractères alphanumériques"
            }
            placeholder="Votre clé secrète AWS"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={() => setShowSecretKey(!showSecretKey)}
                    edge="end"
                    sx={{ color: "text.secondary" }}
                  >
                    {showSecretKey ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
            sx={{
              mb: 3,
              "& .MuiOutlinedInput-root": {
                bgcolor: alpha("#334155", 0.3),
                "& fieldset": {
                  borderColor: alpha("#475569", 0.5),
                },
                "&:hover fieldset": {
                  borderColor: "primary.main",
                },
                "&.Mui-focused fieldset": {
                  borderColor: "primary.main",
                },
              },
            }}
          />

          {/* Region Selection */}
          <TextField
            select
            label="Région AWS"
            fullWidth
            required
            value={credentials.region}
            onChange={handleChange("region")}
            error={!!errors.region}
            helperText={
              selectedRegion
                ? `${selectedRegion.name} - ${selectedRegion.location}`
                : errors.region || "Choisissez la région la plus proche"
            }
            sx={{
              mb: 3,
              "& .MuiOutlinedInput-root": {
                bgcolor: alpha("#334155", 0.3),
                "& fieldset": {
                  borderColor: alpha("#475569", 0.5),
                },
                "&:hover fieldset": {
                  borderColor: "primary.main",
                },
                "&.Mui-focused fieldset": {
                  borderColor: "primary.main",
                },
              },
            }}
          >
            {AWS_REGIONS.map((region) => (
              <MenuItem key={region.code} value={region.code}>
                <Box>
                  <Typography variant="body1">{region.name}</Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ fontSize: "0.75rem" }}
                  >
                    {region.code} • {region.location}
                  </Typography>
                </Box>
              </MenuItem>
            ))}
          </TextField>

          {/* Session Token (Optional) */}
          <FormControlLabel
            control={
              <Switch
                checked={useSessionToken}
                onChange={(e) => setUseSessionToken(e.target.checked)}
                color="primary"
              />
            }
            label="Utiliser un Session Token (optionnel)"
            sx={{ mb: useSessionToken ? 2 : 3 }}
          />

          {useSessionToken && (
            <TextField
              label="AWS Session Token"
              fullWidth
              type={showSessionToken ? "text" : "password"}
              value={credentials.sessionToken}
              onChange={handleChange("sessionToken")}
              helperText="Pour les credentials temporaires (STS)"
              placeholder="Token de session temporaire"
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowSessionToken(!showSessionToken)}
                      edge="end"
                      sx={{ color: "text.secondary" }}
                    >
                      {showSessionToken ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              sx={{
                mb: 3,
                "& .MuiOutlinedInput-root": {
                  bgcolor: alpha("#334155", 0.3),
                  "& fieldset": {
                    borderColor: alpha("#475569", 0.5),
                  },
                  "&:hover fieldset": {
                    borderColor: "primary.main",
                  },
                  "&.Mui-focused fieldset": {
                    borderColor: "primary.main",
                  },
                },
              }}
            />
          )}

          {/* Help Link */}
          <Box sx={{ mb: 3, textAlign: "center" }}>
            <Link
              href="https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html"
              target="_blank"
              rel="noopener noreferrer"
              sx={{
                color: "primary.main",
                textDecoration: "none",
                "&:hover": { textDecoration: "underline" },
              }}
            >
              Comment créer des clés d'accès AWS ?
            </Link>
          </Box>

          {/* Action Buttons */}
          <Box sx={{ display: "flex", gap: 2, pt: 2 }}>
            <Button
              variant="outlined"
              startIcon={<ArrowBack />}
              onClick={onBack}
              disabled={loading}
              sx={{
                borderColor: alpha("#475569", 0.5),
                color: "text.secondary",
                "&:hover": {
                  borderColor: "text.primary",
                  bgcolor: alpha("#475569", 0.1),
                },
              }}
            >
              Précédent
            </Button>

            <Button
              type="submit"
              variant="contained"
              endIcon={<ArrowForward />}
              disabled={loading}
              sx={{
                flex: 1,
                py: 1.5,
                fontWeight: 600,
                background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
                "&:hover": {
                  background:
                    "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)",
                },
                "&:disabled": {
                  background: alpha("#6366f1", 0.3),
                },
              }}
            >
              {loading ? "Validation..." : "Valider et continuer"}
            </Button>
          </Box>
        </Paper>
      </Box>
    </Fade>
  );
}
