// © 2024–2026 TOURE Arnaud Patrick
// Licensed under the MIT License
// Chat Page - Main page for chat interface with DAC mode

// src/pages/ChatPage.tsx

import {
  Box,
  alpha,
  Alert,
  Button,
  LinearProgress,
  Typography,
} from "@mui/material";
import ChatSidebar from "../components/Chat/Sidebar";
import ChatWindow from "../components/Chat/ChatWindow";
import ChatInput from "../components/Chat/ChatInput";
import ChatHeader from "../components/Chat/ChatHeader";
import ChatTopBar from "../components/Chat/ChatTopBar"; // TopBar with profile menu
import ChatModeToggle from "../components/Chat/ChatModeToggle"; // 
import AWSCredentialsWarning from "../components/Chat/AWSCredentialsWarning";
import { useChatManager } from "../hooks/useChatManager";
import { useChatMode } from "../contexts/ChatModeContext"; // 
import ProviderSelector from "../components/Chat/ProviderSelector";
import CredentialsForm from "../components/Chat/CredentialsForm";
import InstanceSelector from "../components/Chat/InstanceSelector";
import AWSResourcePanel from "../components/AWS/AWSResourcePanel";
import AuditProgressWidget from "../components/AuditProgressWidget";
import { useExecution } from "../contexts/ExecutionContext";
import { useExecutionPolling } from "../hooks/useExecutionPolling";
import type { ChatState } from "../states/chatStates";
import {
  getAWSCredentialsForChat,
  hasAWSCredentials,
} from "../utils/awsCredentialsHelper";
import axiosClient from "../api/axiosClient";
import { useState, useEffect, useCallback, useRef } from "react";
// États qui affichent les composants de setup
const SETUP_STATES: ChatState[] = [
  "awaiting_provider",
  "awaiting_inventory",
  "awaiting_instance_selection",
];

// États qui affichent l'interface de chat
const CHAT_INTERFACE_STATES: ChatState[] = [
  "ready",
  "awaiting_intent",
  "awaiting_smart_confirmation",
  "executing",
  "deployed",
  "awaiting_instances",
  "awaiting_confirmation",
  "awaiting_execution",
  "free_chat",
  "awaiting_audit_tool",
  "awaiting_credentials",
  "deletion_mode",
];

// --- Persistence de l'ID du chat sélectionné ---
const LS_ACTIVE_CHAT = "dac_active_chat_id";
function saveActiveChatId(id: number) {
  localStorage.setItem(LS_ACTIVE_CHAT, String(id));
}
function loadActiveChatId(): number | null {
  const v = localStorage.getItem(LS_ACTIVE_CHAT);
  return v ? Number(v) : null;
}
// ---

