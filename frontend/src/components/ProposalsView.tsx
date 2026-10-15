import { useCallback, useEffect, useState } from 'react';
import type { AxiosError } from 'axios';
import { FaRobot } from 'react-icons/fa';
import axios from '@/api/axios';
import { useAuth } from '../hooks/useAuth';
import { useTranslation } from '../hooks/useTranslation';
import { SettingsPage, SettingsCard, NoticeCallout } from './UISettings/ui';
import { LoadingState } from '@/components/ui/LoadingState';
import type { StandaloneSectionProps } from './UISettings/constants/standaloneSections';

interface Proposal {
  id: string;
  section: string;
  rationale: string;
  author: string;
  created_at: string;
  diff: string;
  stale: boolean;
  restart_required: boolean;
}

type ApiError = AxiosError<{ detail?: string | { message?: string; errors?: string[] } }>;

function errorMessage(err: unknown, fallback: string): string {
  const detail = (err as ApiError)?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.errors?.length) return detail.errors.join('\n');
  return detail?.message || fallback;
}

function lineClass(line: string): string {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-base-content/50';
  if (line.startsWith('+')) return 'bg-success/15 text-success';
  if (line.startsWith('-')) return 'bg-error/15 text-error';
  if (line.startsWith('@@')) return 'text-info';
  return '';
}

/**
 * Config changes an API key in the "propose" scope filed instead of saving.
 *
 * The server has already checked each one as a save would, and approving goes
 * through the save route, so this page only shows what would change and lets
 * a person decide. A proposal made against a section that changed since is
 * marked, and approving it asks a second time: it would undo those changes.
 */
export default function ProposalsView({ onRestartRequired }: StandaloneSectionProps) {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmStale, setConfirmStale] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/proposals');
      setProposals(data.proposals ?? []);
      setError(null);
    } catch (err: unknown) {
      setError(errorMessage(err, t('proposals.load_failed')));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (isAdmin) void load();
  }, [isAdmin, load]);

  const sectionName = (section: string) => t(`sections.${section}`, { defaultValue: section });

  const approve = async (p: Proposal, force = false) => {
    setBusy(p.id);
    setError(null);
    setNotice(null);
    try {
      const { data } = await axios.post(`/api/proposals/${encodeURIComponent(p.id)}/approve`, { force });
      setConfirmStale(null);
      setNotice(t('proposals.approved', { section: sectionName(p.section) }));
      if (data?.restart_required) onRestartRequired?.();
      await load();
    } catch (err: unknown) {
      if ((err as ApiError)?.response?.status === 409) {
        setConfirmStale(p.id);
        await load();
      } else {
        setError(errorMessage(err, t('proposals.approve_failed')));
      }
    } finally {
      setBusy(null);
    }
  };

  const reject = async (p: Proposal) => {
    setBusy(p.id);
    setError(null);
    setNotice(null);
    try {
      await axios.delete(`/api/proposals/${encodeURIComponent(p.id)}`);
      setNotice(t('proposals.rejected', { section: sectionName(p.section) }));
      await load();
    } catch (err: unknown) {
      setError(errorMessage(err, t('proposals.reject_failed')));
    } finally {
      setBusy(null);
    }
  };

  if (!isAdmin) {
    return (
      <SettingsPage width="wide">
        <NoticeCallout variant="warning" message={t('accounts.admin_only')} />
      </SettingsPage>
    );
  }

  return (
    <SettingsPage width="wide">
      {error && <NoticeCallout variant="error" message={error} />}
      {notice && <NoticeCallout variant="success" message={notice} />}
      {isLoading ? (
        <LoadingState className="py-6" />
      ) : proposals.length === 0 ? (
        <SettingsCard icon={<FaRobot />} title={t('proposals.title')} description={t('proposals.intro')}>
          <p className="text-sm text-base-content/60">{t('proposals.empty')}</p>
        </SettingsCard>
      ) : (
        proposals.map((p) => (
          <SettingsCard
            key={p.id}
            icon={<FaRobot />}
            title={t('proposals.card_title', { section: sectionName(p.section) })}
            description={t('proposals.meta', { author: p.author, date: new Date(p.created_at).toLocaleString() })}
          >
            {p.rationale && <p className="text-sm whitespace-pre-wrap">{p.rationale}</p>}
            {p.stale && <NoticeCallout variant="warning" message={t('proposals.stale')} />}
            {p.restart_required && <NoticeCallout variant="info" message={t('proposals.restart')} />}
            <pre className="stg-inset overflow-x-auto p-2 text-xs leading-5">
              {p.diff
                ? p.diff.split('\n').map((line, i) => (
                    <div key={i} className={lineClass(line)}>{line || ' '}</div>
                  ))
                : t('proposals.no_change')}
            </pre>
            <div className="flex flex-wrap justify-end gap-2">
              <button className="btn btn-ghost btn-sm" disabled={busy === p.id} onClick={() => reject(p)}>
                {t('proposals.reject')}
              </button>
              {confirmStale === p.id ? (
                <button className="btn btn-warning btn-sm" disabled={busy === p.id} onClick={() => approve(p, true)}>
                  {t('proposals.approve_anyway')}
                </button>
              ) : (
                <button className="btn btn-primary btn-sm" disabled={busy === p.id} onClick={() => approve(p)}>
                  {busy === p.id && <span className="loading loading-spinner loading-xs" />}
                  {t('proposals.approve')}
                </button>
              )}
            </div>
          </SettingsCard>
        ))
      )}
    </SettingsPage>
  );
}
