import { useState, useCallback, useEffect } from 'react';
import axios from '@/api/axios';

export interface NodeRedBackup {
  path: string;
  filename: string;
  timestamp: string;
  size: number;
  version: string;
  sha256: string | null;
}

export interface NodeRedStatus {
  running: boolean;
  version: string;
  data_dir_exists: boolean;
  compose_exists: boolean;
}

export interface NodeRedUpdateInfo {
  current_version: string;
  latest_version: string;
  update_available: boolean;
}

export interface NodeRedUpdateProgress {
  status: 'idle' | 'running' | 'success' | 'error';
  progress: number;
  step: string;
  log: string[];
  error: string | null;
}

export const useNodeRedManagement = () => {
  const [status, setStatus] = useState<NodeRedStatus | null>(null);
  const [backups, setBackups] = useState<NodeRedBackup[]>([]);
  const [updateInfo, setUpdateInfo] = useState<NodeRedUpdateInfo | null>(null);
  const [updateProgress, setUpdateProgress] = useState<NodeRedUpdateProgress | null>(null);
  
  const [isLoadingStatus, setIsLoadingStatus] = useState(false);
  const [isLoadingBackups, setIsLoadingBackups] = useState(false);
  const [isCheckingUpdate, setIsCheckingUpdate] = useState(false);
  const [isCreatingBackup, setIsCreatingBackup] = useState(false);
  const [isRestoringBackup, setIsRestoringBackup] = useState(false);
  const [isUploadingRestore, setIsUploadingRestore] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    setIsLoadingStatus(true);
    try {
      const { data } = await axios.get<NodeRedStatus>('/api/nodered/status');
      setStatus(data);
    } catch (err) {
      console.error('Failed to fetch Node-RED status:', err);
    } finally {
      setIsLoadingStatus(false);
    }
  }, []);

  const fetchBackups = useCallback(async () => {
    setIsLoadingBackups(true);
    try {
      const { data } = await axios.get<{ backups: NodeRedBackup[] }>('/api/nodered/backup/list');
      setBackups(data.backups || []);
    } catch (err) {
      console.error('Failed to fetch Node-RED backups:', err);
    } finally {
      setIsLoadingBackups(false);
    }
  }, []);

  const createBackup = useCallback(async () => {
    setIsCreatingBackup(true);
    setError(null);
    try {
      const { data } = await axios.post<{ status: string; message: string }>('/api/nodered/backup/create', null, { timeout: 30000 });
      if (data.status === 'success') {
        await fetchBackups();
        return true;
      } else {
        setError(data.message);
        return false;
      }
    } catch (err) {
      setError('Failed to create Node-RED backup');
      console.error(err);
      return false;
    } finally {
      setIsCreatingBackup(false);
    }
  }, [fetchBackups]);

  const restoreBackup = useCallback(async (backupPath: string) => {
    setIsRestoringBackup(true);
    setError(null);
    try {
      const { data } = await axios.post<{ status: string; message: string }>(
        `/api/nodered/backup/restore?backup_path=${encodeURIComponent(backupPath)}`,
        null,
        { timeout: 120_000 },
      );
      if (data.status === 'success') {
        await fetchStatus();
        return true;
      } else {
        setError(data.message);
        return false;
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || 'Failed to restore Node-RED backup');
      console.error(err);
      return false;
    } finally {
      setIsRestoringBackup(false);
    }
  }, [fetchStatus]);

  const deleteBackup = useCallback(async (backupPath: string) => {
    setError(null);
    try {
      const { data } = await axios.delete<{ status: string; message: string }>(
        `/api/nodered/backup/delete?backup_path=${encodeURIComponent(backupPath)}`
      );
      if (data.status === 'success') {
        await fetchBackups();
        return true;
      } else {
        setError(data.message);
        return false;
      }
    } catch (err) {
      setError('Failed to delete Node-RED backup');
      console.error(err);
      return false;
    }
  }, [fetchBackups]);

  const downloadBackup = useCallback(async (backupPath: string, filename: string) => {
    try {
      const response = await axios.get(
        `/api/nodered/backup/download?backup_path=${encodeURIComponent(backupPath)}`,
        { responseType: 'blob' }
      );
      const blob = response.data;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Failed to download Node-RED backup:', err);
    }
  }, []);

  /** Upload and restore a backup from a local file with optional SHA256 verification. */
  const uploadRestore = useCallback(async (file: File, sha256?: string) => {
    setIsUploadingRestore(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      if (sha256) {
        formData.append('sha256', sha256);
      }
      const { data } = await axios.post<{ status: string; message: string; detail?: string }>(
        '/api/nodered/backup/upload_restore',
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 180_000,
        },
      );
      if (data.status === 'success') {
        await fetchStatus();
        await fetchBackups();
        return true;
      } else {
        setError(data.message || data.detail || 'Upload restore failed');
        return false;
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || 'Failed to restore from uploaded backup');
      console.error(err);
      return false;
    } finally {
      setIsUploadingRestore(false);
    }
  }, [fetchStatus, fetchBackups]);

  const checkUpdates = useCallback(async () => {
    setIsCheckingUpdate(true);
    setError(null);
    try {
      const { data } = await axios.get<NodeRedUpdateInfo>('/api/nodered/update/check');
      setUpdateInfo(data);
    } catch (err) {
      setError('Failed to check Node-RED updates');
      console.error(err);
    } finally {
      setIsCheckingUpdate(false);
    }
  }, []);

  const pollUpdateStatus = useCallback(async () => {
    try {
      const { data } = await axios.get<NodeRedUpdateProgress>('/api/nodered/update/status');
      setUpdateProgress(data);
      return data;
    } catch (err) {
      console.error('Failed to poll update status:', err);
      return null;
    }
  }, []);

  const performUpdate = useCallback(async (version?: string) => {
    setIsUpdating(true);
    setError(null);
    try {
      const params = version ? `?target_version=${encodeURIComponent(version)}` : '';
      const { data } = await axios.post<{ status: string; message: string }>(`/api/nodered/update/perform${params}`);
      
      if (data.status === 'error') {
        setError(data.message);
        setIsUpdating(false);
        return false;
      }

      const interval = setInterval(async () => {
        const progress = await pollUpdateStatus();
        if (!progress) {
          clearInterval(interval);
          setIsUpdating(false);
          return;
        }

        if (progress.status === 'success') {
          clearInterval(interval);
          setIsUpdating(false);
          await fetchStatus();
          await fetchBackups();
          await checkUpdates();
        } else if (progress.status === 'error') {
          clearInterval(interval);
          setIsUpdating(false);
          setError(progress.error || 'Update failed');
        }
      }, 1000);
      
      return true;
    } catch (err) {
      setError('Failed to start Node-RED update');
      console.error(err);
      setIsUpdating(false);
      return false;
    }
  }, [pollUpdateStatus, fetchStatus, fetchBackups, checkUpdates]);

  useEffect(() => {
    fetchStatus();
    fetchBackups();
  }, [fetchStatus, fetchBackups]);

  return {
    status,
    backups,
    updateInfo,
    updateProgress,
    isLoadingStatus,
    isLoadingBackups,
    isCheckingUpdate,
    isCreatingBackup,
    isRestoringBackup,
    isUploadingRestore,
    isUpdating,
    error,
    setError,
    fetchStatus,
    fetchBackups,
    createBackup,
    restoreBackup,
    deleteBackup,
    downloadBackup,
    uploadRestore,
    checkUpdates,
    performUpdate,
  };
};
