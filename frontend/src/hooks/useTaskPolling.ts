// src/hooks/useTaskPolling.ts

import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';

// Configuration retry exponential
const INITIAL_RETRY_DELAY = 1000; // 1s
const MAX_RETRY_DELAY = 30000;    // 30s
const MAX_RETRIES = 5;

// Types pour la gestion des connexions
type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface TaskLog {
  timestamp: string;
  level: 'info' | 'warning' | 'error' | 'success';
  message: string;
  step_name: string;
  progress_percentage?: number;
}

export interface TaskStatus {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress_percentage: number;
  current_step: string;
  task_type: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  updated_at?: string;
  error_message?: string;
  recent_logs: TaskLog[];
  result_data?: any;
  execution_id?: number;
  // Nouveaux champs pour l'amélioration UX
  substep_details?: {
    substeps?: Array<{
      name: string;
      status: 'pending' | 'in_progress' | 'completed' | 'failed';
    }>;
  };
}

interface UseTaskPollingOptions {
  /** Intervalle de polling en millisecondes (défaut: 5000 = 5s) */
  pollingInterval?: number;
  /** Timeout maximum en millisecondes (défaut: 600000 = 10min) */
  maxTimeout?: number;
  /** Auto-arrêter le polling quand la tâche est terminée */
  autoStop?: boolean;
  /** Callback appelé lors des changements de statut */
  onStatusChange?: (status: TaskStatus) => void;
  /** Callback appelé lors de la complétion */
  onComplete?: (result: any) => void;
  /** Callback appelé en cas d'erreur */
  onError?: (error: string) => void;
}

