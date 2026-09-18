import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaRedo } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';
import {
  useSecurityPosture,
  type SecurityCheck,
} from '../hooks/useSecurityPosture';
import { invalidateSecurityPosture } from '../api/securityPostureCache';
import { checkText as checkTextOf, fixRoute } from '../utils/securityPosture';
import CertificateCard from './CertificateCard';
import FrameAncestorsCard from './FrameAncestorsCard';
import { SettingsPage, SecurityFindingCard, NoticeCallout } from './UISettings/ui';

/** This view's own route, so a check fixed here offers no button back to it. */
const SELF_ROUTE = '/settings/security';

export default function SecurityView() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { posture, loading, error, refresh } = useSecurityPosture();

  const checkText = (id: string, field: string, fallback: string): string =>
    checkTextOf(t, id, field, fallback);

  /** Send the admin to whatever fixes this check. */
  const goToFix = (check: SecurityCheck) => {
    const route = fixRoute(check, SELF_ROUTE);
    if (route) navigate(route);
  };

  const [removingLegacyAuth, setRemovingLegacyAuth] = useState(false);

  /**
   * Take the pre-1.6 web.auth block out of config.yaml.
   *
   * The one check that is fixed here rather than somewhere else, so it gets an
   * action instead of a route. Confirmed first because it edits a file the
   * owner may maintain by hand — the confirmation says what is kept, what is
   * not affected, and the one thing the device cannot do for them: change that
   * password wherever else they used it.
   */
  const removeLegacyAuth = async () => {
    if (!window.confirm(t('security.remove_legacy_auth_confirm'))) return;
    setRemovingLegacyAuth(true);
    try {
      const { data } = await axios.delete<{ removed: boolean; backup: string | null }>(
        '/api/security/legacy-auth',
      );
      window.alert(
        data.removed
          ? t('security.remove_legacy_auth_done', { backup: data.backup ?? '' })
          : t('security.remove_legacy_auth_absent'),
      );
      invalidateSecurityPosture();
      await refresh();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err as Error).message;
      window.alert(t('security.remove_legacy_auth_failed', { error: detail }));
    } finally {
      setRemovingLegacyAuth(false);
    }
  };

  const [movingBehindProxy, setMovingBehindProxy] = useState(false);

  /**
   * Take the panel off the local network, leaving the encrypted proxy.
   *
   * The backend refuses this unless the proxy is demonstrably serving the
   * panel already, so the failure people would otherwise discover — a
   * controller answering on no port at all — arrives here as a message
   * instead.
   */
  const moveBehindProxy = async () => {
    if (!window.confirm(t('security.move_behind_proxy_confirm'))) return;
    setMovingBehindProxy(true);
    try {
      const { data: config } = await axios.get('/api/config');
      const web = (config?.web ?? {}) as Record<string, unknown>;
      await axios.put('/api/config/web', { ...web, expose: 'proxy' });
      window.alert(t('security.move_behind_proxy_done'));
      invalidateSecurityPosture();
      await refresh();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err as Error).message;
      window.alert(t('security.move_behind_proxy_failed', { error: detail }));
    } finally {
      setMovingBehindProxy(false);
    }
  };

  /** The action a card offers, which is usually a route and occasionally not. */
  const fixActionFor = (check: SecurityCheck) => {
    if (check.id === 'web_exposed_in_clear') {
      return {
        onFix: movingBehindProxy ? undefined : () => void moveBehindProxy(),
        fixLabel: t('security.move_behind_proxy'),
      };
    }
    if (check.id === 'legacy_web_auth') {
      return {
        onFix: removingLegacyAuth ? undefined : () => void removeLegacyAuth(),
        fixLabel: t('security.remove_legacy_auth'),
      };
    }
    return fixRoute(check, SELF_ROUTE)
      ? { onFix: () => goToFix(check), fixLabel: t('security.fix') }
      : {};
  };

  if (loading && !posture) {
    return (
      <SettingsPage width="wide">
        <div className="flex justify-center py-12">
          <span className="loading loading-ring loading-lg text-primary" />
        </div>
      </SettingsPage>
    );
  }

  if (error || !posture) {
    return (
      <SettingsPage width="wide">
        <NoticeCallout
          variant="warning"
          message={t('security.unavailable')}
          action={
            <button className="btn btn-sm btn-outline" onClick={() => void refresh()}>
              {t('security.retry')}
            </button>
          }
        />
      </SettingsPage>
    );
  }

  const failed = posture.checks.filter(c => c.state === 'failed' && c.severity !== 'info');
  const advice = posture.checks.filter(c => c.state === 'failed' && c.severity === 'info');
  const passed = posture.checks.filter(c => c.state !== 'failed');

  return (
    <SettingsPage width="wide">
      {/* Top summary and refresh toolbar */}
      <div className="stg-card flex flex-wrap items-center justify-between gap-3 p-3.5">
        <div className="flex items-center gap-2 flex-wrap text-sm">
          {failed.length === 0 ? (
            <span className="font-semibold text-success flex items-center gap-1.5">
              <span>✅</span>
              {t('security.all_clear', { count: posture.checks.length })}
            </span>
          ) : (
            <>
              <span className="font-semibold text-base-content">
                {t('security.outstanding', { count: failed.length })}
              </span>
              {posture.summary.critical > 0 && (
                <span className="badge badge-error badge-sm font-semibold">
                  {t('security.severity_count.critical', { count: posture.summary.critical })}
                </span>
              )}
              {posture.summary.warning > 0 && (
                <span className="badge badge-warning badge-sm font-semibold">
                  {t('security.severity_count.warning', { count: posture.summary.warning })}
                </span>
              )}
            </>
          )}
        </div>

        <button
          className="btn btn-sm btn-ghost gap-2 text-base-content/70 hover:text-base-content ml-auto"
          onClick={() => void refresh()}
        >
          <FaRedo className="text-xs" />
          {t('security.recheck')}
        </button>
      </div>

      {/* Actionable findings */}
      {failed.length > 0 && (
        <div className="space-y-3">
          {failed.map(check => (
            <SecurityFindingCard
              key={check.id}
              severity={check.severity}
              title={checkText(check.id, 'title', check.title)}
              detail={checkText(check.id, 'detail', check.detail)}
              remedy={checkText(check.id, 'remedy', check.remedy)}
              severityLabel={t(`security.severity.${check.severity}`)}
              {...fixActionFor(check)}
            />
          ))}
        </div>
      )}

      {/* Advice findings */}
      {advice.length > 0 && (
        <div className="space-y-3">
          <div className="px-1">
            <h3 className="font-semibold text-sm text-base-content">{t('security.advice')}</h3>
            <p className="text-xs text-base-content/60 mt-0.5 max-w-3xl">{t('security.advice_intro')}</p>
          </div>
          {advice.map(check => (
            <SecurityFindingCard
              key={check.id}
              severity={check.severity}
              title={checkText(check.id, 'title', check.title)}
              detail={checkText(check.id, 'detail', check.detail)}
              remedy={checkText(check.id, 'remedy', check.remedy)}
              severityLabel={t(`security.severity.${check.severity}`)}
              {...fixActionFor(check)}
            />
          ))}
        </div>
      )}

      {/* Frame ancestors card */}
      <CertificateCard />

      <FrameAncestorsCard onSaved={() => void refresh()} />

      {/* Passed checks folded away */}
      {passed.length > 0 && (
        <div className="stg-card collapse collapse-arrow">
          <input type="checkbox" />
          <div className="collapse-title text-sm font-semibold flex items-center gap-2">
            <span>✅</span>
            <span>{t('security.passed', { count: passed.length })}</span>
          </div>
          <div className="collapse-content">
            <ul className="space-y-2 pt-2 border-t border-base-content/8">
              {passed.map(check => (
                <li key={check.id} className="flex items-start gap-2.5 text-sm">
                  <span className="text-success mt-0.5 text-xs">●</span>
                  <div>
                    <span className="font-medium text-base-content">
                      {checkText(check.id, 'title', check.title)}
                    </span>
                    <span className="text-base-content/60">
                      {' — '}
                      {checkText(check.id, 'ok', check.detail)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </SettingsPage>
  );
}
