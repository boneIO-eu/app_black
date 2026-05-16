/**
 * "Add Output" dropdown button with board/expander capacity counters.
 *
 * Replaces the inline 40-line IIFE that lived in ArrayTableWidget. Rendered
 * only when an expander is configured (i.e. there are EX_* entries in `value`).
 * For board-only setups, ArrayTableWidget keeps its plain `<button>` path.
 */
import React from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

import { useOutputCapacity } from '../hooks/useOutputCapacity';
import type { OutputEntity, OutputKind } from '../types/output';

export interface OutputAddButtonProps {
  outputs: OutputEntity[];
  deviceType: string | undefined;
  onAdd: (kind: OutputKind) => void;
}

const OutputAddButton: React.FC<OutputAddButtonProps> = ({ outputs, deviceType, onAdd }) => {
  const { t } = useTranslation();
  const c = useOutputCapacity(outputs, deviceType);

  return (
    <div className="dropdown dropdown-end">
      <div tabIndex={0} className={`btn btn-primary btn-sm ${c.allFull ? 'btn-disabled' : ''}`}>
        <FaPlus className="mr-1" />
        {t('settings.add_new')}
        <svg className="w-3 h-3 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>
      <ul tabIndex={0} className="dropdown-content menu menu-sm shadow bg-base-100 rounded-box w-56 z-50 border border-base-300">
        <li>
          <button
            onClick={() => !c.boardFull && onAdd('board')}
            className={c.boardFull ? 'opacity-40 cursor-not-allowed' : ''}
            disabled={c.boardFull}
          >
            <span className="flex-1">{t('outputs.add_board_output')}</span>
            <span className={`badge badge-sm ${c.boardFull ? 'badge-error' : 'badge-ghost'}`}>
              {c.boardUsed}/{c.boardCapacity}
            </span>
          </button>
        </li>
        <li>
          <button
            onClick={() => !c.expanderFull && onAdd('expander')}
            className={c.expanderFull ? 'opacity-40 cursor-not-allowed' : ''}
            disabled={c.expanderFull}
          >
            <span className="flex-1">{t('outputs.add_expander_output')}</span>
            <span className={`badge badge-sm ${c.expanderFull ? 'badge-error' : 'badge-ghost'}`}>
              {c.expanderUsed}/{c.expanderCapacity}
            </span>
          </button>
        </li>
      </ul>
    </div>
  );
};

export default OutputAddButton;
