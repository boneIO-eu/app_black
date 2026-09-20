import React, { useState } from 'react';
import { FaChevronDown, FaChevronRight } from 'react-icons/fa';

export interface MoreOptionsProps {
  /** The row's label, e.g. "More options". */
  label: string;
  /** What is inside, named, so it can be found without opening it. */
  summary?: string;
  /** Open on first render — for an entity that already sets something inside. */
  defaultOpen?: boolean;
  children: React.ReactNode;
}

/**
 * The fields a form does not need to ask for, behind one row.
 *
 * Every optional field shown up front competes with the required ones, and the
 * optional ones are usually the tall ones — a nine-area picker outweighed the
 * name and the id it sat next to. Naming what is inside matters: a bare "More"
 * has to be opened to be ruled out.
 */
export const MoreOptions: React.FC<MoreOptionsProps> = ({
  label,
  summary,
  defaultOpen = false,
  children,
}) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-t border-base-content/8 pt-3">
      <button
        type="button"
        className="flex items-center gap-2 text-left w-full group"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {open ? <FaChevronDown className="w-2.5 h-2.5 opacity-50" />
              : <FaChevronRight className="w-2.5 h-2.5 opacity-50" />}
        <span className="text-[13px] font-medium text-base-content/85 group-hover:text-base-content">
          {label}
        </span>
        {summary && !open && (
          <span className="text-xs text-base-content/50 truncate">— {summary}</span>
        )}
      </button>
      {open && <div className="mt-3 space-y-3">{children}</div>}
    </div>
  );
};

export default MoreOptions;
