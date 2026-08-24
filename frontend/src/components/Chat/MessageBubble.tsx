import { Box, Paper, Typography, Avatar, alpha, useTheme } from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { parseServerDate } from "../../utils/dateUtils";

// Mapping markdown -> MUI sans spread de props (évite ref/className)
const mdComponents = {
  p: ({ children }: any) => (
    <Box
      component="div"
      sx={{
        mb: 1,
        "&:last-child": { mb: 0 },
        lineHeight: 1.6,
        fontSize: "0.9rem",
      }}
    >
      {children}
    </Box>
  ),
  h1: ({ children }: any) => (
    <Typography variant="h5" sx={{ mt: 2, mb: 1, fontWeight: 600 }}>
      {children}
    </Typography>
  ),
  h2: ({ children }: any) => (
    <Typography variant="h6" sx={{ mt: 2, mb: 1, fontWeight: 600 }}>
      {children}
    </Typography>
  ),
  h3: ({ children }: any) => (
    <Typography variant="subtitle1" sx={{ mt: 1.5, mb: 1, fontWeight: 600 }}>
      {children}
    </Typography>
  ),
  strong: ({ children }: any) => (
    <strong style={{ fontWeight: 600 }}>{children}</strong>
  ),
  code: ({ inline, children }: any) =>
    inline ? (
      <Box
        component="code"
        sx={{
          px: 0.6,
          py: 0.2,
          borderRadius: 1,
          fontFamily: "monospace",
          fontSize: "0.9em",
          bgcolor: "rgba(0,0,0,0.06)",
        }}
      >
        {children}
      </Box>
    ) : (
      <Box
        component="pre"
        sx={{
          mt: 1,
          mb: 1.2,
          p: 1.2,
          borderRadius: 2,
          overflow: "auto",
          bgcolor: "rgba(0,0,0,0.06)",
        }}
      >
        <Box
          component="code"
          sx={{ fontFamily: "monospace", fontSize: "0.9em" }}
        >
          {children}
        </Box>
      </Box>
    ),
  ul: ({ children }: any) => (
    <Box component="ul" sx={{ pl: 3, mb: 1.2 }}>
      {children}
    </Box>
  ),
  ol: ({ children }: any) => (
    <Box component="ol" sx={{ pl: 3, mb: 1.2 }}>
      {children}
    </Box>
  ),
  li: ({ children }: any) => (
    <Box component="li" sx={{ mb: 0.5 }}>
      {children}
    </Box>
  ),
  blockquote: ({ children }: any) => (
    <Box
      component="blockquote"
      sx={{
        m: 0,
        mt: 1,
        mb: 1.2,
        pl: 2,
        borderLeft: "3px solid rgba(0,0,0,0.2)",
        opacity: 0.9,
      }}
    >
      {children}
    </Box>
  ),
  a: ({ href, children }: any) => (
    <Box
      component="a"
      href={href}
      target="_blank"
      rel="noreferrer"
      sx={{ color: "primary.main" }}
    >
      {children}
    </Box>
  ),
  table: ({ children }: any) => (
    <Box component="div" sx={{ overflowX: "auto", my: 1 }}>
      <Box component="table" sx={{ width: "100%", borderCollapse: "collapse" }}>
        {children}
      </Box>
    </Box>
  ),
  th: ({ children }: any) => (
    <Box
      component="th"
      sx={{
        borderBottom: "1px solid rgba(0,0,0,0.15)",
        textAlign: "left",
        p: 1,
      }}
    >
      {children}
    </Box>
  ),
  td: ({ children }: any) => (
    <Box
      component="td"
      sx={{ borderBottom: "1px solid rgba(0,0,0,0.08)", p: 1 }}
    >
      {children}
    </Box>
  ),
};
import { Person, SmartToy, Schedule } from "@mui/icons-material";

interface Message {
  sender: "user" | "bot";
  text: string;
  timestamp?: string;
}

interface MessageBubbleProps {
  message: Message;
  isConsecutive: boolean;
}

function formatTime(timestamp?: string) {
  if (!timestamp) return "";
  const date = parseServerDate(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "À l'instant";
  if (diffMins < 60) return `Il y a ${diffMins}min`;
  if (diffHours < 24) return `Il y a ${diffHours}h`;
  if (diffDays === 1) return "Hier";
  if (diffDays < 7) return `Il y a ${diffDays}j`;

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MessageBubble({
  message,
  isConsecutive,
}: MessageBubbleProps) {
  const theme = useTheme();
  const isUser = message.sender === "user";

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: isUser ? "row-reverse" : "row",
        alignItems: "flex-start",
        gap: 1.5,
        mb: isConsecutive ? 0.5 : 2,
      }}
    >
      {/* Avatar */}
      <Avatar
        sx={{
          width: 36,
          height: 36,
          visibility: isConsecutive ? "hidden" : "visible",
          background: isUser
            ? "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)"
            : "linear-gradient(135deg, #10b981 0%, #34d399 100%)",
          boxShadow: theme.shadows[3],
        }}
      >
        {isUser ? <Person /> : <SmartToy />}
      </Avatar>

      {/* Message Content */}
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: isUser ? "flex-end" : "flex-start",
          maxWidth: { xs: "85%", sm: "75%", md: "65%" },
          flex: 1,
        }}
      >
        {/* Sender info and timestamp */}
        {!isConsecutive && (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
              mb: 0.5,
              color: "text.secondary",
            }}
          >
            <Typography variant="caption" fontWeight={500}>
              {isUser ? "Vous" : "Assistant DevOps"}
            </Typography>
            {message.timestamp && (
              <>
                <Schedule sx={{ fontSize: 12, opacity: 0.7 }} />
                <Typography variant="caption" sx={{ opacity: 0.8 }}>
                  {formatTime(message.timestamp)}
                </Typography>
              </>
            )}
          </Box>
        )}

        {/* Message bubble */}
        <Paper
          elevation={0}
          sx={{
            bgcolor: isUser
              ? alpha(theme.palette.primary.main, 0.1)
              : alpha(theme.palette.secondary.main, 0.05),
            border: `1px solid ${
              isUser
                ? alpha(theme.palette.primary.main, 0.2)
                : alpha(theme.palette.secondary.main, 0.1)
            }`,
            color: "text.primary",
            px: 2.5,
            py: 1.5,
            borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
            position: "relative",
            backdropFilter: "blur(10px)",
            "&:hover": {
              bgcolor: isUser
                ? alpha(theme.palette.primary.main, 0.15)
                : alpha(theme.palette.secondary.main, 0.08),
              transform: "translateY(-1px)",
              boxShadow: theme.shadows[4],
            },
            transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
          }}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={mdComponents as any}
          >
            {message.text}
          </ReactMarkdown>
        </Paper>
      </Box>
    </Box>
  );
}
