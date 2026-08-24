import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemButton,
  IconButton,
  Tooltip,
  TextField,
  Button,
  Avatar,
  Fade,
  alpha,
  CircularProgress,
} from "@mui/material";
import {
  Delete,
  Edit,
  Add,
  Logout,
  Chat,
  Code,
  Settings,
  AccessTime,
} from "@mui/icons-material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { renameChat as renameChatAPI } from "../../api/axiosClient";
import ConfirmDeleteModal from "../Common/ConfirmDeleteModal";
import { useToast } from "../../contexts/ToastContext";
import { formatRelativeTime, formatFullDateTime } from "../../utils/dateUtils";

interface ChatSummary {
  id: number;
  name: string;
  created_at?: string;
}

interface ChatSidebarProps {
  chats: ChatSummary[];
  selectedChatId: number | null;
  onSelectChat: (id: number | null) => void | Promise<void>;
  onDeleteChat: (id: number) => void | Promise<void>;
  onRenameChat: (id: number, newName: string) => void;
  onCreateNewChat: () => void;
  onRefreshChats?: () => Promise<any>; // Can return any (Chat[] or void)
}

export default function ChatSidebar({
  chats,
  selectedChatId,
  onSelectChat,
  onDeleteChat,
  onRenameChat,
  onCreateNewChat,
  onRefreshChats,
}: ChatSidebarProps) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [chatToDelete, setChatToDelete] = useState<ChatSummary | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const navigate = useNavigate();
  const { showSuccess, showError } = useToast();

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("selectedSessionId");
    navigate("/");
    window.location.reload();
  };

  const handleRename = async (id: number, newName: string) => {
    try {
      await renameChatAPI(id, newName);
      onRenameChat(id, newName);

      // Refresh automatique de la liste
      if (onRefreshChats) {
        await onRefreshChats();
      }

      showSuccess(`Chat renommé en "${newName}"`);
    } catch (err) {
      console.error(" Échec du renommage :", err);
      showError("Impossible de renommer le chat");
    } finally {
      setEditingId(null);
    }
  };

  const openDeleteModal = (chat: ChatSummary) => {
    setChatToDelete(chat);
    setDeleteModalOpen(true);
  };

  const closeDeleteModal = () => {
    setDeleteModalOpen(false);
    setChatToDelete(null);
  };

  const handleDeleteConfirm = async () => {
    if (!chatToDelete) return;

    setIsDeleting(true);
    try {
      //  Laisser useChatManager.deleteChat gérer le delete + next_chat
      await onDeleteChat(chatToDelete.id);

      // Refresh automatique de la liste
      if (onRefreshChats) {
        await onRefreshChats();
      }

      showSuccess(`Chat "${chatToDelete.name}" supprimé`);
      closeDeleteModal();
    } catch (err) {
      console.error(" Échec de la suppression :", err);
      showError("Impossible de supprimer le chat");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <Box
      sx={{
        width: { xs: "100%", md: "320px" },
        height: { xs: "auto", md: "100vh" },
        minHeight: { xs: "60px", md: "100vh" },
        background: "linear-gradient(180deg, #1e293b 0%, #0f172a 100%)",
        color: "text.primary",
        display: "flex",
        flexDirection: "column",
        borderRight: { xs: "none", md: "1px solid" },
        borderBottom: { xs: "1px solid", md: "none" },
        borderColor: "divider",
        backdropFilter: "blur(20px)",
        zIndex: { xs: 1000, md: "auto" },
      }}
    >
      {/* Header with branding */}
      <Box
        sx={{
          px: 3,
          py: 3,
          display: "flex",
          alignItems: "center",
          gap: 2,
          borderBottom: "1px solid",
          borderColor: alpha("#475569", 0.3),
          background: alpha("#6366f1", 0.05),
        }}
      >
        <Avatar
          sx={{
            bgcolor: "primary.main",
            width: 36,
            height: 36,
            background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
          }}
        >
          <Code />
        </Avatar>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6" fontWeight={600} color="text.primary">
            DevOps Chat
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Infrastructure Assistant
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Tooltip title="Paramètres">
            <IconButton
              onClick={() => navigate("/profile")}
              sx={{
                color: "text.secondary",
                bgcolor: alpha("#475569", 0.1),
                "&:hover": {
                  color: "primary.main",
                  bgcolor: alpha("#6366f1", 0.1),
                  transform: "scale(1.05)",
                },
                transition: "all 0.2s ease-in-out",
              }}
            >
              <Settings />
            </IconButton>
          </Tooltip>
          <Tooltip title="Nouveau chat">
            <IconButton
              onClick={onCreateNewChat}
              sx={{
                color: "primary.main",
                bgcolor: alpha("#6366f1", 0.1),
                "&:hover": {
                  bgcolor: alpha("#6366f1", 0.2),
                  transform: "scale(1.05)",
                },
                transition: "all 0.2s ease-in-out",
              }}
            >
              <Add />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Chat list */}
      <Box
        sx={{
          px: 2,
          py: 1,
          display: { xs: "none", md: "block" },
        }}
      >
        <Typography
          variant="body2"
          color="text.secondary"
          fontWeight={500}
          sx={{ mb: 2 }}
        >
          Conversations récentes
        </Typography>
      </Box>

      <List
        sx={{
          overflowY: "auto",
          flex: 1,
          px: 2,
          display: { xs: "none", md: "block" },
        }}
      >
        {chats.map((chat, index) => {
          const isEditing = editingId === chat.id;

          return (
            <Fade in key={chat.id} timeout={300 + index * 50}>
              <ListItem
                disablePadding
                sx={{
                  mb: 1,
                  borderRadius: 2,
                  overflow: "hidden",
                  position: "relative",
                  "&:hover .action-buttons": {
                    opacity: 1,
                  },
                }}
              >
                <ListItemButton
                  selected={chat.id === selectedChatId}
                  onClick={() => {
                    if (!isEditing) onSelectChat(chat.id);
                  }}
                  sx={{
                    px: 2,
                    py: 1.5,
                    borderRadius: 2,
                    position: "relative",
                    "&.Mui-selected": {
                      bgcolor: alpha("#6366f1", 0.15),
                      "&::before": {
                        content: '""',
                        position: "absolute",
                        left: 0,
                        top: "50%",
                        transform: "translateY(-50%)",
                        width: 3,
                        height: "60%",
                        bgcolor: "primary.main",
                        borderRadius: "0 2px 2px 0",
                      },
                      "&:hover": {
                        bgcolor: alpha("#6366f1", 0.2),
                      },
                    },
                    "&:hover": {
                      bgcolor: alpha("#6366f1", 0.08),
                    },
                  }}
                >
                  {isEditing ? (
                    <Box
                      component="form"
                      onSubmit={(e) => {
                        e.preventDefault();
                        const trimmed = editText.trim();
                        if (trimmed && trimmed !== chat.name) {
                          handleRename(chat.id, trimmed);
                        } else {
                          setEditingId(null);
                        }
                      }}
                      sx={{ width: "100%" }}
                    >
                      <TextField
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        onBlur={() => {
                          const trimmed = editText.trim();
                          if (trimmed && trimmed !== chat.name) {
                            handleRename(chat.id, trimmed);
                          } else {
                            setEditingId(null);
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Escape") {
                            setEditingId(null);
                          }
                        }}
                        autoFocus
                        fullWidth
                        variant="standard"
                        size="small"
                        inputProps={{ maxLength: 50 }}
                        sx={{
                          input: {
                            color: "#fff",
                            bgcolor: "#333",
                            px: 1,
                            borderRadius: 1,
                          },
                        }}
                      />
                    </Box>
                  ) : (
                    <>
                      <Avatar
                        sx={{
                          width: 32,
                          height: 32,
                          mr: 2,
                          bgcolor: alpha("#10b981", 0.1),
                          border: "2px solid",
                          borderColor: alpha("#10b981", 0.2),
                        }}
                      >
                        <Chat sx={{ fontSize: 16, color: "secondary.main" }} />
                      </Avatar>
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography
                          variant="body2"
                          noWrap
                          sx={{
                            fontSize: "0.875rem",
                            fontWeight: chat.id === selectedChatId ? 600 : 400,
                            color: "text.primary",
                            mb: 0.5,
                          }}
                        >
                          {chat.name || `Chat #${chat.id}`}
                        </Typography>
                        <Tooltip
                          title={formatFullDateTime(chat.created_at)}
                          arrow
                        >
                          <Box
                            sx={{
                              display: "flex",
                              alignItems: "center",
                              gap: 0.5,
                            }}
                          >
                            <AccessTime
                              sx={{
                                fontSize: 12,
                                color: "text.secondary",
                                opacity: 0.7,
                              }}
                            />
                            <Typography
                              variant="caption"
                              sx={{
                                fontSize: "0.75rem",
                                color: "text.secondary",
                                opacity: 0.8,
                              }}
                            >
                              {formatRelativeTime(chat.created_at)}
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Box>

                      {/* Action buttons */}
                      <Box
                        className="action-buttons"
                        sx={{
                          display: "flex",
                          gap: 0.5,
                          opacity: 0,
                          transition: "opacity 0.2s ease-in-out",
                        }}
                      >
                        <Tooltip title="Renommer">
                          <IconButton
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingId(chat.id);
                              setEditText(chat.name);
                            }}
                            sx={{
                              color: "text.secondary",
                              "&:hover": {
                                color: "primary.main",
                                bgcolor: alpha("#6366f1", 0.1),
                              },
                            }}
                          >
                            <Edit fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Supprimer">
                          <IconButton
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              openDeleteModal(chat);
                            }}
                            disabled={isDeleting}
                            sx={{
                              color: "text.secondary",
                              "&:hover": {
                                color: "error.main",
                                bgcolor: alpha("#ef4444", 0.1),
                              },
                              "&:disabled": {
                                opacity: 0.5,
                              },
                            }}
                          >
                            {isDeleting && chatToDelete?.id === chat.id ? (
                              <CircularProgress size={16} />
                            ) : (
                              <Delete fontSize="small" />
                            )}
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </>
                  )}
                </ListItemButton>
              </ListItem>
            </Fade>
          );
        })}
      </List>

      {/* Footer with logout */}
      <Box
        sx={{
          p: 2,
          borderTop: "1px solid",
          borderColor: alpha("#475569", 0.3),
          display: { xs: "none", md: "block" },
        }}
      >
        <Button
          variant="outlined"
          fullWidth
          startIcon={<Logout />}
          onClick={handleLogout}
          sx={{
            borderColor: alpha("#ef4444", 0.3),
            color: "error.main",
            "&:hover": {
              borderColor: "error.main",
              bgcolor: alpha("#ef4444", 0.1),
              transform: "translateY(-1px)",
            },
            transition: "all 0.2s ease-in-out",
          }}
        >
          Se déconnecter
        </Button>
      </Box>

      {/* Modal de confirmation de suppression */}
      <ConfirmDeleteModal
        open={deleteModalOpen}
        onClose={closeDeleteModal}
        onConfirm={handleDeleteConfirm}
        title="Supprimer la conversation"
        message="Êtes-vous sûr de vouloir supprimer cette conversation ? Cette action est irréversible et tous les messages seront définitivement perdus."
        itemName={chatToDelete?.name}
        isLoading={isDeleting}
      />
    </Box>
  );
}
