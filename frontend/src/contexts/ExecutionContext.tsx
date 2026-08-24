import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";

export interface RunningExecution {
  executionId: string;
  chatId: number;
  sessionId: string;
  startedAt: Date;
}

interface ExecutionContextType {
  runningExecution: RunningExecution | null;
  setRunningExecution: (execution: RunningExecution | null) => void;
  canStartExecution: () => boolean;
  startExecution: (execution: RunningExecution) => boolean;
  endExecution: () => void;
}

const ExecutionContext = createContext<ExecutionContextType | undefined>(
  undefined,
);

export function ExecutionProvider({ children }: { children: ReactNode }) {
  const [runningExecution, setRunningExecution] =
    useState<RunningExecution | null>(null);

  const canStartExecution = useCallback(() => {
    return runningExecution === null;
  }, [runningExecution]);

  const startExecution = useCallback(
    (execution: RunningExecution): boolean => {
      if (runningExecution !== null) {
        console.warn(
          "[ExecutionContext] Une exécution est déjà en cours:",
          runningExecution.executionId,
        );
        return false;
      }
      setRunningExecution(execution);
      console.log(
        "[ExecutionContext] Exécution démarrée:",
        execution.executionId,
      );
      return true;
    },
    [runningExecution],
  );

  const endExecution = useCallback(() => {
    console.log(
      "[ExecutionContext] Exécution terminée:",
      runningExecution?.executionId,
    );
    setRunningExecution(null);
  }, [runningExecution]);

  const value: ExecutionContextType = {
    runningExecution,
    setRunningExecution,
    canStartExecution,
    startExecution,
    endExecution,
  };

  return (
    <ExecutionContext.Provider value={value}>
      {children}
    </ExecutionContext.Provider>
  );
}

export function useExecution() {
  const context = useContext(ExecutionContext);
  if (!context) {
    throw new Error("useExecution must be used within ExecutionProvider");
  }
  return context;
}
