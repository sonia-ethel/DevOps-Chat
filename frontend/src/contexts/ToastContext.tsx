import {
  createContext,
  useContext,
  useState,
  useCallback,
} from "react";
import type { ReactNode } from "react";
import {
  Snackbar,
  Alert,
  Slide,
} from "@mui/material";
import type { AlertColor, SlideProps } from "@mui/material";

type TransitionProps = Omit<SlideProps, 'direction'>;

function SlideTransition(props: TransitionProps) {
  return <Slide {...props} direction="up" />;
}

interface Toast {
  id: string;
  message: string;
  type: AlertColor;
  duration?: number;
}

interface ToastContextType {
  showToast: (message: string, type?: AlertColor, duration?: number) => void;
  showSuccess: (message: string, duration?: number) => void;
  showError: (message: string, duration?: number) => void;
  showInfo: (message: string, duration?: number) => void;
  showWarning: (message: string, duration?: number) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}

interface ToastProviderProps {
  children: ReactNode;
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev: Toast[]) => prev.filter((toast: Toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: AlertColor = "info", duration: number = 4000) => {
      const id = Date.now().toString() + Math.random().toString(36);
      const newToast: Toast = { id, message, type, duration };

      setToasts((prev: Toast[]) => [...prev, newToast]);

      if (duration > 0) {
        setTimeout(() => removeToast(id), duration);
      }
    },
    [removeToast]
  );

  const showSuccess = useCallback(
    (message: string, duration: number = 4000) => {
      showToast(message, "success", duration);
    },
    [showToast]
  );

  const showError = useCallback(
    (message: string, duration: number = 6000) => {
      showToast(message, "error", duration);
    },
    [showToast]
  );

  const showInfo = useCallback(
    (message: string, duration: number = 4000) => {
      showToast(message, "info", duration);
    },
    [showToast]
  );

  const showWarning = useCallback(
    (message: string, duration: number = 5000) => {
      showToast(message, "warning", duration);
    },
    [showToast]
  );

  const contextValue: ToastContextType = {
    showToast,
    showSuccess,
    showError,
    showInfo,
    showWarning,
  };

  // On affiche seulement le toast le plus récent
  const currentToast = toasts[toasts.length - 1];

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      <Snackbar
        open={!!currentToast}
        autoHideDuration={currentToast?.duration || 4000}
        onClose={() => currentToast && removeToast(currentToast.id)}
        TransitionComponent={SlideTransition}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        sx={{
          "& .MuiSnackbarContent-root": {
            minWidth: 300,
          },
        }}
      >
        {currentToast && (
          <Alert
            onClose={() => removeToast(currentToast.id)}
            severity={currentToast.type}
            variant="filled"
            sx={{
              width: "100%",
              fontWeight: 500,
              "& .MuiAlert-message": {
                fontSize: "0.875rem",
              },
            }}
          >
            {currentToast.message}
          </Alert>
        )}
      </Snackbar>
    </ToastContext.Provider>
  );
}