import React from 'react';
import { cn } from '@/lib/utils';

export interface CodeBlockProps {
  /** Optional caption above the block */
  label?: React.ReactNode;
  /** The text. Objects are stringified as pretty JSON. */
  children: React.ReactNode;
  /** Colour the block by outcome instead of leaving it neutral */
  tone?: 'neutral' | 'success' | 'error';
  /** Cap the height and scroll past it */
  maxHeight?: string;
  className?: string;
}

/**
 * Terminal-ish output inside a card: command results, diagnostics, sudoers
 * file contents.
 */
export const CodeBlock: React.FC<CodeBlockProps> = ({
  label,
  children,
  tone = 'neutral',
  maxHeight,
  className = '',
}) => {
  const toneClass = {
    neutral: 'stg-inset-strong',
    success: 'bg-success/8 border-success/25',
    error: 'bg-error/8 border-error/25',
  }[tone];

  return (
    <div className={cn('min-w-0', className)}>
      {label && (
        <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-base-content/50 mb-1.5">
          {label}
        </div>
      )}
      <pre
        className={cn(
          'stg-inset overflow-auto p-3 text-xs font-mono leading-relaxed text-base-content/80 whitespace-pre-wrap break-words',
          toneClass,
        )}
        style={maxHeight ? { maxHeight } : undefined}
      >
        {children}
      </pre>
    </div>
  );
};

export default CodeBlock;
