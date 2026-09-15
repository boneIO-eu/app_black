import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../hooks/useTranslation';
import {
  useSecurityPosture,
  type SecurityCheck,
  type Severity,
} from '../hooks/useSecurityPosture';
import { checkText as checkTextOf, fixRoute } from '../utils/securityPosture';
import DiagnosticsCard from './DiagnosticsCard';
import FrameAncestorsCard from './FrameAncestorsCard';

/** This view's own route, so a check fixed here offers no button back to it. */
const SELF_ROUTE = '/settings/security';

/**
 * What is still unlocked on this controller, and where to fix it.
 *
 * boneIO's real testers are people whose devices have been running since 1.5,
 * so the hardening work has to find them rather than wait to be found. This
 * section is the place it is all visible at once; the same data drives the
 * sidebar badge, the prompt after an update and a Home Assistant sensor.
 *
 * Every row ends in a link to the control that fixes it, or — where there
 * deliberately is no control, such as the anonymous-access opt-out — the exact
 * change to make by hand. A finding with no way to act on it is a scold.
 *
 * Checks that pass are shown too, folded away. Seeing that seven things were
 * examined is what makes "two outstanding" mean something.
 */

const SEVERITY_STYLES: Record<Severity, { badge: string; border: string; icon: string }> = {
  critical: { badge: 'badge-error', border: 'border-error/40 bg-error/5', icon: '⛔' },
  warning: { badge: 'badge-warning', border: 'border-warning/40 bg-warning/5', icon: '⚠️' },
  info: { badge: 'badge-info', border: 'border-info/40 bg-info/5', icon: 'ℹ️' },
};

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

  if (loading && !posture) {
    return (
      <div className="flex justify-center py-12">
        <span className="loading loading-ring loading-lg text-primary" />
      </div>
    );
  }

  if (error || !posture) {
    return (
      <div className="p-4 sm:p-6">
        <div className="alert alert-warning">
          <span>{t('security.unavailable')}</span>
          <button className="btn btn-sm btn-outline" onClick={() => void refresh()}>
            {t('security.retry')}
          </button>
        </div>
      </div>
    );
  }

  // Two groups, because they ask for different things. Actionable findings are
  // a problem on this device; advice applies to nearly every controller and is
  // a choice the owner makes — mixing them would make the whole list feel
  // optional.
  const failed = posture.checks.filter(c => c.state === 'failed' && c.severity !== 'info');
  const advice = posture.checks.filter(c => c.state === 'failed' && c.severity === 'info');
  const passed = posture.checks.filter(c => c.state !== 'failed');

  const renderCheck = (check: SecurityCheck) => {
    const style = SEVERITY_STYLES[check.severity];
    return (
      <div key={check.id} className={`border rounded-xl p-4 ${style.border}`}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-start gap-2 min-w-0">
            <span aria-hidden="true">{style.icon}</span>
            <div className="min-w-0">
              <h3 className="font-semibold">
                {checkText(check.id, 'title', check.title)}
              </h3>
              <p className="text-sm opacity-80 mt-1">
                {checkText(check.id, 'detail', check.detail)}
              </p>
            </div>
          </div>
          <span className={`badge ${style.badge} badge-sm shrink-0`}>
            {t(`security.severity.${check.severity}`)}
          </span>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          {fixRoute(check, SELF_ROUTE) ? (
            <button className="btn btn-sm btn-primary" onClick={() => goToFix(check)}>
              {t('security.fix')}
            </button>
          ) : null}
          <p className="text-xs opacity-70 font-mono break-all">
            {checkText(check.id, 'remedy', check.remedy)}
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold flex items-center gap-2">
          🛡️ {t('security.title')}
        </h2>
        <p className="text-sm opacity-70 mt-1 max-w-3xl">{t('security.intro')}</p>
      </div>

      {failed.length === 0 ? (
        <div className="alert alert-success">
          <span>
            {t('security.all_clear', { count: posture.checks.length })}
          </span>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold">
              {t('security.outstanding', { count: failed.length })}
            </span>
            {posture.summary.critical > 0 && (
              <span className="badge badge-error badge-sm">
                {t('security.severity_count.critical', { count: posture.summary.critical })}
              </span>
            )}
            {posture.summary.warning > 0 && (
              <span className="badge badge-warning badge-sm">
                {t('security.severity_count.warning', { count: posture.summary.warning })}
              </span>
            )}
            {/* No info badge here: those have their own block below, and
                counting them in the same line would undo the split. */}
          </div>

          {failed.map(renderCheck)}
        </div>
      )}

      {advice.length > 0 && (
        <div className="space-y-3">
          <div>
            <h3 className="font-semibold text-sm">{t('security.advice')}</h3>
            <p className="text-xs opacity-70 mt-1 max-w-3xl">{t('security.advice_intro')}</p>
          </div>
          {advice.map(renderCheck)}
        </div>
      )}

      {/* A control, not a finding: shown whether or not the check passes, so
          the restriction can be tightened as well as repaired. */}
      <FrameAncestorsCard onSaved={() => void refresh()} />

      {/* Not a security setting, but the same audience: this is the page an
          admin is on when something is wrong. */}
      <DiagnosticsCard />

      {passed.length > 0 && (
        <details className="border border-base-300 rounded-xl">
          <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium">
            {t('security.passed', { count: passed.length })}
          </summary>
          <ul className="px-4 pb-4 space-y-2">
            {passed.map(check => (
              <li key={check.id} className="flex items-start gap-2 text-sm">
                <span aria-hidden="true">{check.state === 'ok' ? '✅' : '❔'}</span>
                <div>
                  <span className="font-medium">
                    {checkText(check.id, 'title', check.title)}
                  </span>
                  <span className="opacity-70">
                    {' — '}
                    {checkText(check.id, 'ok', check.detail)}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="flex justify-end">
        <button className="btn btn-sm btn-outline" onClick={() => void refresh()}>
          {t('security.recheck')}
        </button>
      </div>
    </div>
  );
}
