import { useState, useCallback, useEffect } from 'react';
import { FaCheck, FaSpinner, FaShieldAlt, FaSync } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import SudoPasswordDialog from './SudoPasswordDialog';
import { SettingsCard, NoticeCallout } from './ui';

/**
 * Component for checking and fixing timedatectl sudoers configuration.
 * Checks if NOPASSWD rules exist for `timedatectl set-timezone` and
 * `timedatectl set-ntp`, and allows creating the sudoers file via
 * SudoPasswordDialog.
 */
export default function FixTimezoneSudoers() {
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
      const { data } = await axios.get('/api/timezone/sudoers/check');
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
      const { data } = await axios.post('/api/timezone/sudoers/fix', { password });
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

  /**
   * When the rules are already in place there is nothing to do, and a full
   * card saying so pushed the actual timezone controls below the fold. A
   * single line is enough to confirm it, with the re-check still reachable.
   */
  if (isOk && !loading && !fixResult) {
    return (
      <div className="stg-inset flex items-center gap-2.5 px-3.5 py-2.5 text-[13px]">
        <FaCheck className="text-success shrink-0" />
        <span className="text-base-content/70 min-w-0 flex-1">
          {t('timezone_sudoers.status_ok')}
        </span>
        <button
          className="btn btn-ghost btn-xs gap-1.5 shrink-0"
          onClick={checkSudoers}
          disabled={loading}
        >
          <FaSync className="w-3 h-3" />
          <span className="hidden sm:inline">{t('timezone_sudoers.check_now')}</span>
        </button>
      </div>
    );
  }

  return (
    <>
      <SettingsCard
        icon={<FaShieldAlt />}
        title={t('timezone_sudoers.title')}
        description={t('timezone_sudoers.description')}
        action={
          <button
            className="btn btn-ghost btn-sm gap-2"
            onClick={checkSudoers}
            disabled={loading}
          >
            {loading ? <FaSpinner className="animate-spin" /> : <FaSync />}
            {t('timezone_sudoers.check_now')}
          </button>
        }
      >
        <div className="space-y-3">
          {/* Loading */}
          {loading && (
            <div className="flex items-center gap-2.5 text-[13px] text-base-content/60">
              <FaSpinner className="animate-spin" />
              {t('timezone_sudoers.checking')}
            </div>
          )}

          {/* Status OK */}
          {isOk && !loading && (
            <NoticeCallout
              variant="success"
              title={t('timezone_sudoers.status_ok')}
              message={t('timezone_sudoers.status_ok_hint')}
            />
          )}

          {/* Needs fix */}
          {needsFix && !loading && (
            <>
              <NoticeCallout
                variant="warning"
                title={t('timezone_sudoers.password_required')}
                message={
                  <>
                    {t('timezone_sudoers.password_required_hint')}
                    {checkResult?.error && (
                      <span className="block font-mono text-xs opacity-60 mt-1">
                        {checkResult.error}
                      </span>
                    )}
                  </>
                }
                action={
                  <button
                    className="btn btn-primary btn-sm gap-2"
                    onClick={() => {
                      setSudoError(null);
                      setShowSudoDialog(true);
                    }}
                  >
                    <FaShieldAlt />
                    {t('timezone_sudoers.create_sudoers')}
                  </button>
                }
              />

              <NoticeCallout
                variant="neutral"
                message={
                  <>
                    <span className="block">{t('timezone_sudoers.info_1')}</span>
                    <code className="block font-mono text-xs mt-1 text-base-content/70">
                      /etc/sudoers.d/boneio-timedatectl
                    </code>
                    <span className="block mt-1">{t('timezone_sudoers.info_2')}</span>
                  </>
                }
              />
            </>
          )}

          {/* Fix result */}
          {fixResult && (
            <NoticeCallout
              variant={fixResult.status === 'success' ? 'success' : 'error'}
              message={fixResult.message}
            />
          )}
        </div>
      </SettingsCard>

      <SudoPasswordDialog
        open={showSudoDialog}
        onOpenChange={setShowSudoDialog}
        title={t('timezone_sudoers.title')}
        description={t('timezone_sudoers.password_required_hint')}
        submitLabel={t('timezone_sudoers.create_sudoers')}
        isSubmitting={fixing}
        error={sudoError}
        onSubmit={fixSudoers}
      />
    </>
  );
}
