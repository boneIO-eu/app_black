import React from 'react';

interface HelpLabelProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Reusable help label component that wraps text properly on mobile.
 * Replaces the pattern: <label className="label"><span className="label-text-alt ...">
 */
const HelpLabel: React.FC<HelpLabelProps> = ({ children, className = '' }) => (
  <div className={`pt-1 pb-0.5 ${className}`.trim()}>
    <span className="text-xs text-base-content/60 block max-w-prose">
      {children}
    </span>
  </div>
);

export default HelpLabel;
