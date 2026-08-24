// © 2024–2026 TOURE Arnaud Patrick
// Licensed under the MIT License

import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import axiosClient, { startChat, renameChat } from "../api/axiosClient";
import { useChatMode } from "../contexts/ChatModeContext";
import { parseServerDate, sortMessagesByDate } from "../utils/dateUtils";
import { useAuth } from "../context/AuthContext";

interface Chat {
  id: number;
  name: string;
  session_id: string;
  created_at?: string;
  mode?: "free" | "dac"; // Mode du chat (source de vérité depuis backend)
}

export interface ChatMessage {
  id: string;
  sender: "user" | "assistant" | "bot";
  text: string;
  created_at: string;
  loading?: boolean;
  extra?: any; // État, instances disponibles, etc
}

export function useChatManager() {
  const { id: projectIdParam } = useParams<{ id: string }>();
  const { chatMode, setChatMode } = useChatMode(); // Recuperation du mode Free/DAC
  const { user, loading: authLoading } = useAuth(); // Vérifier auth avant API calls
  const [chats, setChats] = useState<Chat[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [chatState, setChatState] = useState<string>("free_chat"); // Mode decouverte par defaut
  const [isTyping, setIsTyping] = useState(false);
  const [isRecovering, setIsRecovering] = useState(false);
  const [reloadFlag, setReloadFlag] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]); // Messages (Free Chat seulement)

  //  DAC UI State (InstanceSelector, etc)
  const [uiState, setUiState] = useState<any>(null);
  const [availableInstances, setAvailableInstances] = useState<any[]>([]);
  const [auditRunning, setAuditRunning] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [jwtToken, setJwtToken] = useState<string | null>(null);

  // Verrou anti-double-bootstrap (StrictMode protection)
  const isLoadingChatsRef = useRef(false); //  Anti-boucle loadChats
  const lastLoadChatsAtRef = useRef(0);
  const didRestoreOnceRef = useRef(false);
  const didTryAutoCreateRef = useRef(false);

  // Merger les messages entrants (pour Free Chat post-envoi)
  // Stratégie: fusionner par ID, garder le message avec created_at le plus récent
  const mergeIncomingMessages = (
    prev: ChatMessage[],
    incoming: any[],
  ): ChatMessage[] => {
    // Build a map by ID for deduplication
    const byId = new Map<string | number, ChatMessage>();

    // Add previous messages first
    for (const m of prev) {
      if (m.id != null) {
        byId.set(m.id, m);
      }
    }

    // Process incoming messages, keeping the one with most recent created_at
    for (const incomingMsg of incoming) {
      const formatted: ChatMessage = {
        id: incomingMsg.id || crypto.randomUUID(),
        sender: incomingMsg.sender === "user" ? "user" : "assistant",
        text: incomingMsg.text || incomingMsg.content || "",
        created_at: incomingMsg.created_at || new Date().toISOString(),
      };

      // Skip if no ID (can't deduplicate)
      if (!formatted.id) continue;

      const existing = byId.get(formatted.id);
      if (!existing) {
        // No existing message with this ID, add it
        byId.set(formatted.id, formatted);
      } else {
        // Both have IDs - keep the one with more recent created_at
        const existingTime = parseServerDate(existing.created_at).getTime();
        const newTime = parseServerDate(formatted.created_at).getTime();

        if (newTime >= existingTime) {
          // New message is more recent or same age, use it
          byId.set(formatted.id, formatted);
        }
        // Otherwise keep the existing one
      }
    }

    // Convert back to array and sort by date
    return sortMessagesByDate(Array.from(byId.values()));
  };

  // Charger les messages d'un chat depuis l'API et les stocker en state
  const loadChatMessages = async (chatId: number) => {
    //  DEBUG LOG (temporaire)
    console.log("[loadChatMessages] ACTIVE CHAT USED:", chatId);

    try {
      const response = await axiosClient.get("/chats/get_messages", {
        params: { chat_id: chatId },
      });

      // Vérifier la structure de la réponse
      const messagesData = Array.isArray(response.data)
        ? response.data
        : response.data?.messages || [];

      //  CRITICAL FIX: Stocker les messages en state (avec extra pour InstanceSelector)
      const currentChatId = Number(chatId);
      const currentSessionId = sessionId ? Number(sessionId) : null;
      const formattedMessages: ChatMessage[] = messagesData.map((m: any) => {
        const senderValue = m.sender || m.role || "assistant";
        const createdAt = m.created_at || m.createdAt || m.timestamp;
        return {
          id: m.id || crypto.randomUUID(),
          sender: senderValue === "user" ? "user" : "assistant",
          text: m.text || m.content || "",
          created_at: createdAt || new Date().toISOString(),
          extra: m.extra || undefined, //  Préserver extra (state, available_instances, etc)
          chat_id: m.chat_id ?? currentChatId,
          session_id: m.session_id ?? currentSessionId,
        } as ChatMessage & { chat_id?: number; session_id?: number | null };
      });
      formattedMessages.sort((a, b) => {
        const aTime = Date.parse(a.created_at);
        const bTime = Date.parse(b.created_at);
        if (Number.isFinite(aTime) && Number.isFinite(bTime)) {
          return aTime - bTime;
        }
        const aId = typeof a.id === "number" ? a.id : Number(a.id);
        const bId = typeof b.id === "number" ? b.id : Number(b.id);
        if (Number.isFinite(aId) && Number.isFinite(bId)) {
          return aId - bId;
        }
        return 0;
      });
      setMessages(formattedMessages);
    } catch (err) {
      console.error(" [loadChatMessages] ERROR", { chatId, error: err });
      // Ne pas vider les messages existants en cas d'erreur
    }
  };

  //  Charge les chats
  const loadChats = async (): Promise<Chat[]> => {
    const now = Date.now();
    if (now - lastLoadChatsAtRef.current < 1000) {
      console.log(" [loadChats] throttled");
      return [];
    }
    lastLoadChatsAtRef.current = now;

    //  Protéger contre les appels simultanés
    if (isLoadingChatsRef.current) {
      console.log(" [loadChats] Déjà en cours, skip");
      return [];
    }

    isLoadingChatsRef.current = true;
    try {
      const response = await axiosClient.get("/chats/list_all_chats");
      const chatList: Chat[] = response.data
        .map((chat: any) => ({
          id: chat.chat_id,
          name: chat.name,
          session_id: chat.session_id ?? null,
          created_at: chat.created_at,
          mode: chat.mode || "dac", //  MODE depuis backend (source de vérité)
        }))
        .filter((chat: Chat) => chat.session_id !== null)
        .sort(
          (a: Chat, b: Chat) =>
            new Date(b.created_at || "").getTime() -
            new Date(a.created_at || "").getTime(),
        ); // Tri par date décroissante

      setChats(chatList);

      // WARN NE PLUS modifier selectedChatId ici (cause boucles infinies)
      // La sélection est gérée par restoreSession() ou selectChat()

      return chatList;
    } catch (err) {
      console.error(" Erreur chargement des chats utilisateur :", err);
      return [];
    } finally {
      isLoadingChatsRef.current = false; //  Relâcher le verrou
    }
  };

  //  Trouver la session associée à un chat
  const getSessionIdForChat = async (
    chatId: number,
  ): Promise<string | null> => {
    const fromState = chats.find((c) => c.id === chatId)?.session_id;
    if (fromState) return fromState.toString();

    try {
      const res = await axiosClient.get("/chats/get_metadata", {
        params: { chat_id: chatId },
      });
      const sid = res.data?.session_id ?? res.data?.sessionId;
      return sid ? sid.toString() : null;
    } catch (err) {
      console.warn(" [getSessionIdForChat] fallback metadata failed", {
        chatId,
        error: err,
      });
      return null;
    }
  };

  //  Restaure session + chats au démarrage (ou auto-crée)
  useEffect(() => {
    const restoreSession = async () => {
      //  Attendre que l'auth soit complète avant de restaurer
      if (authLoading) {
        console.log("Auth en cours, skip restoreSession");
        return;
      }

      // OK Important: si pas authentifié, ne pas restaurer/charger (évite boucles)
      if (!user) {
        console.log("User null, skip restoreSession");
        return;
      }

      // OK One-shot guard: restore ne doit tourner qu'une fois par montage
      if (didRestoreOnceRef.current) {
        console.log("restoreSession déjà exécuté, skip");
        return;
      }
      didRestoreOnceRef.current = true;

      try {
        // Priorité à l'ID de projet depuis l'URL
        let targetSessionId = null;

        if (projectIdParam && !isNaN(Number(projectIdParam))) {
          targetSessionId = projectIdParam;
        } else {
          // Fallback vers localStorage
          const localSessionId = localStorage.getItem("selectedSessionId");
          if (localSessionId && !isNaN(Number(localSessionId))) {
            targetSessionId = localSessionId;
          }
        }

        if (targetSessionId) {
          try {
            const sessionResp = await axiosClient.get(
              `/sessions/${targetSessionId}`,
            );
            setSessionId(targetSessionId);
            setChatState(sessionResp.data.state || "free_chat");

            // Sauvegarder dans localStorage
            localStorage.setItem("selectedSessionId", targetSessionId);
            localStorage.setItem("currentProjectId", targetSessionId);

            const loaded = await loadChats();

            // --- LOGIQUE DE REPRISE DU CHAT ACTIF ---
            const persistedChatId = loadActiveChatId();
            const canResumePersisted =
              persistedChatId && loaded.some((c) => c.id === persistedChatId);
            const chatIdToSelect =
              (canResumePersisted ? persistedChatId : null) ??
              loaded[0]?.id ??
              null;
            if (chatIdToSelect) {
              setSelectedChatId(chatIdToSelect);
              saveActiveChatId(chatIdToSelect);

              //  FIX CRITICAL: Restaurer le mode DEPUIS LE BACKEND (pas localStorage)
              const selectedChat = loaded.find((c) => c.id === chatIdToSelect);
              if (selectedChat?.mode) {
                const restoredMode = selectedChat.mode as "free" | "dac";
                setChatMode(restoredMode);

                // Toujours charger les messages du chat sélectionné
                await loadChatMessages(chatIdToSelect);
              }
            }
            // ---
          } catch (err) {
            console.warn(" Session locale invalide, suppression.");
            localStorage.removeItem("selectedSessionId");
            setSessionId(null);
            setChats([]);
          }
        } else {
          // Pas de session existante -> auto-créer session + chat
          try {
            if (didTryAutoCreateRef.current) {
              console.warn("Auto-create déjà tenté, skip retry");
              return;
            }
            didTryAutoCreateRef.current = true;

            const chatRes = await startChat(undefined, "Chat de découverte");

            // Mettre à jour les states avec les IDs retournés
            const newSessionId = chatRes.session_id.toString();
            localStorage.setItem("selectedSessionId", newSessionId);
            setSessionId(newSessionId);
            setChatState(chatRes.state || "free_chat");

            // Charger les chats et sélectionner le nouveau
            await loadChats();
            setSelectedChatId(chatRes.chat_id);
            localStorage.setItem("activeChatId", chatRes.chat_id.toString()); //  Persister
            // Toujours charger les messages du chat sélectionné
            await loadChatMessages(chatRes.chat_id);
          } catch (err) {
            console.error("Erreur auto-création session/chat:", err);
            // OK IMPORTANT: ne pas relancer loadChats en boucle ici.
            // On laisse l'utilisateur cliquer sur "Nouveau chat" ou on affiche un message.
          }
        }
      } finally {
        // no-op
      }
    };

    restoreSession();
  }, [projectIdParam, authLoading, user?.id]); // OK Utiliser user?.id au lieu de user (objet ref change)

  //  Garantit une session (crée si absence) — STABLE pour persistence
  const ensureSession = async (): Promise<string> => {
    if (sessionId) {
      return sessionId;
    }

    try {
      //  CRITICAL: Use GET /sessions/or-create (NOT POST /sessions/create)
      // This endpoint returns EXISTING session if present, creates only if missing
      // This ensures sessionId is STABLE across refresh
      const res = await axiosClient.get("/sessions/or-create");
      const newId = res.data.id.toString();
      localStorage.setItem("selectedSessionId", newId);
      setSessionId(newId);
      setChatState(res.data.state || "free_chat");
      return newId;
    } catch (err) {
      console.error(" Impossible de garantir une session :", err);
      throw err;
    }
  };

  //  Garantit la session du projet (priorité à l'URL)
  const ensureProjectSession = async (): Promise<string> => {
    if (projectIdParam && !isNaN(Number(projectIdParam))) {
      localStorage.setItem("selectedSessionId", projectIdParam);
      setSessionId(projectIdParam);
      return projectIdParam;
    }
    return await ensureSession();
  };

  //  Crée un nouveau chat
  const createNewChat = async () => {
    try {
      const sid = await ensureProjectSession(); // devrait être une string
      const res = await startChat(Number(sid), "Nouveau Chat");

      //  Sélection immédiate et persistence
      setSelectedChatId(res.chat_id);
      setSessionId(sid);
      localStorage.setItem("selectedSessionId", sid);
      localStorage.setItem("activeChatId", String(res.chat_id));
      // Ne pas effacer l'historique, on recharge juste après

      // Toujours recharger depuis le backend après création
      await loadChatMessages(res.chat_id);

      // Recharger la liste en arrière-plan (pas bloquant)
      loadChats();
    } catch (err) {
      console.error(" Création chat échouée :", err);
    }
  };

  const renameChat = (id: number, newName: string) => {
    setChats((prev) =>
      prev.map((chat) => (chat.id === id ? { ...chat, name: newName } : chat)),
    );
  };

  const deleteChat = async (id: number) => {
    setIsRecovering(true);
    try {
      const deletedWasSelected = id === selectedChatId;

      // Supprimer du backend et récupérer le prochain chat directement
      const res = await axiosClient.delete(`/chats/${id}`);
      const { next_chat: nextChatPayload, remaining_chats_count: remaining } =
        res.data || {};

      // Normaliser les champs backend (chat_id vs id)
      const nextChatId: number | null =
        nextChatPayload?.chat_id ?? nextChatPayload?.id ?? null;
      const nextSessionId: string | null = nextChatPayload?.session_id
        ? nextChatPayload.session_id.toString()
        : null;
      const remainingCount = Number(remaining ?? -1);

      //  Cas critique: plus aucun chat -> sélectionner immédiatement le nouveau
      if (remainingCount === 0) {
        if (!nextChatId) {
          console.warn(
            " [deleteChat] remaining=0 but no next chat id returned",
          );
        } else {
          const sid = nextSessionId ?? (await ensureProjectSession());
          setSessionId(sid);
          localStorage.setItem("selectedSessionId", sid);

          setSelectedChatId(nextChatId);
          localStorage.setItem("activeChatId", String(nextChatId));
          // Ne pas effacer l'historique, on recharge juste après

          // S'assurer que le chat existe en liste même si setChats tarde
          setChats((prev) => {
            const filtered = prev.filter((c) => c.id !== id);
            const mapped: Chat = {
              id: nextChatId,
              name: nextChatPayload?.name || "Nouveau chat",
              session_id: String(sid),
              created_at:
                nextChatPayload?.created_at || new Date().toISOString(),
            };
            const exists = filtered.some((c) => c.id === mapped.id);
            return exists ? filtered : [mapped, ...filtered];
          });

          await loadChatMessages(nextChatId);
          return; // Ne pas passer aux autres branches
        }
      }

      if (nextSessionId) {
        setSessionId(nextSessionId);
        localStorage.setItem("selectedSessionId", nextSessionId);
      } else {
        const ensured = await ensureProjectSession();
      }

      setChats((prev) => {
        const filtered = prev.filter((chat) => chat.id !== id);

        // Injecter/mettre à jour le next_chat retourné par le backend
        if (nextChatId && nextChatPayload) {
          const mapped: Chat = {
            id: nextChatId,
            name: nextChatPayload.name || "Nouveau chat",
            session_id: nextChatPayload.session_id,
            created_at: nextChatPayload.created_at || new Date().toISOString(),
          };

          const exists = filtered.some((c) => c.id === mapped.id);
          return exists
            ? filtered.map((c) => (c.id === mapped.id ? mapped : c))
            : [mapped, ...filtered];
        }

        return filtered;
      });

      // Si le chat supprimé était sélectionné (ou aucune sélection), se placer sur next_chat
      if ((deletedWasSelected || !selectedChatId) && nextChatId) {
        setSelectedChatId(nextChatId);
        localStorage.setItem("activeChatId", nextChatId.toString());
        await loadChatMessages(nextChatId);
        return;
      }

      // Fallback de sécurité si le backend ne renvoie pas de next_chat (ne devrait pas arriver)
      if (!nextChatPayload) {
        console.warn(
          " [deleteChat] No next_chat returned by backend, falling back to refresh",
        );
        await loadChats();
      }
    } catch (err) {
      console.error(" [deleteChat] ERROR:", err);
    } finally {
      setIsRecovering(false);
    }
  };

  //  Force le rechargement des chats depuis le serveur
  const refreshChats = async (): Promise<Chat[]> => {
    return await loadChats();
  };

  const sendMessage = async (msg: string): Promise<any> => {
    setIsTyping(true);

    //  SOURCE DE VÉRITÉ UNIQUE: selectedChatId SEULEMENT
    // ERR INTERDIT: localStorage fallback, chats[0] fallback, etc.
    let chatId: number | null = selectedChatId ? Number(selectedChatId) : null;

    //  DEBUG LOG (temporaire)
    console.log("[sendMessage] ACTIVE CHAT USED:", {
      activeChatId: chatId,
      selectedChatId,
      localStorage: localStorage.getItem("activeChatId"),
    });

    try {
      // Validation stricte: chatId DOIT être défini
      if (!chatId || !Number.isFinite(chatId) || chatId <= 0) {
        console.error("[sendMessage] Invalid or missing chatId:", {
          chatId,
          selectedChatId,
          availableChats: chats.map((c) => c.id),
        });
        throw new Error(
          "Aucun chat sélectionné. Sélectionne un chat dans la sidebar.",
        );
      }

      const sid =
        (chatId ? await getSessionIdForChat(chatId) : null) ||
        (await ensureProjectSession());

      if (!sid || !Number.isFinite(Number(sid))) {
        console.error("Invalid sessionId:", { sid });
        throw new Error("Invalid session ID");
      }

      if (!chatId) {
        const res = await startChat(Number(sid), "Chat initial");
        const newChat: Chat = {
          id: res.chat_id,
          name: "Chat initial",
          session_id: String(res.session_id || sid),
          created_at: new Date().toISOString(),
        };
        setChats((prev) => [newChat, ...prev]);
        setSelectedChatId(newChat.id);
        chatId = newChat.id;
      }

      // Auto-rename si c'est le premier message d'un "Nouveau chat" ou "Chat de découverte"
      // CRITICAL: Chercher dans le chat qu'on vient de créer/sélectionner, pas dans l'ancien state
      const allChats = chats.length > 0 ? chats : []; // Fallback si state pas à jour
      const currentChat = allChats.find((c) => c.id === chatId);

      // Déterminer si c'est un titre par défaut (sans dépendre du state)
      const isDefaultTitle =
        currentChat &&
        (currentChat.name === "Nouveau chat" ||
          currentChat.name === "Chat de découverte" ||
          currentChat.name === "Chat initial");

      // Déterminer si c'est le premier message (avant que le message soit ajouté au state)
      const isFirstMessage = messages.length === 0;

      if (isDefaultTitle && isFirstMessage) {
        try {
          // Prendre les premiers mots du message (max 40 caractères)
          const autoName = msg.length > 40 ? msg.substring(0, 37) + "..." : msg;
          await renameChat(chatId, autoName);

          // Mettre à jour localement (optimistic)
          setChats((prev) =>
            prev.map((c) => (c.id === chatId ? { ...c, name: autoName } : c)),
          );
        } catch (renameErr) {
          console.warn(" Auto-rename échoué, pas bloquant:", renameErr);
        }
      }

      //  ROUTAGE: Free Chat vs DAC selon currentChat.mode
      const mode = currentChat?.mode || "dac"; // fallback dac si absent
      if (mode === "free") {
        // --- FREE CHAT ---

        // 1. Ajouter message utilisateur (optimistic)
        const optimisticUserId = "user-" + Date.now();
        const userMsg: ChatMessage = {
          id: optimisticUserId,
          sender: "user",
          text: msg,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, userMsg]);

        // 2. Ajouter message "réfléchit"
        const thinkingId = "thinking-" + Date.now();
        const thinkingMsg: ChatMessage = {
          id: thinkingId,
          sender: "assistant",
          text: "L'assistant réfléchit...",
          created_at: new Date().toISOString(),
          loading: true,
        };
        setMessages((prev) => [...prev, thinkingMsg]);

        let freeChattRes: any = null;
        try {
          // 3. Appel backend (endpoint unifié)
          const res = await axiosClient.post("/chat_creation/chat_message", {
            session_id: Number(sid),
            chat_id: Number(chatId),
            sender: "user",
            text: msg,
          });
          freeChattRes = res.data; // Capture for later return

          // 4. Merger immédiatement avec fonction utilitaire
          const incomingMessages = res.data?.messages || [];
          if (incomingMessages.length > 0) {
            setMessages((prev) => {
              const filtered = prev.filter(
                (m) => m.id !== thinkingId && m.id !== optimisticUserId,
              );
              return mergeIncomingMessages(filtered, incomingMessages);
            });
          } else {
            // Fallback: just remove thinking
            setMessages((prev) => prev.filter((m) => m.id !== thinkingId));
          }
        } catch (err: any) {
          console.error("[sendMessage] Free Chat Error:", err);

          // Extraire le message d'erreur détaillé
          const errorDetail =
            err?.response?.data?.detail ||
            err?.response?.data?.message ||
            err?.message ||
            "Erreur inconnue";

          // Remplacer le message "réfléchit" par l'erreur
          setMessages((prev) =>
            prev.map((m) =>
              m.id === thinkingId
                ? {
                    ...m,
                    text: `ERR Erreur: ${errorDetail}`,
                    loading: false,
                  }
                : m,
            ),
          );
          throw err;
        }
        return freeChattRes; // Return response for free chat mode
      } else {
        // --- DAC MODE ---

        let sessionToUse = Number(sid);
        if (!Number.isFinite(sessionToUse) && chatId) {
          // Si sessionId null, on fait un resumeChat
          const resume = await axiosClient.get(`/chats/${chatId}/resume`);
          sessionToUse = Number(resume.data.session_id);
          setSessionId(String(sessionToUse));
          setChatState(resume.data.session_state);
        }
        const normalizedInput = msg.trim().toLowerCase();
        if (
          chatMode === "dac" &&
          chatState === "awaiting_audit_confirmation" &&
          ["ok", "lancer"].includes(normalizedInput)
        ) {
          console.log("[DAC] Audit started (UI)");
          setAuditRunning(true);
        }

        //  OPTIMISTIC UI: Ajouter le message utilisateur immédiatement
        const userMsgId = "user-" + Date.now();
        const userMsg: ChatMessage = {
          id: userMsgId,
          sender: "user",
          text: msg,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, userMsg]);

        const payload = {
          session_id: sessionToUse,
          chat_id: Number(chatId),
          sender: "user",
          text: msg,
        };

        try {
          // ÉTAPE 1 & 2: Capturer et traiter la réponse correctement
          const res = await axiosClient.post(
            "/chat_creation/chat_message",
            payload,
          );

          //  NORMALISATION ROBUSTE: tolérer les 2 formats de réponse backend
          const normalizedState = res.data?.session_state ?? res.data?.state;
          const normalizedAvailableInstances =
            res.data?.available_instances ??
            res.data?.extra?.available_instances ??
            [];
          const normalizedExtra = res.data?.extra || {};
          const normalizedExecutionId =
            res.data?.execution_id_db ||
            normalizedExtra?.execution_id_db ||
            res.data?.execution_id ||
            normalizedExtra?.execution_id;

          //  Si on démarre un audit, stocker l'execution_id et le JWT token
          if (normalizedExecutionId) {
            console.log("[DAC] Execution ID reçu:", normalizedExecutionId);
            setExecutionId(normalizedExecutionId);

            // Récupérer le JWT token depuis localStorage
            const token = localStorage.getItem("access_token");
            if (token) {
              setJwtToken(token);
              console.log("[DAC] JWT token stocké pour SSE");
            }
          }

          //  OPTIMISTIC UI: Ajouter le message bot immédiatement
          //  Fallback robuste: si pas de message, utiliser le texte de statut ou un JSON de debug
          const assistantText = res.data?.message
            ? res.data.message
            : normalizedState
              ? `État changé: ${normalizedState}`
              : JSON.stringify(res.data, null, 2); // debug: afficher toute la réponse

          if (assistantText && assistantText.trim()) {
            const botMsg: ChatMessage = {
              id: "bot-" + Date.now(),
              sender: "bot",
              text: assistantText,
              created_at: new Date().toISOString(),
              extra: {
                ...normalizedExtra,
                state: normalizedState,
                available_instances: normalizedAvailableInstances,
              },
            };
            setMessages((prev) => [...prev, botMsg]);
          }

          //  UPDATE STATE GLOBAL: mettre à jour la machine d'état immédiatement
          if (normalizedState) {
            setChatState(normalizedState);
          }
          if (
            Array.isArray(normalizedAvailableInstances) &&
            normalizedAvailableInstances.length > 0
          ) {
            setAvailableInstances(normalizedAvailableInstances);
          }

          //  UI STATE: Déclencher les sélecteurs conditionnels SEULEMENT si état approprié
          const instanceSelectionStates = [
            "awaiting_audit_instance_selection",
            "awaiting_monitoring_instance_selection",
            "awaiting_instance_selection",
          ];

          if (
            res.data?.session_mode === "dac" &&
            instanceSelectionStates.includes(normalizedState)
          ) {
            console.log(
              "[DAC] UI State: instance selection (état=%s)",
              normalizedState,
            );

            setUiState({
              type: "instance_selection",
              mode: normalizedState.includes("audit")
                ? "audit"
                : normalizedState.includes("monitoring")
                  ? "monitoring"
                  : "configure",
              chatId: res.data.chat_id,
            });
          } else {
            //  Cleanup: masquer le sélecteur si on n'est plus dans un état approprié
            if (
              normalizedState &&
              !instanceSelectionStates.includes(normalizedState)
            ) {
              setUiState(null);
            }
          }

          //  AUDIT FEEDBACK: Arrêter la barre d'audit si terminé
          if (
            res.data?.message?.includes("Audit terminé") ||
            normalizedState === "audit_completed"
          ) {
            console.log("[DAC] Audit finished");
            setAuditRunning(false);
            setUiState(null);
          }

          //  Fallback: merger messages (free chat)
          if (res.data?.messages && Array.isArray(res.data.messages)) {
            setMessages((prev) => {
              const filtered = prev.filter(
                (m) => !m.id?.startsWith("thinking-"),
              );
              return mergeIncomingMessages(filtered, res.data.messages);
            });
          } else if (!res.data?.message) {
            // Aucun message ni messages array: reload par sécurité
            setReloadFlag((prev) => !prev);
          }
          return res.data; // Return response data for caller
        } catch (err: any) {
          console.error("[sendMessage] DAC Mode Error:", err);

          // Extraire le message d'erreur détaillé
          const errorDetail =
            err?.response?.data?.detail ||
            err?.response?.data?.message ||
            err?.message ||
            "Erreur inconnue";

          // Afficher l'erreur dans le chat
          const errorMsg: ChatMessage = {
            id: "error-" + Date.now(),
            sender: "bot",
            text: `ERR Erreur serveur: ${errorDetail}`,
            created_at: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, errorMsg]);

          throw err;
        }
      }
    } catch (err: any) {
      console.error(" Envoi message échoué :", {
        error: err,
        response: err.response,
        status: err.response?.status,
        responseURL: err.response?.request?.responseURL,
        data: err.response?.data,
      });
      throw err; // Re-throw so caller knows it failed
    } finally {
      // OK Refresh direct après action utilisateur (sans throttle)
      try {
        if (chatId && Number.isFinite(Number(chatId))) {
          console.log("[sendMessage] Refresh messages after send", chatId);
          await loadChatMessages(Number(chatId));
        }
      } catch (refreshErr) {
        console.warn("[sendMessage] Refresh messages failed", refreshErr);
      } finally {
        setIsTyping(false);
      }
    }
  };

  const selectChat = async (id: number | null) => {
    //  DEBUG LOG (temporaire)
    console.log("[selectChat] CHAT SELECTION:", {
      requestedId: id,
      currentSelectedId: selectedChatId,
    });

    //  FIX: Normaliser l'ID en number
    if (id !== null) {
      id = Number(id);
      if (!Number.isFinite(id) || id <= 0) {
        console.error(" Invalid chat ID:", { id });
        return;
      }
    }

    if (id === null) {
      setSelectedChatId(null);
      setSessionId(null);
      // Ne pas effacer l'historique lors d'un simple reset de sélection
      localStorage.removeItem("selectedSessionId");
      localStorage.removeItem("activeChatId");
      return;
    }

    //  Si les chats ne sont pas encore chargés, les charger d'abord
    let currentChats = chats;
    if (!currentChats || currentChats.length === 0) {
      console.warn(
        " [selectChat] Chats array vide, chargement depuis le serveur...",
      );
      currentChats = await loadChats();
    }

    const chat = currentChats.find((c) => c.id === id);
    if (!chat) {
      console.warn(
        " Chat introuvable avec l'ID :",
        id,
        "parmi",
        currentChats.length,
        "chats disponibles",
      );
      return;
    }

    // Mettre à jour la session immédiatement
    setSessionId(chat.session_id);
    localStorage.setItem("selectedSessionId", chat.session_id);

    // Mettre à jour la sélection
    setSelectedChatId(id);
    localStorage.setItem("activeChatId", id.toString()); //  Persister le chat sélectionné
    // Ne pas effacer l'historique, on recharge juste après

    //  FIX CRITICAL: Restaurer le mode DEPUIS LE BACKEND (pas localStorage)
    const modeFromBackend = chat.mode || "dac";
    setChatMode(modeFromBackend as "free" | "dac");

    // Recharger les messages depuis le backend dans tous les modes
    await loadChatMessages(id);

    const chatSessionId = chat.session_id;
    if (!chatSessionId || chatSessionId === "undefined") {
      console.error(" session_id manquant ou invalide pour le chat :", chat);
      return;
    }

    try {
      const sessionResp = await axiosClient.get(`/sessions/${chatSessionId}`);
      setSessionId(chatSessionId);
      setChatState(sessionResp.data.state || "free_chat"); //  Mode découverte par défaut
      localStorage.setItem("selectedSessionId", chatSessionId);
      setSelectedChatId(id);
    } catch (err) {
      console.error(" Échec chargement session associée au chat :", err);
    }
  };

  return {
    chats,
    selectedChatId,
    sessionId,
    chatState,
    setChatState,
    isTyping,
    isRecovering,
    reloadFlag,
    messages,
    setMessages,
    selectChat,
    createNewChat,
    renameChat,
    deleteChat,
    sendMessage,
    loadChats,
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
    setJwtToken,
  };
}

// --- Helpers de persistance (clé unifiée) ---
const LS_ACTIVE_CHAT = "activeChatId";
function saveActiveChatId(id: number) {
  localStorage.setItem(LS_ACTIVE_CHAT, String(id));
}
function loadActiveChatId(): number | null {
  const v = localStorage.getItem(LS_ACTIVE_CHAT);
  return v ? Number(v) : null;
}
// ---
