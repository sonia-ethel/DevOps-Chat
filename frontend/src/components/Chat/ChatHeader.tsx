// src/components/Chat/ChatHeader.tsx

import React from "react";
import {
  Box,
  Typography,
  IconButton,
  Chip,
  Tooltip,
  alpha,
  useTheme,
} from "@mui/material";
import {
  Cloud as CloudIcon,
  AutoAwesome as AutoAwesomeIcon,
  CircleNotifications as CircleNotificationsIcon,
} from "@mui/icons-material";
import {
  CHAT_STATE_LABELS,
  CHAT_STATE_COLORS,
  type ChatState,
} from "../../states/chatStates";

interface ChatHeaderProps {
  sessionId: string | null;
  chatState: string;
  onAWSPanelOpen: () => void;
}

const ChatHeader: React.FC<ChatHeaderProps> = ({
  sessionId,
  chatState,
  onAWSPanelOpen,
}) => {
  const theme = useTheme();
  const hasSession = !!sessionId;

  //  Vérification que le state est valide
  const isValidChatState = (state: string): state is ChatState =>
    Object.keys(CHAT_STATE_LABELS).includes(state);

  const currentState = isValidChatState(chatState)
    ? chatState
    : "awaiting_intent";
  const stateLabel = CHAT_STATE_LABELS[currentState];
  const stateColor = CHAT_STATE_COLORS[currentState];

  //  Icône selon l'état
  const getStateIcon = () => {
    switch (currentState) {
      case "executing":
        return (
          <CircleNotificationsIcon
            sx={{ fontSize: 16, animation: "pulse 2s infinite" }}
          />
        );
      case "deployed":
      case "completed":
        return <AutoAwesomeIcon sx={{ fontSize: 16 }} />;
      default:
        return <CircleNotificationsIcon sx={{ fontSize: 16 }} />;
    }
  };

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        px: 3,
        py: 2,
        backgroundColor: "background.paper",
        borderBottom: "1px solid",
        borderColor: "divider",
        backdropFilter: "blur(10px)",
        background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.05)} 0%, ${alpha(theme.palette.background.paper, 0.95)} 100%)`,
      }}
    >
      {/*  Project Context & État */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Box
            sx={{
              width: 32,
              height: 32,
              borderRadius: "8px",
              background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: theme.shadows[2],
            }}
          >
            <AutoAwesomeIcon sx={{ color: "white", fontSize: 20 }} />
          </Box>
          <Typography
            variant="h6"
            sx={{
              fontWeight: 700,
              background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
              backgroundClip: "text",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              letterSpacing: "0.5px",
            }}
          >
            DevOps Assistant
          </Typography>
        </Box>

        {/* État actuel avec indicateur visuel */}
        <Chip
          icon={getStateIcon()}
          label={stateLabel}
          size="small"
          sx={{
            bgcolor: alpha(stateColor, 0.1),
            color: stateColor,
            border: `1px solid ${alpha(stateColor, 0.3)}`,
            fontWeight: 500,
            "& .MuiChip-icon": {
              color: stateColor,
            },
            "@keyframes pulse": {
              "0%": { opacity: 1 },
              "50%": { opacity: 0.6 },
              "100%": { opacity: 1 },
            },
          }}
        />
      </Box>

      {/*  Actions */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        {/* Indicateur de session */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mr: 1 }}>
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              bgcolor: hasSession ? "success.main" : "warning.main",
              animation: hasSession ? "pulse 2s infinite" : "none",
              "@keyframes pulse": {
                "0%": { opacity: 1 },
                "50%": { opacity: 0.5 },
                "100%": { opacity: 1 },
              },
            }}
          />
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ fontSize: "0.75rem" }}
          >
            {hasSession ? "Connecté" : "Initialisation..."}
          </Typography>
        </Box>

        {/* Bouton AWS Panel */}
        <Tooltip title="Gérer mes instances AWS" arrow>
          <Box component="span">
            <IconButton
              onClick={onAWSPanelOpen}
              disabled={!hasSession}
              sx={{
                bgcolor: hasSession ? "primary.main" : "action.disabled",
                color: hasSession ? "primary.contrastText" : "action.disabled",
                width: 40,
                height: 40,
                "&:hover": {
                  bgcolor: hasSession ? "primary.dark" : "action.disabled",
                  transform: hasSession ? "scale(1.05)" : "none",
                },
                "&:disabled": {
                  bgcolor: "action.disabled",
                  color: "action.disabled",
                },
                transition: "all 0.2s ease-in-out",
                boxShadow: hasSession ? theme.shadows[2] : "none",
              }}
            >
              <CloudIcon sx={{ fontSize: 20 }} />
            </IconButton>
          </Box>
        </Tooltip>
      </Box>

    </Box>
  );
};

export default ChatHeader;
