import { FaMapMarkerAlt } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

interface GroupByAreaToggleProps {
  active: boolean;
  onToggle: (on: boolean) => void;
}

/** The "group by area" button next to the sort and view controls. */
export default function GroupByAreaToggle({ active, onToggle }: GroupByAreaToggleProps) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      className={`btn btn-sm gap-1 ${active ? 'btn-active' : 'btn-ghost'}`}
      onClick={() => onToggle(!active)}
      aria-pressed={active}
      title={t('common.group_by_area')}
    >
      <FaMapMarkerAlt />
      <span className="hidden sm:inline">{t('common.group_by_area')}</span>
    </button>
  );
}
