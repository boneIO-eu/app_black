import { useState } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { parseDiff } from './diffRows';

const COLLAPSED_ROWS = 28;

const ROW_STYLE = {
  add: 'bg-success/12',
  del: 'bg-error/10 text-base-content/55 line-through decoration-error/40',
  ctx: '',
} as const;

const MARK_STYLE = {
  add: 'text-success border-success',
  del: 'text-error border-error',
  ctx: 'text-transparent border-transparent',
} as const;

/** What a proposal would change in its section, before and after in one column. */
export default function ProposalDiff({ diff }: { diff: string }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const { rows, added, removed } = parseDiff(diff);

  if (!rows.length) {
    return <p className="text-sm text-base-content/60">{t('proposals.no_change')}</p>;
  }
  const shown = expanded ? rows : rows.slice(0, COLLAPSED_ROWS);

  return (
    <div className="stg-inset overflow-hidden">
      <div className="flex items-center gap-3 border-b border-[var(--stg-line)] px-3 py-1.5 text-xs">
        <span className="font-semibold text-success">+{added}</span>
        <span className="font-semibold text-error">−{removed}</span>
        <span className="text-base-content/50">{t('proposals.diff_lines')}</span>
      </div>
      <div className="overflow-x-auto py-1 font-mono text-xs leading-5">
        {shown.map((row, i) =>
          row.kind === 'gap' ? (
            <div key={i} className="my-1 px-3 text-base-content/35 select-none" aria-label={t('proposals.diff_gap')}>
              ⋯
            </div>
          ) : (
            <div key={i} className={`flex min-w-max ${ROW_STYLE[row.kind]}`}>
              <span className="w-10 shrink-0 select-none pr-2 text-right text-base-content/30 tabular-nums">
                {row.line ?? ''}
              </span>
              <span className={`w-5 shrink-0 select-none border-l-2 text-center font-bold ${MARK_STYLE[row.kind]}`}>
                {row.kind === 'add' ? '+' : row.kind === 'del' ? '−' : ' '}
              </span>
              <span className="whitespace-pre pr-4">{row.text || ' '}</span>
            </div>
          ),
        )}
      </div>
      {rows.length > COLLAPSED_ROWS && (
        <button
          type="button"
          className="w-full border-t border-[var(--stg-line)] py-1.5 text-xs text-primary hover:bg-[var(--stg-tint)]"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? t('proposals.diff_less') : t('proposals.diff_more', { count: rows.length - COLLAPSED_ROWS })}
        </button>
      )}
    </div>
  );
}
