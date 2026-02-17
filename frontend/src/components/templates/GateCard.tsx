import { useTranslation } from '@/hooks/useTranslation';
import { FaDoorOpen } from 'react-icons/fa';
import type { GateState } from './types';

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

  return (
    <div className="rounded-xl bg-base-100 shadow-sm px-4 py-6 max-w-xs w-full flex flex-col justify-between min-h-[120px]">
      {/* Header row: icon + name + state badge */}
      <div className="flex items-center gap-2">
        <FaDoorOpen className={`h-4 w-4 shrink-0 ${isOpen ? 'text-warning' : 'text-blue-500'}`} />
        <span className="font-medium text-sm truncate flex-1">{data.name || data.id}</span>
        <span className={`badge badge-sm ${isOpen ? 'badge-warning' : isClosed ? 'badge-success' : 'badge-ghost'}`}>
          {isOpen ? t('templates.gate_open') : isClosed ? t('templates.gate_closed') : data.state}
        </span>
      </div>

      {/* Controls — pushed to bottom */}
      <div className="flex gap-1.5 mt-auto pt-3">
        <button
          className="btn btn-xs btn-outline flex-1"
          disabled={isOpen}
          onClick={() => onCommand(data.id, 'OPEN')}
        >
          {t('templates.open')}
        </button>
        <button
          className="btn btn-xs btn-ghost flex-1"
          onClick={() => onCommand(data.id, 'STOP')}
        >
          Stop
        </button>
        {!isOpenOnly && (
          <button
            className="btn btn-xs btn-outline flex-1"
            disabled={isClosed}
            onClick={() => onCommand(data.id, 'CLOSE')}
          >
            {t('templates.close')}
          </button>
        )}
      </div>
    </div>
  );
}
