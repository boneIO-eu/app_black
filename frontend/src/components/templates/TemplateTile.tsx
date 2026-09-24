import React from 'react';
import clsx from 'clsx';

import { TONE_ICON, DOT_TONE, type Tone } from './tileStyles';

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
        <span className={clsx('flex items-center justify-center w-10 h-10 rounded-full shrink-0', TONE_ICON[tone])}>
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