export default function ChatPage() {
  //  État local pour le panel AWS
  const [awsPanelOpen, setAwsPanelOpen] = useState(false);
  const [showAWSWarning, setShowAWSWarning] = useState(false);
  const [credentialsLoaded, setCredentialsLoaded] = useState(false);

  //  Étape 5-7: Polling state pour l'audit
  const [currentExecutionId, setCurrentExecutionId] = useState<number | null>(
    null,
  );
  const polling = useExecutionPolling(currentExecutionId, true);

  //  Mode Free/DAC
  const { chatMode, setChatMode } = useChatMode();

  //  Contexte projet
  // const { currentProject, loading: projectLoading } = useProjectContext();

  const {
    chats,
    selectedChatId: rawSelectedChatId,
    sessionId: rawSessionId,
    chatState,
    setChatState,
    isTyping,
    isRecovering,
    reloadFlag,
    messages,
    setMessages,
    createNewChat,
    renameChat,
    deleteChat,
    sendMessage,
    selectChat,
    refreshChats,
    //  DAC UI State
    uiState,
    setUiState,
    availableInstances,
    setAvailableInstances,
    auditRunning,
    setAuditRunning,
    //  Execution Stream
    executionId,
    setExecutionId,
    jwtToken,
  } = useChatManager();

  //  Normalisation systématique
  const normalizedChatId =
    rawSelectedChatId != null ? Number(rawSelectedChatId) : null;
  const normalizedSessionId =
    rawSessionId != null ? Number(rawSessionId) : null;

  //  Gestion d'exécution (empêcher l'empilement)
  const { runningExecution, startExecution, endExecution } = useExecution();

  //  Démarrer l'exécution quand un execution_id est reçu
  useEffect(() => {
    if (executionId && !runningExecution) {
      const success = startExecution({
        executionId,
        chatId: normalizedChatId || 0,
        sessionId: String(normalizedSessionId || ""),
        startedAt: new Date(),
      });
      if (!success) {
        console.warn(
          "[Chat] Impossible de démarrer l'exécution - une autre est déjà en cours",
        );
      }
    }
  }, [
    executionId,
    runningExecution,
    startExecution,
    normalizedChatId,
    normalizedSessionId,
  ]);

  // Trouver le chat sélectionné selon la structure API (chat_id, session_id)
  const selectedChat = chats.find(
    (c: any) => c.chat_id === normalizedChatId || c.id === normalizedChatId,
  );

  // Alias pour compatibilité
  const selectedChatId = normalizedChatId;
  const sessionId = normalizedSessionId;

  //  Cleanup du stream quand on change de chat ou que le composant se démonte
  useEffect(() => {
    return () => {
      // Quand on change de chat, nettoyer l'exécution en cours
      if (executionId) {
        console.log("[Chat]  Nettoyage stream au changement de chat");
        setExecutionId(null);
        setAuditRunning(false);
        endExecution();
      }
    };
  }, [
    normalizedChatId,
    executionId,
    setExecutionId,
    setAuditRunning,
    endExecution,
  ]);

  const isExecuting = ["executing", "running", "in_progress"].includes(
    chatState ?? "",
  );
  const inputDisabled = isExecuting;

  const AuditProgress = ({
    title,
    subtitle,
  }: {
    title: string;
    subtitle: string;
  }) => (
    <Box
      sx={{
        mt: 2,
        px: 2,
        py: 1.5,
        borderRadius: 2,
        bgcolor: alpha("#0f172a", 0.6),
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
        {title}
      </Typography>
      <Typography variant="body2" sx={{ opacity: 0.8, mb: 1 }}>
        {subtitle}
      </Typography>
      <LinearProgress />
      <Typography
        variant="caption"
        sx={{ display: "block", mt: 1, opacity: 0.7 }}
      >
        Cette opération peut prendre 1 à 2 minutes.
      </Typography>
    </Box>
  );

  const didCheckAwsRef = useRef(false);

  // Charger les credentials AWS une seule fois au mount
  useEffect(() => {
    if (didCheckAwsRef.current) return;
    didCheckAwsRef.current = true;

    if (auditRunning) {
      // OK Ne pas lancer la vérif réseau pendant un audit
      setCredentialsLoaded(true);
      return;
    }

    const checkCredentials = async () => {
      try {
        const hasCredentials = await hasAWSCredentials(false);
        setShowAWSWarning(!hasCredentials);
      } catch (error) {
        console.warn("Could not check AWS credentials:", error);
        setShowAWSWarning(true);
      } finally {
        setCredentialsLoaded(true);
      }
    };

    checkCredentials();
  }, []);

  //  Callback : provider sélectionné
  const handleProviderSelected = async (providerType: string | null) => {
    if (!providerType) return; // Ignore si null

    // For AWS provider, check if credentials are already stored
    if (providerType === "aws") {
      // OK Skip network check pendant un audit
      const hasCredentials = await hasAWSCredentials(auditRunning);
      if (hasCredentials) {
        setChatState("awaiting_intent");
        return;
      }
    }

    setChatState("awaiting_credentials");
  };

  //  Callback : credentials soumis
  const handleCredentialsSubmitted = async (creds: any) => {
    // For AWS, try to use stored credentials instead of manually entered ones
    try {
      const awsCredentials = await getAWSCredentialsForChat();
      if (awsCredentials) {
        // TODO: Pass AWS credentials to the chat system
      }
    } catch (error) {
      console.warn(
        "Could not load stored AWS credentials, using provided ones:",
        error,
      );
    }

    setChatState("awaiting_intent");
  };

  //  Callback : instances sélectionnées
  const handleInstancesSelected = (_ids: number[]) => {
    // NOTE: L'envoi est géré par InstanceSelector.handleConfirm()
    // La réponse backend est traitée via handleInstanceResponse()
  };

  const handleInstanceResponse = (data: any) => {
    if (!data || typeof data !== "object") return;

    const normalizedState = data?.session_state ?? data?.state;
    const normalizedExtra = data?.extra || {};
    const normalizedAvailableInstances =
      data?.available_instances ?? normalizedExtra?.available_instances ?? [];
    const normalizedExecutionId =
      data?.execution_id_db ||
      normalizedExtra?.execution_id_db ||
      data?.execution_id ||
      normalizedExtra?.execution_id;

    const assistantText =
      typeof data?.message === "string"
        ? data.message
        : JSON.stringify(data, null, 2);

    if (assistantText?.trim()) {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-${Date.now()}`,
          sender: "bot",
          text: assistantText,
          created_at: new Date().toISOString(),
          extra: {
            ...normalizedExtra,
            state: normalizedState,
            available_instances: normalizedAvailableInstances,
          },
        },
      ]);
    }

    if (normalizedState) {
      setChatState(normalizedState);
    }

    if (
      Array.isArray(normalizedAvailableInstances) &&
      normalizedAvailableInstances.length > 0
    ) {
      setAvailableInstances(normalizedAvailableInstances);
    }
    if (normalizedExecutionId) {
      setExecutionId(normalizedExecutionId);
      //  Étape 7: Activer le polling pour cet execution_id
      setCurrentExecutionId(normalizedExecutionId);
    }

    // Une fois la réponse reçue, on masque le sélecteur
    setUiState(null);
  };

  const [currentSessionState, setCurrentSessionState] =
    useState<string>("awaiting_intent");
  const [wasReset, setWasReset] = useState(false);

  // Mapping d'aide pour les états (doit matcher le backend)
  const stateHelp: Record<string, string> = {
    awaiting_instance_selection:
      "Tu es dans Configuration -> sélection d'instances. Réponds par 'toutes' ou '1,3'.",
    awaiting_audit_instance_selection:
      "Tu es dans Audit -> sélection d'instances. Réponds par 'toutes' ou '1,3'.",
    awaiting_audit_confirmation:
      "Tu es dans Audit -> confirmation. Réponds par 'ok' pour lancer, ou 'annuler'.",
    awaiting_monitoring_instance_selection:
      "Tu es dans Monitoring -> sélection d'instances. Réponds par 'toutes' ou '1,3'.",
    awaiting_monitoring_confirmation:
      "Tu es dans Monitoring -> confirmation. Réponds par 'ok' pour lancer, ou 'annuler'.",
    awaiting_ssm_fix_confirm:
      "Tu es dans SSM -> confirmation bootstrap. Réponds par 'oui' ou 'non'.",
    deletion_mode: "Tu es dans Suppression. Donne des IDs, ou tape 'lister'.",
  };

  // Patch sendMessage pour capter session_state
  const wrappedSendMessage = async (msg: string) => {
    const res = await sendMessage(msg);
    if (res && typeof res === "object" && "session_state" in res) {
      const newState = res.session_state as string;
      // si on était dans un état actif et que ça revient à awaiting_intent -> reset
      if (
        currentSessionState &&
        currentSessionState !== "awaiting_intent" &&
        newState === "awaiting_intent"
      ) {
        setWasReset(true);
        setTimeout(() => setWasReset(false), 6000);
      }
      setCurrentSessionState(newState);
    }
    return res;
  };

  // Affiche la bannière si on n'est pas dans l'état neutre
  const showResumeBanner =
    currentSessionState && currentSessionState !== "awaiting_intent";
  const resumeHint =
    stateHelp[currentSessionState] || "Décris ta demande en une phrase.";

  // Affiche la bannière spéciale si la session a expiré (reset)
  const showSessionResetBanner = wasReset;

  // Au chargement, relire activeChatId et sélectionner ce chat si possible
  useEffect(() => {
    const persistedId = loadActiveChatId();
    if (persistedId && chats.some((c) => c.id === persistedId)) {
      selectChat(persistedId);
    }
  }, [chats]);

  // Au montage: charger la liste, sélectionner un chat, charger ses messages
  useEffect(() => {
    if (selectedChatId) return;
    let cancelled = false;

    void (async () => {
      const list = await refreshChats();
      if (cancelled) return;

      const persistedId = loadActiveChatId();
      const hasPersisted =
        persistedId && list.some((c) => c.id === Number(persistedId));
      const targetId = hasPersisted
        ? Number(persistedId)
        : (list[0]?.id ?? null);

      if (targetId) {
        await selectChat(Number(targetId));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedChatId, refreshChats, selectChat]);

  // Quand l'utilisateur clique un chat, persister l'ID
  function handleSelectChat(id: number | string | null) {
    const normalizedId = id != null ? Number(id) : null;
    if (normalizedId !== null) saveActiveChatId(normalizedId);
    // Synchronise le mode du chat sélectionné avec le contexte global
    const chat = chats.find((c) => c.id === normalizedId);
    if (chat?.mode) {
      setChatMode(chat.mode);
    }
    selectChat(normalizedId);
  }

  useEffect(() => {
    // Si on a un chat sélectionné mais que l'UI chat ne s'affiche pas, on force un état safe
    if (
      selectedChatId &&
      !CHAT_INTERFACE_STATES.includes(chatState as ChatState)
    ) {
      setChatState("ready");
    }
  }, [selectedChatId, chatState, setChatState]);

  return (
    <Box
      sx={{
        display: "flex",
        height: "100vh",
        bgcolor: "background.default",
        overflow: "hidden",
        flexDirection: { xs: "column", md: "row" },
      }}
    >
      {/* Sidebar avec son propre scroll - FIXE */}
      <Box
        sx={{
          height: "100vh",
          overflowY: "auto",
          minWidth: 0,
          flex: "0 0 auto",
        }}
      >
        <ChatSidebar
          chats={chats}
          selectedChatId={selectedChatId}
          onDeleteChat={deleteChat}
          onRenameChat={renameChat}
          onCreateNewChat={createNewChat}
          onSelectChat={handleSelectChat}
          onRefreshChats={refreshChats}
        />
      </Box>

      {/* Main content area - colonne principale */}
      <Box
        sx={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          bgcolor: "background.default",
          position: "relative",
          overflow: "hidden",
          height: "100vh",
        }}
      >
        {/* Resume Banner */}
        {showResumeBanner && (
          <Alert
            severity="info"
            sx={{
              borderRadius: 0,
              mb: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
            action={
              <Button
                color="inherit"
                size="small"
                onClick={() => wrappedSendMessage("annuler")}
              >
                Annuler étape
              </Button>
            }
          >
            <strong>État courant :</strong> {currentSessionState}
            <br />
            <span>{resumeHint}</span>
          </Alert>
        )}
        {/* Bannière session expirée (FLOW_TIMEOUT) */}
        {showSessionResetBanner && (
          <Alert
            severity="info"
            sx={{
              borderRadius: 0,
              mb: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            Session reprise, retour au menu
          </Alert>
        )}

        {/*  TopBar with profile menu - FIXED at top */}
        <ChatTopBar />

        {/* Header + Mode Bar - FIXE EN HAUT */}
        <Box sx={{ flex: "0 0 auto", overflow: "hidden" }}>
          {/*  DEBUG PANEL (TEMPORAIRE - à supprimer après fix) */}
          {process.env.NODE_ENV === "development" && (
            <Box
              sx={{
                bgcolor: "warning.main",
                color: "warning.contrastText",
                px: 2,
                py: 0.5,
                fontSize: "0.75rem",
                fontFamily: "monospace",
                display: "flex",
                gap: 2,
                borderBottom: "1px solid",
                borderColor: "divider",
              }}
            >
              <span> UI selectedChat: {selectedChat?.id || "null"}</span>
              <span> API activeChatId: {selectedChatId || "null"}</span>
              <span> sessionId: {sessionId || "null"}</span>
            </Box>
          )}

          {/* Header professionnel */}
          <ChatHeader
            sessionId={sessionId}
            chatState={chatState}
            onAWSPanelOpen={() => setAwsPanelOpen(true)}
          />

          {/*  Mode Toggle Free/DAC */}
          <ChatModeToggle
            sessionId={selectedChat?.session_id ?? sessionId ?? undefined}
            chatId={selectedChat?.id ?? selectedChatId}
            onNeedCredentials={() => setAwsPanelOpen(true)}
            onModeChanged={(mode) => {
              if (!selectedChatId) return;
              void (async () => {
                await refreshChats();
                await selectChat(selectedChatId);
              })();
            }}
          />
        </Box>

        {/* AWS Credentials Warning - Seulement en mode DAC */}
        {credentialsLoaded && showAWSWarning && chatMode === "dac" && (
          <Box sx={{ px: 3, pt: 2 }}>
            <AWSCredentialsWarning onDismiss={() => setShowAWSWarning(false)} />
          </Box>
        )}

        {/* Setup steps */}
        {SETUP_STATES.includes(chatState as ChatState) && (
          <Box
            sx={{
              p: 3,
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Box sx={{ maxWidth: 600, width: "100%" }}>
              {chatState === "awaiting_provider" && (
                <ProviderSelector onProviderSelected={handleProviderSelected} />
              )}
              {chatState === "awaiting_credentials" && (
                <CredentialsForm
                  onSubmit={handleCredentialsSubmitted}
                  provider=""
                />
              )}
              {chatState === "awaiting_inventory" && (
                <InstanceSelector
                  instances={[]}
                  onConfirm={handleInstancesSelected}
                  onResponse={handleInstanceResponse}
                />
              )}
              {chatState === "awaiting_instance_selection" && (
                <ChatWindow
                  chatId={selectedChatId}
                  isTyping={isTyping}
                  reloadTrigger={reloadFlag}
                  onInstancesSelected={handleInstancesSelected}
                  onInstanceResponse={handleInstanceResponse}
                  onCreateNew={createNewChat}
                />
              )}
            </Box>
          </Box>
        )}

        {/* Chat interface - style ChatGPT avec messages scrollables + input sticky */}

        {/* Toujours afficher ChatWindow + ChatInput si un chat est sélectionné */}
        {selectedChatId && (
          <>
            {/*  Étape 6-8: Execution Progress Widget (tous les task_types) */}
            <Box sx={{ px: 2, pt: 2 }}>
              <AuditProgressWidget
                status={polling.status as any}
                progress={polling.progress}
                message={polling.message}
                executionId={currentExecutionId}
              />
            </Box>

            {/* Zone de messages scrollable - CRITIQUE: minHeight: 0 */}
            <Box
              sx={{
                flex: "1 1 auto",
                overflowY: "auto", //  Scroll indépendant pour les messages
                minHeight: 0, // CRITIQUE: sinon le flex se casse
                display: "flex",
                flexDirection: "column",
                px: 2,
                pb: 1,
              }}
            >
              <ChatWindow
                chatId={selectedChatId}
                sessionId={sessionId}
                isTyping={isTyping}
                reloadTrigger={reloadFlag}
                messages={messages}
                setMessages={setMessages}
                onInstancesSelected={handleInstancesSelected}
                onInstanceResponse={handleInstanceResponse}
                onCreateNew={createNewChat}
              />

              {auditRunning && (
                <AuditProgress
                  title="Audit en cours"
                  subtitle="Analyse de sécurité et de santé des instances…"
                />
              )}

              {/*  DAC - Instance Selection UI (audit/monitoring/configure) */}
              {uiState?.type === "instance_selection" && (
                <Box sx={{ px: 2, py: 2 }}>
                  <InstanceSelector
                    instances={availableInstances}
                    state={
                      uiState.mode === "audit"
                        ? "awaiting_audit_instance_selection"
                        : uiState.mode === "monitoring"
                          ? "awaiting_monitoring_instance_selection"
                          : "awaiting_instance_selection"
                    }
                    onConfirm={(selected) => {
                      console.log(
                        `[DAC] ${uiState.mode} instances selected:`,
                        selected,
                      );
                      handleInstancesSelected(selected);
                    }}
                    onResponse={handleInstanceResponse}
                    sessionId={sessionId ?? undefined}
                    chatId={selectedChatId ?? undefined}
                  />
                </Box>
              )}

              {/* Backward compat: old audit_instance_selection type */}
              {uiState?.type === "audit_instance_selection" && (
                <Box sx={{ px: 2, py: 2 }}>
                  <InstanceSelector
                    instances={availableInstances}
                    state="awaiting_audit_instance_selection"
                    onConfirm={(selected) => {
                      console.log("[DAC] Instances selected:", selected);
                      handleInstancesSelected(selected);
                    }}
                    onResponse={handleInstanceResponse}
                    sessionId={sessionId ?? undefined}
                    chatId={selectedChatId ?? undefined}
                  />
                </Box>
              )}
            </Box>

            {/* Input sticky en bas - FIXE */}
            <Box
              sx={{
                flex: "0 0 auto", // Ne jamais se compresser
                borderTop: "1px solid",
                borderColor: "divider",
                bgcolor: alpha("#1e293b", 0.3),
                backdropFilter: "blur(20px)",
              }}
            >
              <ChatInput
                chatId={selectedChatId}
                onSend={sendMessage}
                disabled={inputDisabled}
              />
            </Box>
          </>
        )}

        {/* Si session introuvable, afficher bouton "Reprendre" */}
        {!sessionId && (
          <Box sx={{ p: 2, textAlign: "center" }}>
            <Button
              variant="outlined"
              color="primary"
              onClick={() => window.location.reload()}
              size="small"
            >
              Reprendre la session
            </Button>
          </Box>
        )}

        {/*  AWS Resource Panel */}
        <AWSResourcePanel
          open={awsPanelOpen}
          onClose={() => setAwsPanelOpen(false)}
          sessionId={sessionId}
        />
      </Box>
    </Box>
  );
}
