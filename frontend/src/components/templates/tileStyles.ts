// Shared by TemplateTile and the tiles built on it. Kept out of
// TemplateTile.tsx so that file exports only a component and Fast Refresh
// can reload it in place.

/** What a state means, not what it looks like — each tone maps to one colour. */
export type Tone = 'success' | 'warning' | 'error' | 'info' | 'primary' | 'neutral';

export const TONE_ICON: Record<Tone, string> = {
  success: 'bg-success/15 text-success',
  warning: 'bg-warning/20 text-warning',
  error: 'bg-error/15 text-error',
  info: 'bg-info/15 text-info',
  primary: 'bg-primary/15 text-primary',
  neutral: 'bg-base-content/8 text-base-content/50',
};

export const DOT_TONE: Record<Tone, string> = {
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
