import { useTranslation } from '@/hooks/useTranslation';
import { FaDoorOpen, FaDoorClosed, FaArrowUp, FaArrowDown, FaStop } from 'react-icons/fa';
import clsx from 'clsx';
import type { GateState } from './types';
import { TemplateTile } from './TemplateTile';
import { TILE_BUTTON_STACKED, type Tone } from './tileStyles';

const TONE: Record<string, Tone> = {
  open: 'warning',
  closed: 'success',
  opening: 'info',
  closing: 'info',
};

export default function GateCard({
  data,
  onCommand,
}: {
  data: GateState;
  onCommand: (id: string, command: string) => void;
}) {
  const { t } = useTranslation();
  const isOpen = data.state === 'open';
  const isClosed = data.state === 'closed';
  const isOpenOnly = data.control_mode === 'open_only';

  const stateLabel: Record<string, string> = {
    open: t('templates.gate_open'),
    closed: t('templates.gate_closed'),
    opening: t('templates.gate_opening'),
    closing: t('templates.gate_closing'),
  };

  // The button that undoes the current state is the one you are most likely
  // after, so it is the filled one. Open and Close stay disabled in the state
  // they would not change: on a single-relay gate a pulse is a toggle, and
  // "open" on an open gate would start closing it.
  const suggested = isOpen && !isOpenOnly ? 'CLOSE' : isClosed ? 'OPEN' : null;

  return (
    <TemplateTile
      icon={isClosed ? FaDoorClosed : FaDoorOpen}
      tone={TONE[data.state] ?? 'neutral'}
      name={data.name || data.id}
      state={stateLabel[data.state] ?? data.state}
      footer={
        <div className={clsx('grid gap-2', isOpenOnly ? 'grid-cols-2' : 'grid-cols-3')}>
          <button
            type="button"
            className={clsx(TILE_BUTTON_STACKED, suggested === 'OPEN' && 'btn-primary')}
            disabled={isOpen}
            onClick={() => onCommand(data.id, 'OPEN')}
          >
            <FaArrowUp className="w-4 h-4" />
            <span className="text-xs leading-tight">{t('templates.open')}</span>
          </button>
          <button
            type="button"
            className={TILE_BUTTON_STACKED}
            onClick={() => onCommand(data.id, 'STOP')}
          >
            <FaStop className="w-3.5 h-3.5" />
            <span className="text-xs leading-tight">{t('templates.stop')}</span>
          </button>
          {!isOpenOnly && (
            <button
              type="button"
              className={clsx(TILE_BUTTON_STACKED, suggested === 'CLOSE' && 'btn-primary')}
              disabled={isClosed}
              onClick={() => onCommand(data.id, 'CLOSE')}
            >
              <FaArrowDown className="w-4 h-4" />
              <span className="text-xs leading-tight">{t('templates.close')}</span>
            </button>
          )}
        </div>
      }
    />
  );
}
