import React from 'react';
import { FaSearch, FaTimes } from 'react-icons/fa';
import { useTranslation } from '../../../hooks/useTranslation';

interface FilterInputProps {
  filter: string;
  setFilter: (value: string) => void;
  totalCount?: number;
  filteredCount?: number;
}

/**
 * Reusable filter input component for tables.
 * Shows search icon, input field, clear button, and optional results count.
 */
const FilterInput: React.FC<FilterInputProps> = ({ 
  filter, 
  setFilter, 
  totalCount, 
  filteredCount 
}) => {
  const { t } = useTranslation();

  return (
    <div className="space-y-2">
      <div className="relative">
        <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-base-content/40" />
        <input
          type="text"
          placeholder={t('common.filter_placeholder')}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="input input-bordered w-full pl-9 pr-8"
        />
        {filter && (
          <button
            onClick={() => setFilter('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 btn btn-ghost btn-xs p-1 min-h-0 h-5 w-5"
          >
            <FaTimes className="w-3 h-3" />
          </button>
        )}
      </div>
      
      {/* Results count when filtering */}
      {filter && totalCount !== undefined && filteredCount !== undefined && (
        <div className="text-xs text-base-content/60">
          {t('common.showing')} {filteredCount} {t('common.of')} {totalCount}
        </div>
      )}
    </div>
  );
};

export default FilterInput;
