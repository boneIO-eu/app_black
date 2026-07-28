/**
 * Hook for detecting and handling device tree overlay mismatches
 * when the hardware version is changed in the boneio config section.
 */
import { useState, useCallback } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';

/** Mapping: board version → expected overlay basename */
const VERSION_TO_OVERLAY: Record<string, string> = {
  '0.2': 'BONEIO-BLACK-PINS-v0.2-v0.3.dtbo',
  '0.3': 'BONEIO-BLACK-PINS-v0.2-v0.3.dtbo',
  '0.4': 'BONEIO-BLACK-PINS-v0.4-v0.8.dtbo',
  '0.5': 'BONEIO-BLACK-PINS-v0.4-v0.8.dtbo',
  '0.6': 'BONEIO-BLACK-PINS-v0.4-v0.8.dtbo',
  '0.7': 'BONEIO-BLACK-PINS-v0.4-v0.8.dtbo',
  '0.8': 'BONEIO-BLACK-PINS-v0.4-v0.8.dtbo',
  '1.0': 'BONEIO-BLACK-PINS-v1.0.dtbo',
};

interface OverlayStatus {
  current_overlay: string | null;
  expected_overlay: string | null;
  uenv_path: string | null;
  match: boolean;
  error?: string;
}

interface OverlayDialogState {
  open: boolean;
  currentOverlay: string | null;
  expectedOverlay: string | null;
  newVersion: string;
}

interface OverlayChangeResponse {
  status: 'changed' | 'unchanged' | 'error';
  message: string;
  overlay?: string;
  previous_overlay?: string;
  restart_required?: boolean;
}

/**
 * Provides overlay mismatch detection and change functionality.
 *
 * After saving the 'boneio' section with a new version, call `checkOverlayAfterVersionChange()`
 * to detect if the device tree overlay needs updating. If a mismatch is found, opens a
 * confirmation dialog that asks for sudo password.
 */
export function useOverlayCheck() {
  const { t } = useTranslation();
  const [dialogState, setDialogState] = useState<OverlayDialogState>({
    open: false,
    currentOverlay: null,
    expectedOverlay: null,
    newVersion: '',
  });
  const [isChanging, setIsChanging] = useState(false);
  const [changeResult, setChangeResult] = useState<'success' | 'error' | null>(null);
  const [changeError, setChangeError] = useState<string | null>(null);

  /**
   * Check if the overlay matches the new board version.
   * Opens a dialog if there's a mismatch.
   *
   * @param newVersion - The newly saved board version string (e.g. "0.4")
   */
  const checkOverlayAfterVersionChange = useCallback(async (newVersion: string) => {
    const expectedOverlay = VERSION_TO_OVERLAY[newVersion];
    if (!expectedOverlay) return;

    try {
      const { data } = await axios.get<OverlayStatus>('/api/system/overlay');

      if (data.error || !data.current_overlay) return;

      // No mismatch — current overlay already matches the expected one
      if (data.current_overlay === expectedOverlay) return;

      // Mismatch detected — show dialog
      setDialogState({
        open: true,
        currentOverlay: data.current_overlay,
        expectedOverlay,
        newVersion,
      });
    } catch {
      // Non-critical — overlay check is best-effort
      console.debug('Overlay check failed (non-critical)');
    }
  }, []);

  /**
   * Apply the overlay change via sudo.
   *
   * @param password - Sudo password for writing to /boot/uEnv.txt
   * @returns true if change was successful
   */
  const applyOverlayChange = useCallback(async (password: string): Promise<boolean> => {
    if (!dialogState.expectedOverlay) return false;

    setIsChanging(true);
    setChangeResult(null);
    setChangeError(null);

    try {
      const { data } = await axios.post<OverlayChangeResponse>('/api/system/overlay', {
        overlay: dialogState.expectedOverlay,
        password,
      });

      if (data.status === 'changed' || data.status === 'unchanged') {
        setChangeResult('success');
        // Close dialog after a short delay to show success
        setTimeout(() => {
          setDialogState(prev => ({ ...prev, open: false }));
          setChangeResult(null);
        }, 2000);
        return true;
      } else {
        setChangeResult('error');
        setChangeError(data.message || t('overlay.change_failed'));
        return false;
      }
    } catch (err: unknown) {
      setChangeResult('error');
      // Extract error message from HTTP error response (4xx/5xx)
      const axiosErr = err as { response?: { data?: { message?: string } } };
      const serverMessage = axiosErr.response?.data?.message;
      const errorMsg = serverMessage || (err instanceof Error ? err.message : String(err));
      setChangeError(errorMsg);
      return false;
    } finally {
      setIsChanging(false);
    }
  }, [dialogState.expectedOverlay, t]);

  /**
   * Dismiss the overlay change dialog without making changes.
   */
  const dismissDialog = useCallback(() => {
    setDialogState(prev => ({ ...prev, open: false }));
    setChangeResult(null);
    setChangeError(null);
  }, []);

  return {
    overlayDialog: dialogState,
    isChangingOverlay: isChanging,
    overlayChangeResult: changeResult,
    overlayChangeError: changeError,
    checkOverlayAfterVersionChange,
    applyOverlayChange,
    dismissDialog,
  };
}
