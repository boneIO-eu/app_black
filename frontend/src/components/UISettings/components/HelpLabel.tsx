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
  <label className={`label whitespace-normal ${className}`.trim()}>
    <span className="label-text-alt text-base-content/60 wrap-break-word">
      {children}
    </span>
  </label>
);

export default HelpLabel;
