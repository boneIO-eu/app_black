import React from 'react';
import clsx from 'clsx';

/** What a state means, not what it looks like — each tone maps to one colour. */
export type Tone = 'success' | 'warning' | 'error' | 'info' | 'primary' | 'neutral';

const ICON_TONE: Record<Tone, string> = {
  success: 'bg-success/15 text-success',
  warning: 'bg-warning/20 text-warning',
  error: 'bg-error/15 text-error',
  info: 'bg-info/15 text-info',
  primary: 'bg-primary/15 text-primary',
  neutral: 'bg-base-content/8 text-base-content/50',
};

const DOT_TONE: Record<Tone, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-error',
  info: 'bg-info',
  primary: 'bg-primary',
  neutral: 'bg-base-content/30',
};

/** 44px, the smallest target a thumb hits reliably. Shared by every tile's controls. */
export const TILE_BUTTON = 'btn h-11 min-h-11 text-sm font-medium';

/**
 * A button in a row of three: icon over its label, 56px tall. Side by side
 * at tile width the labels did not fit and were cut to "Ot…"; stacked they
 * keep their words at any tile width the grid allows.
 */
export const TILE_BUTTON_STACKED = 'btn h-14 min-h-14 flex-col gap-1 px-1 font-medium';

/**
 * One tile for every template type, so a thermostat, an alarm and a gate
 * read as the same kind of thing: a coloured icon, the name, the state in
 * words, then whatever the tile shows, then its controls along the bottom.
 *
 * The state is a word with a dot, not a coloured badge: the word carries the
 * meaning for anyone who does not tell the colours apart, and body-weight
 * text stays readable where amber or green text on white would not.
 */
export function TemplateTile({
  icon: Icon,
  tone,
  name,
  state,
  action,
  children,
  footer,
}: {
  icon: React.ComponentType<{ className?: string }>;
  tone: Tone;
  name: string;
  state: React.ReactNode;
  /** A small control beside the name, e.g. a power button. */
  action?: React.ReactNode;
  children?: React.ReactNode;
  /** The tile's controls; pinned to the bottom so a row of tiles lines up. */
  footer?: React.ReactNode;
}) {
  return (
    <div className="stg-inset p-4 h-full flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className={clsx('flex items-center justify-center w-10 h-10 rounded-full shrink-0', ICON_TONE[tone])}>
          <Icon className="w-5 h-5" />
        </span>
        <div className="flex flex-col min-w-0 flex-1">
          <span className="text-base font-medium truncate">{name}</span>
          <span className="flex items-center gap-1.5 text-sm text-base-content/70">
            <span className={clsx('w-2 h-2 rounded-full shrink-0', DOT_TONE[tone])} aria-hidden="true" />
            <span className="truncate">{state}</span>
          </span>
        </div>
        {action}
      </div>
      {children}
      {footer && <div className="mt-auto">{footer}</div>}
    </div>
  );
}
