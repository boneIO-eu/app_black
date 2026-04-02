import { useState, useCallback, useEffect } from 'react';
import { FaSpinner, FaExclamationTriangle, FaCheck, FaShieldAlt, FaSync } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import SudoPasswordDialog from './SudoPasswordDialog';

/**
 * Component for checking and fixing CAN interface sudoers configuration.
 * Always visible in SystemState page with a manual "Check" button.
 * Shows status (OK / needs fix) and allows creating sudoers file via SudoPasswordDialog.
 */
export default function FixCanSudoers() {
  const { t } = useTranslation();
  const [checkResult, setCheckResult] = useState<{
    needs_password: boolean;
    sudoers_file_exists: boolean;
    error: string | null;
  } | null>(null);
  const [fixResult, setFixResult] = useState<{
    status: string;
    message: string;
    content?: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [showSudoDialog, setShowSudoDialog] = useState(false);
  const [sudoError, setSudoError] = useState<string | null>(null);

  const checkSudoers = useCallback(async () => {
    setLoading(true);
    setCheckResult(null);
    setFixResult(null);
    try {
      const { data } = await axios.get('/api/can/sudoers/check');
      setCheckResult(data);
    } catch (err: any) {
      setCheckResult({
        needs_password: true,
        sudoers_file_exists: false,
        error: err.message || 'Request failed',
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const fixSudoers = async (password: string) => {
    setFixing(true);
    setFixResult(null);
    setSudoError(null);
    try {
      const { data } = await axios.post('/api/can/sudoers/fix', { password });
      setFixResult(data);
      if (data.status === 'success') {
        setShowSudoDialog(false);
        // Re-check to confirm fix worked
        checkSudoers();
      } else {
        setSudoError(data.message || t('common.error'));
      }
    } catch (err: any) {
      setSudoError(err.response?.data?.detail || err.message || 'Request failed');
    } finally {
      setFixing(false);
    }
  };

  // Auto-check on mount
  useEffect(() => {
    checkSudoers();
  }, [checkSudoers]);

  const needsFix = checkResult?.needs_password === true;
  const isOk = checkResult !== null && !checkResult.needs_password;

  return (
    <div className="card bg-base-200 shadow-xl">
      <div className="card-body">
        <h3 className="card-title">
          <FaShieldAlt />
          {t('can_sudoers.title')}
        </h3>
        <p className="text-sm opacity-70">
          {t('can_sudoers.description')}
        </p>

        {/* Manual check button */}
        <div className="card-actions mt-1">
          <button
            className="btn btn-outline btn-sm"
            onClick={checkSudoers}
            disabled={loading}
          >
            {loading ? <FaSpinner className="animate-spin" /> : <FaSync />}
            {t('can_sudoers.check_now')}
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center gap-2 text-sm mt-2">
            <FaSpinner className="animate-spin" />
            {t('can_sudoers.checking')}
          </div>
        )}

        {/* Status OK */}
        {isOk && !loading && (
          <div className="alert alert-success mt-2">
            <FaCheck />
            <div>
              <p className="font-semibold">{t('can_sudoers.status_ok')}</p>
              <p className="text-sm opacity-80">{t('can_sudoers.status_ok_hint')}</p>
            </div>
          </div>
        )}

        {/* Needs fix */}
        {needsFix && !loading && (
          <>
            <div className="alert alert-warning mt-2">
              <FaExclamationTriangle />
              <div>
                <p className="font-semibold">{t('can_sudoers.password_required')}</p>
                <p className="text-sm opacity-80">{t('can_sudoers.password_required_hint')}</p>
                {checkResult?.error && (
                  <p className="text-xs font-mono mt-1 opacity-60">{checkResult.error}</p>
                )}
              </div>
            </div>

            <div className="card-actions mt-2">
              <button
                className="btn btn-primary btn-sm"
                onClick={() => {
                  setSudoError(null);
                  setShowSudoDialog(true);
                }}
              >
                <FaShieldAlt />
                {t('can_sudoers.create_sudoers')}
              </button>
            </div>

            <div className="alert alert-info mt-2">
              <div className="text-xs">
                <p>{t('can_sudoers.info_1')}</p>
                <p className="font-mono mt-1">/etc/sudoers.d/boneio-can</p>
                <p className="mt-1">{t('can_sudoers.info_2')}</p>
              </div>
            </div>
          </>
        )}

        {/* Fix result */}
        {fixResult && (
          <div className={`alert ${fixResult.status === 'success' ? 'alert-success' : 'alert-error'} mt-2`}>
            {fixResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
            <span className="text-sm">{fixResult.message}</span>
          </div>
        )}
      </div>

      <SudoPasswordDialog
        open={showSudoDialog}
        onOpenChange={setShowSudoDialog}
        title={t('can_sudoers.title')}
        description={t('can_sudoers.password_required_hint')}
        submitLabel={t('can_sudoers.create_sudoers')}
        isSubmitting={fixing}
        error={sudoError}
        onSubmit={fixSudoers}
      />
    </div>
  );
}
