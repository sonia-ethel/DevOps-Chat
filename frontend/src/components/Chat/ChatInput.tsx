// © 2024–2026 TOURE Arnaud Patrick
// Licensed under the MIT License

import { TextField, IconButton, Paper, alpha, Fade } from "@mui/material";
import { Send } from "@mui/icons-material";
import { useState, useEffect, useRef, type KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (msg: string) => void;
  chatId?: number | null;
  disabled?: boolean;
}

export default function ChatInput({
  onSend,
  chatId,
  disabled = false,
}: ChatInputProps) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement | null>(null); //  textarea pour multiline

  useEffect(() => {
    //  Focus dès qu’un chat est sélectionné
    if (chatId !== null && inputRef.current) {
      inputRef.current.focus();
    }
  }, [chatId]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();

    if (trimmed && !disabled) {
      //  Envoi possible dès qu'on a une session (chatId peut être null, sera créé auto)
      onSend(trimmed);
      setText(""); //  Vider après envoi
    }
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (
      (e.key === "Enter" && !e.shiftKey) ||
      (e.key === "Enter" && e.ctrlKey)
    ) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  };

  const isInputDisabled = disabled; //  Pas de vérification chatId, actif en mode découverte

  return (
    <Paper
      component="form"
      onSubmit={handleSubmit}
      elevation={0}
      sx={{
        p: 2,
        bgcolor: alpha("#1e293b", 0.8),
        backdropFilter: "blur(20px)",
        borderTop: "1px solid",
        borderColor: "divider",
        display: "flex",
        gap: 1.5,
        alignItems: "flex-end",
      }}
    >
      <TextField
        fullWidth
        multiline
        inputRef={inputRef}
        minRows={1}
        maxRows={4}
        variant="outlined"
        placeholder={
          isInputDisabled
            ? "Connexion en cours..."
            : "Posez vos questions sur l'infrastructure, les déploiements ou les tâches DevOps..."
        }
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isInputDisabled}
        aria-label="Message input"
        sx={{
          "& .MuiOutlinedInput-root": {
            bgcolor: alpha("#334155", 0.3),
            borderRadius: 3,
            fontSize: "0.875rem",
            "& fieldset": {
              borderColor: alpha("#475569", 0.5),
            },
            "&:hover fieldset": {
              borderColor: "primary.main",
            },
            "&.Mui-focused fieldset": {
              borderColor: "primary.main",
              borderWidth: 2,
            },
          },
          "& .MuiInputBase-input": {
            color: "text.primary",
          },
          "& .MuiInputBase-input::placeholder": {
            color: "text.secondary",
            opacity: 1,
          },
        }}
      />
      <Fade in={!!text.trim() && !isInputDisabled}>
        <IconButton
          type="submit"
          disabled={!text.trim() || isInputDisabled}
          sx={{
            bgcolor: "primary.main",
            color: "white",
            width: 44,
            height: 44,
            "&:hover": {
              bgcolor: "primary.dark",
              transform: "scale(1.05)",
            },
            "&:disabled": {
              bgcolor: alpha("#6366f1", 0.3),
              color: alpha("#ffffff", 0.5),
            },
            transition: "all 0.2s ease-in-out",
          }}
        >
          <Send />
        </IconButton>
      </Fade>
    </Paper>
  );
}
