// src/hooks/useAWSInstances.ts

import { useState, useCallback, useEffect } from 'react';
import axiosClient from '../api/axiosClient';

interface AWSInstance {
  instance_id: string;
  state?: string;
  public_ip?: string;
  private_ip?: string;
  provider: string;
  source: 'database' | 'cloud_api';
  launch_time?: string;
}

interface UseAWSInstancesReturn {
  instances: AWSInstance[];
  loading: boolean;
  error: string | null;
  deleting: Set<string>;
  loadInstances: () => Promise<void>;
  deleteInstance: (instanceId: string) => Promise<void>;
  refreshInstances: () => Promise<void>;
  clearError: () => void;
}

export const useAWSInstances = (sessionId: number | null): UseAWSInstancesReturn => {
  const [instances, setInstances] = useState<AWSInstance[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Set<string>>(new Set());

  //  Charger les instances
  const loadInstances = useCallback(async () => {
    if (!sessionId) {
      setInstances([]);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await axiosClient.get('/resources/list_all_resources', {
        params: { session_id: sessionId },
      });

      const { cloud_resources, database_resources } = response.data;

      // Déduplication par instance_id (priorité aux cloud_resources)
      const instanceMap = new Map<string, AWSInstance>();
      
      // D'abord les database resources
      database_resources?.forEach((r: any) => {
        instanceMap.set(r.instance_id, {
          instance_id: r.instance_id,
          state: 'unknown',
          public_ip: r.public_ip,
          provider: r.provider,
          source: 'database' as const,
        });
      });

      // Puis les cloud resources (écrasent les database resources si même ID)
      cloud_resources?.forEach((r: any) => {
        instanceMap.set(r.instance_id, {
          instance_id: r.instance_id,
          state: r.state,
          public_ip: r.public_ip,
          provider: r.provider,
          source: 'cloud_api' as const,
          launch_time: r.launch_time,
        });
      });

      const uniqueInstances = Array.from(instanceMap.values())
        .sort((a, b) => a.instance_id.localeCompare(b.instance_id));

      setInstances(uniqueInstances);
      
      console.log(` Loaded ${uniqueInstances.length} AWS instances`);
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || err.message || 'Erreur lors du chargement';
      setError(errorMessage);
      console.error(' Error loading AWS instances:', err);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  //  Supprimer une instance
  const deleteInstance = useCallback(async (instanceId: string) => {
    if (!sessionId) return;

    setDeleting(prev => new Set(prev).add(instanceId));
    setError(null);

    try {
      console.log(` Deleting instance ${instanceId}...`);
      
      //  Essayer d'abord la nouvelle API de suppression directe
      try {
        const response = await axiosClient.post('/resources/delete_resource_direct', null, {
          params: {
            session_id: sessionId,
            instance_id: instanceId,
          },
        });
        
        const result = response.data;
        
        if (result.source === 'cleanup_db_only') {
          console.log(` Instance ${instanceId} cleaned up (was already deleted on AWS):`, result.details);
        } else {
          console.log(` Instance ${instanceId} deleted via direct API:`, result.details);
        }
        
      } catch (directApiError: any) {
        const directErrorMsg = directApiError.response?.data?.detail || 'Unknown error';
        console.warn(` Direct API failed, trying legacy API:`, directErrorMsg);
        
        //  Fallback vers l'ancienne API si la directe échoue
        await axiosClient.post('/resources/delete_resource', null, {
          params: {
            session_id: sessionId,
            instance_id: instanceId,
          },
        });
        
        console.log(` Instance ${instanceId} deleted via legacy API`);
      }

      // Supprimer immédiatement de la liste locale (optimistic update)
      setInstances(prev => prev.filter(instance => instance.instance_id !== instanceId));
      
    } catch (err: any) {
      let errorMessage = 'Erreur lors de la suppression';
      
      if (err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      //  Messages d'erreur plus explicites
      if (errorMessage.includes("Aucune instance n'a pu être supprimée")) {
        errorMessage = `L'instance ${instanceId} n'est pas trackée dans le système. Utilisez l'AWS Console pour la supprimer manuellement.`;
      }
      
      setError(errorMessage);
      console.error(` Error deleting instance ${instanceId}:`, err);
      
      // En cas d'erreur, recharger la liste pour avoir l'état actuel
      await loadInstances();
    } finally {
      setDeleting(prev => {
        const newSet = new Set(prev);
        newSet.delete(instanceId);
        return newSet;
      });
    }
  }, [sessionId, loadInstances]);

  //  Alias pour refresh
  const refreshInstances = useCallback(async () => {
    await loadInstances();
  }, [loadInstances]);

  //  Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  //  Auto-load when sessionId changes
  useEffect(() => {
    loadInstances();
  }, [loadInstances]);

  return {
    instances,
    loading,
    error,
    deleting,
    loadInstances,
    deleteInstance,
    refreshInstances,
    clearError,
  };
};