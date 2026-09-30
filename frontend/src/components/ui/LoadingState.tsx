import { cn } from '@/lib/utils';
import { useTranslation } from '@/hooks/useTranslation';

interface LoadingStateProps {
  /** Padding around it, as the place it stands in needs. */
  className?: string;
  /** The ring for a whole page, the spinner inside a card. */
  variant?: 'page' | 'card';
}

/**
 * A spinner with the word under it.
 *
 * On the controller a section can take a few seconds to answer; a bare
 * spinner that long reads as something stuck, "Loading…" reads as waiting.
 */
export function LoadingState({ className, variant = 'card' }: LoadingStateProps) {
  const { t } = useTranslation();
  return (
    <div role="status" className={cn('flex flex-col items-center gap-2', className)}>
      <span
        className={cn(
          'loading text-primary',
          variant === 'page' ? 'loading-ring loading-lg' : 'loading-spinner loading-md',
        )}
      />
      <span className="text-sm text-base-content/60">{t('common.loading')}</span>
    </div>
  );
}

export default LoadingState;
