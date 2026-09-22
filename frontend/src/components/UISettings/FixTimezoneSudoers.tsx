import { useState, useCallback, useEffect } from 'react';
import { FaCheck, FaSpinner, FaShieldAlt, FaSync } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { SettingsCard, NoticeCallout } from './ui';

/**
 * Reports whether the timedatectl sudoers rules are in place.
 *
 * This used to offer to create them, which meant asking the operator for their
 * sudo password and posting it to `/api/timezone/sudoers/fix`. That endpoint is
 * gone: the password for this account is shared across controllers, so an
 * endpoint that collects it is a path to intercepting it. The rule now arrives
 * with system migration 1.6.7, over a channel that needs no password — so all
 * that is left here is to say whether it landed, and to point at the migrations
 * when it has not.
 */
export default function FixTimezoneSudoers() {
  const { t } = useTranslation();
  const [checkResult, setCheckResult] = useState<{
    needs_password: boolean;
    sudoers_file_exists: boolean;
    error: string | null;
  } | null>(null);
  /** Set when the request itself failed — which is not an answer about the
   *  rule, and must not be reported as one. */
  const [unreachable, setUnreachable] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const checkSudoers = useCallback(async () => {
    setLoading(true);
    setCheckResult(null);
    setUnreachable(null);
    try {
      // Longer than the backend's own five-second cap on `sudo -l`. With both
      // at five seconds the two raced, the client always lost, and a device
      // that was merely busy came back as "the rule is missing" — with the
      // migrations page next door correctly saying it had been installed.
      const { data } = await axios.get('/api/timezone/sudoers/check', { timeout: 20000 });
      setCheckResult(data);
    } catch (err: unknown) {
      // "Could not ask" is a third state. Reporting it as "not installed" sent
      // people to apply migrations that were already applied.
      const message = err instanceof Error ? err.message : String(err);
      setUnreachable(message || 'Request failed');
    } finally {
      setLoading(false);
    }
  }, []);

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
  if (isOk && !loading) {
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
        {loading && (
          <div className="flex items-center gap-2.5 text-[13px] text-base-content/60">
            <FaSpinner className="animate-spin" />
            {t('timezone_sudoers.checking')}
          </div>
        )}

        {isOk && !loading && (
          <NoticeCallout
            variant="success"
            title={t('timezone_sudoers.status_ok')}
            message={t('timezone_sudoers.status_ok_hint')}
          />
        )}

        {unreachable && !loading && (
          <NoticeCallout
            variant="warning"
            title={t('timezone_sudoers.unknown')}
            message={
              <>
                <span className="block">{t('timezone_sudoers.unknown_hint')}</span>
                <span className="block font-mono text-xs opacity-60 mt-1">{unreachable}</span>
              </>
            }
          />
        )}

        {needsFix && !loading && (
          <NoticeCallout
            variant="warning"
            title={t('timezone_sudoers.missing')}
            message={
              <>
                <span className="block">{t('timezone_sudoers.missing_hint')}</span>
                <code className="block font-mono text-xs mt-1 text-base-content/70">
                  /etc/sudoers.d/boneio-timedatectl
                </code>
                {checkResult?.error && (
                  <span className="block font-mono text-xs opacity-60 mt-1">
                    {checkResult.error}
                  </span>
                )}
              </>
            }
          />
        )}
      </div>
    </SettingsCard>
  );
}
