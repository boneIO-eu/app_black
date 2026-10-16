import { useCallback, useEffect, useState, FormEvent } from 'react';
import type { AxiosError } from 'axios';
import { FaKey, FaPaste, FaRobot, FaUser } from 'react-icons/fa';
import axios from '@/api/axios';
import { useAuth } from '../hooks/useAuth';
import { useTranslation } from '../hooks/useTranslation';
import { PROPOSALS_CHANGED } from '../hooks/usePendingProposals';
import { SettingsPage, SettingsCard, NoticeCallout, EmptyState, FormActions } from './UISettings/ui';
import { LoadingState } from '@/components/ui/LoadingState';
import type { StandaloneSectionProps } from './UISettings/constants/standaloneSections';
import { parsePastedSection } from './pastedSection';
import ProposalDiff from './ProposalDiff';

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

/** "key:Claude (pawel)" for an API key, a username for something pasted. */
function parseAuthor(author: string): { key: string; owner: string } | { user: string } {
  const match = author.match(/^key:(.+) \((.+)\)$/);
  return match ? { key: match[1], owner: match[2] } : { user: author };
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['day', 86_400], ['hour', 3_600], ['minute', 60],
];

function ago(iso: string, language: string, justNow: string): string {
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  const format = new Intl.RelativeTimeFormat(language, { numeric: 'auto' });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
  }
  return justNow;
}

/**
 * A section pasted from an AI chat - the way in for a key that may only read.
 *
 * It is filed like an agent's proposal, so it is checked as a save would
 * check it and lands in the list below with its diff, to approve or reject.
 */
function PasteCard({ onFiled, startOpen }: { onFiled: (section: string) => Promise<void>; startOpen: boolean }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(startOpen);
  const [text, setText] = useState('');
  const [rationale, setRationale] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const pasted = parsePastedSection(text);
    if ('error' in pasted) {
      setError(t(`proposals.paste_error_${pasted.error}`));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await axios.post(`/api/config/${encodeURIComponent(pasted.section)}/proposals`, {
        data: pasted.data,
        rationale: rationale.trim() || t('proposals.paste_default_rationale'),
      });
      setText('');
      setRationale('');
      await onFiled(pasted.section);
    } catch (err: unknown) {
      setError(errorMessage(err, t('proposals.paste_failed')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <SettingsCard
        icon={<FaPaste />}
        title={t('proposals.paste_title')}
        description={t('proposals.paste_intro')}
        collapsible
        open={open}
        onOpenChange={setOpen}
      >
        {error && <NoticeCallout variant="error" message={error} />}
        <textarea
          className="textarea textarea-bordered w-full font-mono text-xs"
          rows={7}
          placeholder={'output:\n  - name: Lampa\n    boneio_output: OUT_01\n    output_type: light'}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <input
          type="text"
          className="input input-bordered input-sm w-full"
          placeholder={t('proposals.paste_rationale')}
          maxLength={2000}
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
        />
        <div className="flex justify-end">
          <button type="submit" className="btn btn-primary btn-sm gap-2" disabled={busy || !text.trim()}>
            {busy && <span className="loading loading-spinner loading-xs" />}
            {t('proposals.paste_submit')}
          </button>
        </div>
      </SettingsCard>
    </form>
  );
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
  const { t, language } = useTranslation();
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
      window.dispatchEvent(new Event(PROPOSALS_CHANGED));
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
        <EmptyState icon={<FaRobot />} title={t('proposals.empty')} description={t('proposals.empty_hint')} />
      ) : (
        proposals.map((p) => {
          const author = parseAuthor(p.author);
          return (
            <SettingsCard
              key={p.id}
              icon={<FaRobot />}
              title={sectionName(p.section)}
              description={
                <span className="inline-flex flex-wrap items-center gap-x-1.5">
                  {'key' in author ? (
                    <>
                      <FaKey className="text-[11px] opacity-60" aria-hidden="true" />
                      {t('proposals.by_key', { key: author.key, owner: author.owner })}
                    </>
                  ) : (
                    <>
                      <FaUser className="text-[11px] opacity-60" aria-hidden="true" />
                      {t('proposals.by_user', { user: author.user })}
                    </>
                  )}
                  <time dateTime={p.created_at} title={new Date(p.created_at).toLocaleString(language)}>
                    {ago(p.created_at, language, t('proposals.just_now'))}
                  </time>
                </span>
              }
              action={
                p.restart_required ? (
                  <span className="badge badge-warning badge-sm whitespace-nowrap" title={t('proposals.restart')}>
                    {t('proposals.restart_badge')}
                  </span>
                ) : undefined
              }
              footer={
                <FormActions>
                  <button className="btn btn-ghost btn-sm" disabled={busy === p.id} onClick={() => reject(p)}>
                    {t('proposals.reject')}
                  </button>
                  {confirmStale === p.id ? (
                    <button className="btn btn-warning btn-sm" disabled={busy === p.id} onClick={() => approve(p, true)}>
                      {t('proposals.approve_anyway')}
                    </button>
                  ) : (
                    <button className="btn btn-primary btn-sm gap-2" disabled={busy === p.id} onClick={() => approve(p)}>
                      {busy === p.id && <span className="loading loading-spinner loading-xs" />}
                      {t('proposals.approve')}
                    </button>
                  )}
                </FormActions>
              }
            >
              {p.rationale && (
                <blockquote className="border-l-2 border-primary/60 pl-3 text-sm leading-relaxed whitespace-pre-wrap text-base-content/85">
                  {p.rationale}
                </blockquote>
              )}
              {p.stale && <NoticeCallout variant="warning" message={t('proposals.stale')} />}
              <ProposalDiff diff={p.diff} />
            </SettingsCard>
          );
        })
      )}
      <PasteCard
        key={isLoading ? 'loading' : 'ready'}
        startOpen={!isLoading && proposals.length === 0}
        onFiled={async (section) => {
          setNotice(t('proposals.pasted', { section: sectionName(section) }));
          await load();
        }}
      />
    </SettingsPage>
  );
}
