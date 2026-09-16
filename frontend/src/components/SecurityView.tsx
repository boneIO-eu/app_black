import { useNavigate } from 'react-router-dom';
import { FaRedo } from 'react-icons/fa';
import { useTranslation } from '../hooks/useTranslation';
import {
  useSecurityPosture,
  type SecurityCheck,
} from '../hooks/useSecurityPosture';
import { checkText as checkTextOf, fixRoute } from '../utils/securityPosture';
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
              onFix={fixRoute(check, SELF_ROUTE) ? () => goToFix(check) : undefined}
              fixLabel={t('security.fix')}
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
              onFix={fixRoute(check, SELF_ROUTE) ? () => goToFix(check) : undefined}
              fixLabel={t('security.fix')}
            />
          ))}
        </div>
      )}

      {/* Frame ancestors card */}
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