export const useTaskPolling = (taskId: string | null, options: UseTaskPollingOptions = {}) => {
  const {
    pollingInterval = 5000,  // 5 seconds - Plus fréquent pour capturer toutes les étapes
    maxTimeout = 600000,     // 10 minutes
    autoStop = true,
    onStatusChange,
    onComplete,
    onError
  } = options;

  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timeoutReached, setTimeoutReached] = useState(false);
  // Nouveaux états pour l'amélioration UX
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [retryCount, setRetryCount] = useState(0);
  const [nextRetryIn, setNextRetryIn] = useState<number | null>(null);
  
  const intervalRef = useRef<number | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const retryTimeoutRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const lastSuccessfulPoll = useRef<number>(Date.now());

  // Fonction pour calculer l'intervalle de polling adaptatif
  const getAdaptivePollingInterval = useCallback((status?: string, retryCount: number = 0) => {
    if (retryCount > 0) {
      return Math.min(INITIAL_RETRY_DELAY * Math.pow(2, retryCount - 1), MAX_RETRY_DELAY);
    }
    if (status === 'pending') return 2000;      // 2s pour démarrage rapide
    if (status === 'running') return 3000;      // 3s pendant exécution
    return pollingInterval; // défaut
  }, [pollingInterval]);

  // Fonction pour gérer les retries silencieusement
  const scheduleRetry = useCallback((currentRetryCount: number, taskId: string) => {
    if (currentRetryCount >= MAX_RETRIES) {
      // Après max retries, arrêter silencieusement le polling
      setIsPolling(false);
      return;
    }

    const delay = getAdaptivePollingInterval(undefined, currentRetryCount + 1);
    setRetryCount(currentRetryCount + 1);

    retryTimeoutRef.current = window.setTimeout(() => {
      if (mountedRef.current) {
        pollTaskStatus(taskId);
      }
    }, delay);
  }, [getAdaptivePollingInterval]);

  // Fonction de polling améliorée avec gestion des erreurs et retry
  const pollTaskStatus = useCallback(async (taskId: string) => {
    try {
      setConnectionState('connecting');
      
      const token = localStorage.getItem('access_token');
      const baseUrl = import.meta.env.VITE_API_URL || 'https://devops-backend-uzw2.onrender.com';
      const response = await axios.get(
        `${baseUrl}/async/tasks/${taskId}/status`,
        {
          headers: {
            'Authorization': token ? `Bearer ${token}` : undefined,
          },
          timeout: 10000 // Timeout de 10 secondes
        }
      );

      if (!mountedRef.current) return;

      const status: TaskStatus = response.data;
      console.log(' Task status received:', {
        taskId,
        status: status.status,
        progress: status.progress_percentage,
        step: status.current_step,
        logsCount: status.recent_logs?.length || 0
      });
      
      setTaskStatus(status);
      setError(null);
      setConnectionState('connected');
      setRetryCount(0); // Reset retry count en cas de succès
      lastSuccessfulPoll.current = Date.now();

      // Callbacks
      if (onStatusChange) {
        onStatusChange(status);
      }

      // Vérifier si terminé
      if (status.status === 'completed' && onComplete) {
        onComplete(status.result_data);
      } else if (status.status === 'failed' && onError) {
        onError(status.error_message || 'Task failed without error message');
      }

      // Auto-arrêt si terminé
      if (autoStop && ['completed', 'failed', 'cancelled'].includes(status.status)) {
        setIsPolling(false);
        setConnectionState('connected');
        if (intervalRef.current) {
          window.clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        if (timeoutRef.current) {
          window.clearTimeout(timeoutRef.current);
          timeoutRef.current = null;
        }
        if (retryTimeoutRef.current) {
          window.clearTimeout(retryTimeoutRef.current);
          retryTimeoutRef.current = null;
        }
      } else {
        // Programmer le prochain poll avec intervalle adaptatif
        const nextInterval = getAdaptivePollingInterval(status.status, 0);
        if (intervalRef.current) {
          window.clearInterval(intervalRef.current);
        }
        intervalRef.current = window.setTimeout(() => {
          pollTaskStatus(taskId);
        }, nextInterval);
      }

    } catch (err: any) {
      if (!mountedRef.current) return;

      console.warn('Task polling retry:', err.code || err.response?.status);
      
      // Différencier les types d'erreurs - gérer silencieusement les erreurs de connexion
      if (err.response?.status === 404) {
        // Tâche non trouvée - arrêter définitivement
        setError('Tâche non trouvée');
        setConnectionState('error');
        setIsPolling(false);
        if (intervalRef.current) {
          window.clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        if (onError) {
          onError('Tâche non trouvée');
        }
      } else {
        // Toutes les autres erreurs (réseau, serveur, etc.) - retry silencieusement
        // Ne pas mettre à jour connectionState pour éviter d'afficher les erreurs à l'utilisateur
        scheduleRetry(retryCount, taskId);
      }
    }
  }, [onStatusChange, onComplete, onError, autoStop, getAdaptivePollingInterval, scheduleRetry, retryCount]);

  // Démarrer le polling amélioré
  const startPolling = useCallback(() => {
    if (!taskId || isPolling) return;

    setIsPolling(true);
    setError(null);
    setTimeoutReached(false);
    setRetryCount(0);
    setNextRetryIn(null);
    // Note: Ne pas réinitialiser taskStatus ou connectionState pour une expérience utilisateur fluide

    // Premier appel immédiat
    pollTaskStatus(taskId);

    // Timeout de sécurité
    timeoutRef.current = window.setTimeout(() => {
      if (mountedRef.current) {
        setTimeoutReached(true);
        setIsPolling(false);
        setConnectionState('error');
        setError('Timeout atteint - La tâche continue en arrière-plan');
        
        if (intervalRef.current) {
          window.clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        if (retryTimeoutRef.current) {
          window.clearTimeout(retryTimeoutRef.current);
          retryTimeoutRef.current = null;
        }
        
        if (onError) {
          onError('Task polling timeout reached');
        }
      }
    }, maxTimeout);

  }, [taskId, isPolling, maxTimeout, pollTaskStatus, onError]);

  // Arrêter le polling
  const stopPolling = useCallback(() => {
    setIsPolling(false);
    setConnectionState('disconnected');
    setRetryCount(0);
    setNextRetryIn(null);
    
    if (intervalRef.current) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    if (retryTimeoutRef.current) {
      window.clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
  }, []);

  // Polling manuel (refresh)
  const refreshStatus = useCallback(() => {
    if (taskId) {
      pollTaskStatus(taskId);
    }
  }, [taskId, pollTaskStatus]);

  // Auto-start polling quand taskId change
  useEffect(() => {
    if (taskId) {
      startPolling();
    } else {
      stopPolling();
      setTaskStatus(null);
    }

    return () => {
      stopPolling();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  // Cleanup à la destruction du composant
  useEffect(() => {
    return () => {
      mountedRef.current = false;
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
      }
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
      }
      if (retryTimeoutRef.current) {
        window.clearTimeout(retryTimeoutRef.current);
      }
    };
  }, []);

  // Helpers pour l'état
  const isRunning = taskStatus?.status === 'running' || taskStatus?.status === 'pending';
  const isCompleted = taskStatus?.status === 'completed';
  const isFailed = taskStatus?.status === 'failed';
  const isCancelled = taskStatus?.status === 'cancelled';
  const isFinished = isCompleted || isFailed || isCancelled;

  return {
    taskStatus,
    isPolling,
    error,
    timeoutReached,
    
    // Nouveaux états pour l'amélioration UX
    connectionState,
    retryCount,
    nextRetryIn,
    
    // Actions
    startPolling,
    stopPolling,
    refreshStatus,
    
    // Helpers
    isRunning,
    isCompleted,
    isFailed,
    isCancelled,
    isFinished,
    
    // Computed values
    progressPercentage: taskStatus?.progress_percentage || 0,
    currentStep: taskStatus?.current_step || '',
    logs: taskStatus?.recent_logs || [],
    executionId: taskStatus?.execution_id,
    substepDetails: taskStatus?.substep_details
  };
};