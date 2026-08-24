import { createContext, useContext, useState, useEffect } from "react";
import type { ReactNode } from "react";

type ChatMode = "free" | "dac";

interface ChatModeContextType {
  chatMode: ChatMode;
  setChatMode: (mode: ChatMode) => void;
  toggleMode: () => void;
}

const ChatModeContext = createContext<ChatModeContextType | undefined>(
  undefined,
);

export function ChatModeProvider({ children }: { children: ReactNode }) {
  // FIX CRITICAL: NE PAS restaurer depuis localStorage
  // Le mode DOIT venir du backend (via useChatManager -> setChatMode)
  // Valeur initiale = "free" (sera écrasée dès que le chat/session charge)
  const [chatMode, setChatModeState] = useState<ChatMode>("free");

  const setChatMode = (mode: ChatMode) => {
    setChatModeState(mode);
    // On garde la persistence localStorage pour éviter flash UI,
    // mais elle ne doit JAMAIS être la source de vérité au reload
    localStorage.setItem("dac_chat_mode", mode);
    console.log(` Mode chat changé: ${mode}`);
  };

  const toggleMode = () => {
    setChatMode(chatMode === "free" ? "dac" : "free");
  };

  return (
    <ChatModeContext.Provider value={{ chatMode, setChatMode, toggleMode }}>
      {children}
    </ChatModeContext.Provider>
  );
}

export function useChatMode() {
  const context = useContext(ChatModeContext);
  if (!context) {
    throw new Error("useChatMode must be used within ChatModeProvider");
  }
  return context;
}
