import {
  Box,
  Button,
  Chip,
  Tooltip,
  alpha,
  CircularProgress,
} from "@mui/material";
import { Construction, Chat as ChatIcon } from "@mui/icons-material";

import { useChatMode } from "../../contexts/ChatModeContext";
import { hasAWSCredentials } from "../../utils/awsCredentialsHelper";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axiosClient, {
  setChatMode as apiSetChatMode,
  startDAC as apiStartDAC,
} from "../../api/axiosClient";

interface ChatModeToggleProps {
  sessionId?: number | string | null;
  chatId?: any; // Accept any type to avoid TypeScript casting issues
  onNeedCredentials?: () => void;
  onModeChanged?: (mode: string) => void;
  onBotMessage?: (msg: string) => void;
}

const ONBOARDING_ROUTE = "/onboarding/aws";

// Helper pour normaliser et valider les IDs
function toPositiveInt(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) && value > 0 ? value : null;
  }
  if (typeof value === "string") {
    const n = Number.parseInt(value, 10);
    return Number.isFinite(n) && n > 0 ? n : null;
  }
  return null;
}

export default function ChatModeToggle({
  sessionId,
  chatId,
  onNeedCredentials,
  onModeChanged,
  onBotMessage,
}: ChatModeToggleProps) {
  const { chatMode, setChatMode } = useChatMode();
  const [hasCredentials, setHasCredentials] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const navigate = useNavigate();

  const refreshCredentialsState = useCallback(async () => {
    try {
      const result = await hasAWSCredentials();
      setHasCredentials(Boolean(result));
    } catch {
      setHasCredentials(false);
    }
  }, []);

  // Juste pour afficher l'état du bouton/tooltip (pas pour activer DAC)
  useEffect(() => {
    void refreshCredentialsState();

    // Si tu reviens de la page credentials et que ça écrit en DB, on refresh au focus
    const onFocus = () => void refreshCredentialsState();
    window.addEventListener("focus", onFocus);

    return () => {
      window.removeEventListener("focus", onFocus);
    };
  }, [refreshCredentialsState]);

  const switchToFree = useCallback(async () => {
    const cid = toPositiveInt(chatId);

    if (chatMode === "free" || cid === null) return;

    setLoading(true);
    try {
      // IMPORTANT: DOIT appeler le backend pour mettre à jour session.mode
      // C'est la SOURCE DE VÉRITÉ côté backend
      const res = await axiosClient.post(`/chats/${cid}/switch_mode`, {
        mode: "free",
      });

      // Ensuite, on bascule l'UI UNIQUEMENT si la requête a réussi
      setChatMode("free");
      onModeChanged?.("free");

      // FIX: Ne pas recharger les messages - le Free mode gère ça localement
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || err?.message;
      console.error(
        `[ChatModeToggle] Error switching to FREE (${status}):`,
        detail,
      );
      //  Ne JAMAIS changer le state si l'API a échoué
      alert(`Impossible de changer de mode: ${detail}`);
    } finally {
      setLoading(false);
    }
  }, [chatMode, chatId, setChatMode, onModeChanged]);

  const handleSwitchToDAC = useCallback(async () => {
    const sid = toPositiveInt(sessionId);
    const cid = toPositiveInt(chatId);

    // Logs utiles (à garder le temps du debug)

    // Validation stricte (évite undefined, "", NaN, 0)
    if (sid === null || cid === null) {
      console.error(
        "Session ID ou Chat ID invalide (impossible d'activer DAC).",
        { sessionId, chatId, sid, cid },
      );
      return;
    }

    if (chatMode === "dac") return;

    setLoading(true);
    try {
      // 1) Check credentials DB
      const okCreds = await hasAWSCredentials();
      if (!okCreds) {
        onNeedCredentials?.();
        navigate(ONBOARDING_ROUTE, {
          replace: false,
          state: { redirectTo: "/chat", reason: "missing_aws_credentials" },
        });
        return;
      }

      // 2) Switch mode via /chats/{id}/switch_mode (SOURCE DE VÉRITÉ)
      const modeRes = await axiosClient.post(`/chats/${cid}/switch_mode`, {
        mode: "dac",
      });

      // 3) Start DAC session (backend: /chats/switch_to_dac)
      const dacResp = await apiStartDAC(cid, sid);

      // Si OK, on bascule l'UI en dac
      setChatMode("dac");
      onModeChanged?.("dac");

      if (dacResp?.bot_message && onBotMessage) {
        onBotMessage(dacResp.bot_message);
      }

      void refreshCredentialsState();
    } catch (error: any) {
      const status = error?.response?.status;
      const detail = error?.response?.data?.detail || error?.message;
      console.error(
        `[ChatModeToggle] Error switching to DAC (${status}):`,
        detail,
      );

      //  Ne JAMAIS changer le state si l'API a échoué
      alert(`Impossible de changer de mode: ${detail}`);

      if (status === 400) {
        onNeedCredentials?.();
        navigate(ONBOARDING_ROUTE, {
          replace: false,
          state: { redirectTo: "/chat", reason: "missing_aws_credentials" },
        });
      }
    } finally {
      setLoading(false);
    }
  }, [
    sessionId,
    chatId,
    chatMode,
    setChatMode,
    onModeChanged,
    onNeedCredentials,
    navigate,
    refreshCredentialsState,
    onBotMessage,
  ]);

  const handleOpenAWSCredentials = useCallback(() => {
    navigate(ONBOARDING_ROUTE, {
      replace: false,
      state: {
        redirectTo: "/chat",
        reason: hasCredentials
          ? "update_aws_credentials"
          : "missing_aws_credentials",
      },
    });
  }, [hasCredentials, navigate]);

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        p: 1.5,
        borderRadius: "8px",
        backgroundColor: alpha("#334155", 0.4),
        borderBottom: "1px solid",
        borderColor: "divider",
      }}
    >
      {/* Chip Free Chat */}
      <Tooltip
        title={chatMode === "free" ? "Mode actif" : "Cliquer pour activer"}
      >
        <Box component="span">
          <Chip
            icon={<ChatIcon />}
            label="Free Chat"
            variant={chatMode === "free" ? "filled" : "outlined"}
            color={chatMode === "free" ? "primary" : "default"}
            sx={{
              cursor: loading ? "not-allowed" : "pointer",
              fontWeight: chatMode === "free" ? "bold" : "normal",
              transition: "all 0.3s ease",
              opacity: loading ? 0.6 : 1,
            }}
            onClick={switchToFree}
            disabled={loading}
          />
        </Box>
      </Tooltip>

      {/* Bouton Mode DAC */}
      <Tooltip
        title={
          hasCredentials
            ? "Activer le mode DAC (AWS)"
            : "Ajouter des credentials AWS pour activer le mode DAC"
        }
      >
        {/* Wrapper Box indispensable car Tooltip + disabled button */}
        <Box component="span">
          <Button
            variant={chatMode === "dac" ? "contained" : "outlined"}
            startIcon={
              loading ? <CircularProgress size={20} /> : <Construction />
            }
            onClick={handleSwitchToDAC}
            disabled={loading}
            sx={{
              fontWeight: chatMode === "dac" ? "bold" : "normal",
              transition: "all 0.3s ease",
              color: chatMode === "dac" ? "white" : undefined,
              backgroundColor: chatMode === "dac" ? "#FF9800" : undefined,
              "&:hover": {
                backgroundColor: chatMode === "dac" ? "#F57C00" : undefined,
              },
              opacity: loading ? 0.6 : 1,
            }}
          >
            Mode DAC
          </Button>
        </Box>
      </Tooltip>

      {/* Status indicator */}
      <Tooltip
        title={
          hasCredentials
            ? "Modifier les credentials AWS"
            : "Configurer les credentials AWS"
        }
      >
        <Chip
          label={hasCredentials ? "AWS actif" : "AWS non actif"}
          size="small"
          color={hasCredentials ? "success" : "warning"}
          variant={hasCredentials ? "filled" : "outlined"}
          onClick={handleOpenAWSCredentials}
          sx={{ cursor: "pointer" }}
        />
      </Tooltip>
    </Box>
  );
}
