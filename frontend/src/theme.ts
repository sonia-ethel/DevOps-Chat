// src/theme.ts
import { createTheme } from "@mui/material";

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#6366f1", // Modern indigo
      light: "#8b5cf6", // Purple accent
      dark: "#4f46e5",
    },
    secondary: {
      main: "#10b981", // Emerald
      light: "#34d399",
      dark: "#059669",
    },
    background: {
      default: "#0f172a", // Slate-900
      paper: "#1e293b", // Slate-800
    },
    text: {
      primary: "#f1f5f9", // Slate-100
      secondary: "#cbd5e1", // Slate-300
    },
    error: {
      main: "#ef4444", // Red-500
      light: "#f87171",
      dark: "#dc2626",
    },
    warning: {
      main: "#f59e0b", // Amber-500
      light: "#fbbf24",
      dark: "#d97706",
    },
    success: {
      main: "#10b981", // Emerald-500
      light: "#34d399",
      dark: "#059669",
    },
    grey: {
      50: "#f8fafc",
      100: "#f1f5f9",
      200: "#e2e8f0",
      300: "#cbd5e1",
      400: "#94a3b8",
      500: "#64748b",
      600: "#475569",
      700: "#334155",
      800: "#1e293b",
      900: "#0f172a",
    },
  },
  typography: {
    fontFamily: '"Inter", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h1: {
      fontWeight: 700,
      fontSize: "2.5rem",
      lineHeight: 1.2,
      letterSpacing: "-0.025em",
    },
    h2: {
      fontWeight: 600,
      fontSize: "2rem",
      lineHeight: 1.3,
      letterSpacing: "-0.025em",
    },
    h3: {
      fontWeight: 600,
      fontSize: "1.5rem",
      lineHeight: 1.4,
    },
    h4: {
      fontWeight: 500,
      fontSize: "1.25rem",
      lineHeight: 1.4,
    },
    body1: {
      fontSize: "0.875rem",
      lineHeight: 1.5,
    },
    body2: {
      fontSize: "0.75rem",
      lineHeight: 1.5,
    },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          scrollbarWidth: "thin",
          "&::-webkit-scrollbar": {
            width: "6px",
          },
          "&::-webkit-scrollbar-track": {
            backgroundColor: "#1e293b",
          },
          "&::-webkit-scrollbar-thumb": {
            backgroundColor: "#475569",
            borderRadius: "3px",
            "&:hover": {
              backgroundColor: "#64748b",
            },
          },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 500,
          borderRadius: 8,
          padding: "8px 16px",
          transition: "all 0.2s ease-in-out",
          "&:hover": {
            transform: "translateY(-1px)",
            boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
          },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          "& .MuiOutlinedInput-root": {
            borderRadius: 8,
            backgroundColor: "#1e293b",
            "&:hover .MuiOutlinedInput-notchedOutline": {
              borderColor: "#6366f1",
            },
            "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
              borderColor: "#6366f1",
              borderWidth: 2,
            },
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          backdropFilter: "blur(20px)",
          border: "1px solid rgba(148, 163, 184, 0.1)",
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          margin: "2px 8px",
          "&:hover": {
            backgroundColor: "rgba(99, 102, 241, 0.1)",
            transform: "translateX(4px)",
            transition: "all 0.2s ease-in-out",
          },
          "&.Mui-selected": {
            backgroundColor: "rgba(99, 102, 241, 0.2)",
            borderLeft: "3px solid #6366f1",
            "&:hover": {
              backgroundColor: "rgba(99, 102, 241, 0.3)",
            },
          },
        },
      },
    },
  },
});

export default theme;
