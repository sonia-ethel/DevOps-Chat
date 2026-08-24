import React, { useEffect, useRef, useState } from "react";
import {
  Card,
  CardContent,
  LinearProgress,
  Typography,
  Box,
  Chip,
} from "@mui/material";

type ExecutionStatus = "pending" | "running" | "completed" | "failed" | "idle";

interface AuditProgressWidgetProps {
  status: ExecutionStatus;
  progress: number;
  message: string;
  executionId: number | null;
}

export default function AuditProgressWidget({
  status,
  progress,
  message,
  executionId,
}: AuditProgressWidgetProps) {
  const [displayedProgress, setDisplayedProgress] = useState(0);
  const animationIntervalRef = useRef<number | null>(null);

  // Animation fluide de la progress bar
  useEffect(() => {
    if (status !== "running" && status !== "pending") {
      if (animationIntervalRef.current) {
        window.clearInterval(animationIntervalRef.current);
        animationIntervalRef.current = null;
      }
      return;
    }

    // Si progress réel dépasse displayed, jump directement
    if (progress > displayedProgress) {
      setDisplayedProgress(progress);
    }

    // Sinon, animation douce +1% toutes les 400ms
    if (animationIntervalRef.current) {
      window.clearInterval(animationIntervalRef.current);
    }

    if (displayedProgress < progress) {
      animationIntervalRef.current = window.setInterval(() => {
        setDisplayedProgress((prev) => {
          const next = Math.min(prev + 1, progress);
          if (next >= progress) {
            if (animationIntervalRef.current) {
              window.clearInterval(animationIntervalRef.current);
              animationIntervalRef.current = null;
            }
          }
          return next;
        });
      }, 400);
    }

    return () => {
      if (animationIntervalRef.current) {
        window.clearInterval(animationIntervalRef.current);
        animationIntervalRef.current = null;
      }
    };
  }, [progress, displayedProgress, status]);

  if (!executionId) return null;
  if (status !== "running" && status !== "pending") return null;

  const safeProgress = Math.max(0, Math.min(100, displayedProgress));
  const safeMessage = message || "En cours…";

  return (
    <Card
      sx={{
        mb: 2,
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        color: "white",
        borderRadius: 2,
      }}
    >
      <CardContent>
        <Box
          sx={{
            mb: 2,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Audit en cours…
          </Typography>
          <Chip
            label={`${Math.round(safeProgress)}%`}
            size="small"
            sx={{
              backgroundColor: "rgba(255,255,255,0.2)",
              color: "white",
              fontWeight: 600,
            }}
          />
        </Box>

        <LinearProgress
          variant="determinate"
          value={safeProgress}
          sx={{
            mb: 1.5,
            height: 8,
            borderRadius: 4,
            backgroundColor: "rgba(255,255,255,0.2)",
            "& .MuiLinearProgress-bar": { backgroundColor: "white" },
          }}
        />

        <Typography variant="body2" sx={{ fontSize: "0.95rem" }}>
          {safeMessage}
        </Typography>

        <Typography
          variant="caption"
          sx={{ display: "block", mt: 1, opacity: 0.8, fontSize: "0.75rem" }}
        >
          ID: {executionId}
        </Typography>
      </CardContent>
    </Card>
  );
}
