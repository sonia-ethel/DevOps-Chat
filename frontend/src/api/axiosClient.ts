// © 2024–2026 TOURE Arnaud Patrick
// Licensed under the MIT License

// src/api/axiosClient.ts
import axios, { AxiosError } from "axios";

const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
  withCredentials: true,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// Routes d'auth: ne JAMAIS envoyer Authorization
const AUTH_ROUTES = [
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
  "/auth/logout",
];

// Helpers sûrs pour gérer Authorization sans casser AxiosHeaders
function setAuthHeader(config: any, token: string) {
  if (!config.headers) config.headers = {};
  if (typeof config.headers.set === "function") {
    // AxiosHeaders
    config.headers.set("Authorization", `Bearer ${token}`);
  } else {
    // objet simple
    config.headers.Authorization = `Bearer ${token}`;
  }
}

function removeAuthHeader(config: any) {
  if (!config.headers) return;
  if (typeof config.headers.delete === "function") {
    // AxiosHeaders
    config.headers.delete("Authorization");
  } else if ("Authorization" in config.headers) {
    delete (config.headers as any).Authorization;
  }
}

// Intercepteur requête
axiosClient.interceptors.request.use((config) => {
  // Détermine le path proprement
  let path = config.url || "";
  try {
    const u = new URL(
      config.url ?? "",
      config.baseURL || window.location.origin,
    );
    path = u.pathname;
  } catch {
    /* ignore */
  }

  const isAuthRoute = AUTH_ROUTES.some((r) => path.startsWith(r));
  if (isAuthRoute) {
    removeAuthHeader(config);
  } else {
    const token = localStorage.getItem("access_token");
    if (token) setAuthHeader(config, token);
    else removeAuthHeader(config);
  }

  return config;
});

// Intercepteur réponse
axiosClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.code === "ECONNABORTED") {
      console.warn(" La requête a expiré.");
    }

    const reqUrl = error.config?.url || "";
    let path = reqUrl;
    try {
      const u = new URL(
        reqUrl,
        error.config?.baseURL || window.location.origin,
      );
      path = u.pathname;
    } catch {
      /* ignore */
    }

    // Ne PAS rediriger pour les erreurs d'auth (on veut afficher "email/mot de passe incorrect")
    const AUTH_ROUTES = [
      "/auth/login",
      "/auth/register",
      "/auth/refresh",
      "/auth/logout",
    ];
    const isAuthRoute = AUTH_ROUTES.some((r) => path.startsWith(r));

    if (error.response?.status === 401 && !isAuthRoute) {
      localStorage.removeItem("access_token");
      const next = encodeURIComponent(location.pathname + location.search);
      window.location.replace(`/?next=${next}`);
      return;
    }

    return Promise.reject(error);
  },
);

/* ============================================================================
    RESSOURCES (Instances)
============================================================================ */

export const fetchInstances = async (sessionId: number) => {
  const res = await axiosClient.get("/resources/list_resources", {
    params: { session_id: sessionId },
  });
  return res.data;
};

export const deleteInstance = async (sessionId: number, instanceId: string) => {
  const res = await axiosClient.post("/resources/delete_resource", null, {
    params: { session_id: sessionId, instance_id: instanceId },
  });
  return res.data;
};

/* ============================================================================
    CHAT MESSAGES
============================================================================ */

export const getMessages = async (chatId: number) => {
  const res = await axiosClient.get("/chats/get_messages", {
    params: { chat_id: chatId },
  });
  return res.data;
};

/* ============================================================================
    CONFIGURATION Auto
============================================================================ */

export const autoConfigure = async (
  sessionId: number,
  instanceIds: string[],
  requestText: string,
) => {
  const res = await axiosClient.post("/configure/auto_configure", {
    session_id: sessionId,
    instance_ids: instanceIds,
    request_text: requestText,
  });
  return res.data;
};

/* ============================================================================
    CHAT – Création & Gestion
============================================================================ */

// Créer un nouveau chat (crée aussi une session si session_id non fourni)
export const startChat = async (sessionId?: number, name = "Nouveau Chat") => {
  const res = await axiosClient.post("/chats/start_chat", {
    session_id: sessionId || undefined, // Si fourni, utilise session existante
    request_text: "Session de découverte",
    description: "Session créée automatiquement",
    provider: "aws",
    chat_name: name,
  });
  return res.data;
};

// Lister les chats d’une session
export const listChats = async (sessionId: number) => {
  const res = await axiosClient.get("/chats/list_chats", {
    params: { session_id: sessionId },
  });
  return res.data;
};

// Envoyer un message au chatbot (phase création)
export const sendCreationMessage = async (
  sessionId: number | null,
  message: string,
) => {
  const res = await axiosClient.post(
    "/chat_creation/chat_message",
    {},
    { params: sessionId ? { session_id: sessionId, message } : { message } },
  );
  return res.data;
};

// Envoyer un message au chatbot (phase gestion/config)
export const sendManagementMessage = async (
  sessionId: number,
  message: string,
) => {
  const res = await axiosClient.post(
    "/chat_creation/chat_message",
    {},
    { params: { session_id: sessionId, message } },
  );
  return res.data;
};

// Interface unifiée
export const sendChatMessage = async (
  _mode: "creation" | "management",
  sessionId: number,
  chatId: number,
  message: string,
) => {
  const payload = {
    session_id: sessionId,
    chat_id: chatId,
    sender: "user",
    text: message,
  };
  const res = await axiosClient.post("/chat_creation/chat_message", payload);
  return res.data;
};

// --- API helpers pour le mode chat ---
// IMPORTANT: le backend n'a pas /chats/{id}/mode ni /chats/{id}/dac/start
// On utilise /chats/switch_to_dac et on bascule "free" localement via l'UI.

export const setChatMode = async (chatId: number, mode: "free" | "dac") => {
  // Mode "free" : pas de route backend dédiée dans ton code actuel
  // => on ne fait rien côté API, on laisse le front gérer l'affichage.
  if (mode === "free") {
    return { success: true, mode: "free" };
  }

  // Mode "dac" : on passe par switch_to_dac (nécessite session_id, pas chat_id)
  // Donc cette fonction n'est pas le bon endroit pour le faire.
  // On garde une erreur explicite pour éviter les faux appels.
  throw new Error(
    "setChatMode(mode='dac') n'est pas supporté. Utilise startDAC(sessionId).",
  );
};

export const startDAC = async (chatId: number, sessionId: number) => {
  // chatId non utilisé côté backend ici, mais on le garde pour compatibilité signature
  const res = await axiosClient.post(`/chats/switch_to_dac`, {
    session_id: sessionId,
  });
  return res.data;
};
// ---

export default axiosClient;

/* ============================================================================
    Chats: rename / delete
============================================================================ */

export const renameChat = async (chatId: number, newName: string) => {
  const res = await axiosClient.post(`/chats/rename_chat`, {
    chat_id: chatId,
    new_name: newName,
  });
  return res.data;
};

export const deleteChat = async (chatId: number) => {
  const res = await axiosClient.delete(`/chats/${chatId}`);
  return res.data;
};

/* ============================================================================
    AWS Credentials Management
============================================================================ */

export const saveAWSCredentials = async (credentials: {
  accessKeyId: string;
  secretAccessKey: string;
  region: string;
}) => {
  const res = await axiosClient.post("/user/aws-credentials", credentials);
  return res.data;
};

export const getAWSCredentials = async () => {
  const res = await axiosClient.get("/user/aws-credentials");
  return res.data;
};

export const deleteAWSCredentials = async () => {
  const res = await axiosClient.delete("/user/aws-credentials");
  return res.data;
};
