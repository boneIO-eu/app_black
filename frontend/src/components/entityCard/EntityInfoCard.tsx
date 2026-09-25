/**
 * EntityInfoCard — what a long press on any tile opens.
 *
 * Modelled on Home Assistant's more-info dialog: the entity's live state and
 * its controls first, then what it has been doing, with everything that
 * leads elsewhere (quick action, MQTT topics, settings) folded behind a ⋮
 * beside the close button. Those used to be the whole dialog — three big
 * buttons and no way to see the thing they were about.
 *
 * It is a Dialog, so on a phone it arrives as a bottom sheet.
 *
 * The card holds no entity of its own. Each view passes the one it has just
 * rendered, so the card is as live as the tile behind it.
 */
import React, { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { FaEllipsisV, FaTimes } from 'react-icons/fa';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { useTranslation } from '@/hooks/useTranslation';
import { useEntityHistory, useNow } from '@/hooks/useEntityHistory';
import type { HistoryEntry } from '@/utils/entityHistory';
import { formatAgo } from './format';

/** One entry of the ⋮ menu. */
export interface EntityCardMenuItem {
  key: string;
  label: string;
  icon: React.ReactNode;
  onSelect: () => void;
}

interface EntityInfoCardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Coloured icon beside the name. */
  icon: React.ReactNode;
  title: string;
  /** Id, area, device — whatever tells two same-named entities apart. */
  subtitle?: React.ReactNode;
  /** Behind ⋮. Empty → no ⋮ at all, rather than a menu with nothing in it. */
  menu?: EntityCardMenuItem[];
  /** Live state and controls. */
  children: React.ReactNode;
  /** Buffer key for the event list; omit for entities that show a graph instead. */
  historyKey?: string | null;
  /** Turns a recorded value into words, e.g. ON → "Włączone". */
  formatValue?: (entry: HistoryEntry) => React.ReactNode;
  /** Desktop width; a tile with a lot on it (irrigation) needs more. */
  maxWidthClass?: string;
}

export default function EntityInfoCard({
  open,
  onOpenChange,
  icon,
  title,
  subtitle,
  menu = [],
  children,
  historyKey,
  formatValue,
  maxWidthClass = 'sm:max-w-md',
}: EntityInfoCardProps) {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Every way out of the card goes through here, so a card reopened on
  // another entity never comes back with the menu out.
  const handleOpenChange = (next: boolean) => {
    if (!next) setMenuOpen(false);
    onOpenChange(next);
  };

  // Close the menu on a click anywhere else in the card.
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: PointerEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('pointerdown', onDown, true);
    return () => document.removeEventListener('pointerdown', onDown, true);
  }, [menuOpen]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={false}
        maxWidthClass={maxWidthClass}
        className="gap-0 px-0 pb-0 pt-3 sm:p-0 overflow-y-auto"
      >
        {/* Header: icon, name, then ⋮ and ✕ on one line, so the menu sits
            where HA users look for it. */}
        <div className="flex items-start gap-3 px-5 pt-1 sm:pt-5 pb-3">
          <span className="flex items-center justify-center w-10 h-10 rounded-full bg-base-200 shrink-0 text-xl">
            {icon}
          </span>
          <div className="flex flex-col min-w-0 flex-1 pt-0.5">
            <DialogTitle className="text-lg leading-tight truncate">{title}</DialogTitle>
            {subtitle && <div className="text-xs text-base-content/50 truncate mt-0.5">{subtitle}</div>}
          </div>
          <div className="flex items-center gap-1 shrink-0 -mr-2">
            {menu.length > 0 && (
              <div className="relative" ref={menuRef}>
                <button
                  type="button"
                  className={clsx('btn btn-ghost btn-sm btn-circle', menuOpen && 'btn-active')}
                  onClick={() => setMenuOpen(o => !o)}
                  aria-label={t('entity_card.more')}
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  title={t('entity_card.more')}
                >
                  <FaEllipsisV className="w-4 h-4" />
                </button>
                {menuOpen && (
                  <ul
                    role="menu"
                    className="absolute right-0 top-full mt-1 z-10 menu p-1.5 w-60 bg-base-100 border border-base-300 rounded-box shadow-lg"
                  >
                    {menu.map(item => (
                      <li key={item.key} role="none">
                        <button
                          type="button"
                          role="menuitem"
                          className="gap-3"
                          onClick={() => {
                            setMenuOpen(false);
                            item.onSelect();
                          }}
                        >
                          <span className="w-4 h-4 flex items-center justify-center text-base-content/60">{item.icon}</span>
                          {item.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-circle"
              onClick={() => handleOpenChange(false)}
              aria-label={t('common.close')}
              title={t('common.close')}
            >
              <FaTimes className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="px-5 pb-5 flex flex-col gap-5">
          {children}
          {historyKey && (
            <EntityHistoryList historyKey={historyKey} formatValue={formatValue} active={open} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function EntityHistoryList({
  historyKey,
  formatValue,
  active,
}: {
  historyKey: string;
  formatValue?: (entry: HistoryEntry) => React.ReactNode;
  active: boolean;
}) {
  const { t } = useTranslation();
  const entries = useEntityHistory(historyKey);
  const now = useNow(active);

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-base-content/50">
          {t('entity_card.history')}
        </h3>
        <span className="text-[11px] text-base-content/40">{t('entity_card.history_scope')}</span>
      </div>
      {/* Room for ten rows from the start, empty or not: a card that grew
          by a row with every click jumped under the finger. Past ten the
          list scrolls inside it. 329px = ten 33px rows less the first one's
          border. */}
      <div className="h-[329px] overflow-y-auto overscroll-contain -mr-2 pr-2">
        {entries.length === 0 ? (
          <p className="text-sm text-base-content/50 py-2">{t('entity_card.history_empty')}</p>
        ) : (
          <ol className="flex flex-col">
            {entries.map((entry, i) => (
              <li
                key={`${entry.at}-${i}`}
                className={clsx(
                  'flex items-center gap-3 py-1.5 text-sm border-base-content/8',
                  i > 0 && 'border-t',
                )}
              >
                <span className={clsx('w-2 h-2 rounded-full shrink-0', i === 0 ? 'bg-primary' : 'bg-base-content/20')} />
                <span className="flex-1 min-w-0 truncate">
                  {formatValue ? formatValue(entry) : entry.value}
                  {entry.detail && <span className="text-base-content/50"> · {entry.detail}</span>}
                </span>
                <span className="text-xs text-base-content/50 whitespace-nowrap tabular-nums" title={new Date(entry.at).toLocaleString()}>
                  {formatAgo(entry.at, now, t)}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
