import React from 'react';

interface HelpLabelProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Reusable help label component that wraps text properly on mobile.
 * Replaces the pattern: <label className="label"><span className="label-text-alt ...">
 *
 * Deliberately identical to the help line FormField renders — the forms built
 * from schema widgets use this one and the hand-written settings pages use
 * FormField, and the two sit next to each other in the sidebar.
 */
const HelpLabel: React.FC<HelpLabelProps> = ({ children, className = '' }) => (
  <p className={`mt-1.5 text-xs text-base-content/55 leading-relaxed max-w-prose ${className}`.trim()}>
    {children}
  </p>
);

export default HelpLabel;
