import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface OutputSelectDropdownProps {
  value: string;
  onChange: (value: string) => void;
  allOutputs: any[];
  allAreas: any[];
  placeholder?: string;
  /** Saved (committed) outputs for comparison - items not in saved are disabled */
  savedOutputs?: any[];
  /** Saved (committed) output groups for comparison */
  savedOutputGroups?: any[];
  /** IDs to exclude from the list (e.g., to prevent selecting same output twice) */
  excludeIds?: string[];
  /** Hint message shown when no outputs are available */
  emptyHint?: string;
}

/**
 * OutputSelectDropdown - Reusable widget for selecting boneIO outputs.
 * Displays output name, ID, and area in a dropdown format.
 * Supports output groups, saved-state indicators, and area display.
 */
const OutputSelectDropdown: React.FC<OutputSelectDropdownProps> = ({
  value,
  onChange,
  allOutputs,
  allAreas,
  placeholder = 'Select output...',
  savedOutputs,
  savedOutputGroups,
  excludeIds = [],
  emptyHint,
}) => {
  const { t } = useTranslation();
  /**
   * Check if an output is saved (committed) by comparing with saved data.
   */
  const isOutputSaved = (outputId: string, isGroup: boolean): boolean => {
    if (isGroup) {
      if (!savedOutputGroups) return true; // If no saved data provided, assume all are saved
      return savedOutputGroups.some((g: any) => g.id === outputId);
    } else {
      if (!savedOutputs) return true;
      return savedOutputs.some((o: any) => {
        const id = o.id || o.boneio_output;
        return id === outputId;
      });
    }
  };

  /**
   * Derive a consistent ID for an output entry.
   * Remote outputs may have an empty `id` — in that case, generate
   * the same fallback as the backend: `${device_id}_${output_id}`.
   */
  const deriveOutputId = (output: any): string => {
    if (output.id) return output.id;
    if (output.boneio_output) return output.boneio_output;
    // Remote output fallback: device_id + output_id (mirrors backend logic)
    if (output.device_id && output.output_id) {
      return `${output.device_id}_${output.output_id}`.replace(/-/g, '_');
    }
    return '';
  };

  // Normalize outputs to have consistent id field and filter out excluded IDs
  const normalizedOutputs = allOutputs
    .filter((output) => {
      const id = deriveOutputId(output);
      return id && !excludeIds.includes(id);
    })
    .map((output) => {
      const id = deriveOutputId(output);
      const isGroup = output.isGroup || false;
      const isRemote = Boolean(output.device_id && output.output_id);
      const isSaved = isOutputSaved(id, isGroup);
      return {
        ...output,
        id,
        name: output.name || id,
        isGroup,
        isRemote,
        isSaved,
      };
    });

  // Find selected output for display
  const selectedOutput = normalizedOutputs.find((output) => output.id === value);
  
  const getAreaName = (areaId: string) => {
    if (!areaId) return '';
    const area = allAreas.find((a) => a.id === areaId);
    return area?.name || areaId;
  };

  return (
    <Select value={value || ''} onValueChange={onChange}>
      <SelectTrigger className="w-full input input-bordered h-auto min-h-12 py-2">
        <SelectValue placeholder={placeholder}>
          {selectedOutput ? (
            <div className="flex flex-col items-start">
              <span className="font-medium">
                {selectedOutput.isGroup && <span className="badge badge-xs badge-secondary mr-1">{t('outputs.badge_group')}</span>}
                {selectedOutput.isRemote && <span className="badge badge-xs badge-info mr-1">{t('outputs.badge_remote')}</span>}
                {selectedOutput.name}
              </span>
              <span className="text-xs opacity-60">
                ID: {selectedOutput.id}
                {selectedOutput.device_id && ` • ${t('outputs.device_label')}: ${selectedOutput.device_id}`}
                {selectedOutput.area && ` • ${t('outputs.area_label')}: ${getAreaName(selectedOutput.area)}`}
              </span>
            </div>
          ) : (
            <span className="opacity-50">{placeholder}</span>
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent className="bg-base-100">
        {normalizedOutputs.length === 0 ? (
          <div className="px-3 py-4 text-center text-sm text-base-content/50">
            <p className="font-medium">{emptyHint || t('outputs.no_outputs_available')}</p>
          </div>
        ) : (
          normalizedOutputs.map((output) => (
            <SelectItem 
              key={output.id} 
              value={output.id}
              disabled={!output.isSaved}
              className={`focus:bg-base-200 hover:bg-base-200 data-highlighted:bg-base-200 ${!output.isSaved ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <div className="flex flex-col">
                <span className="font-medium">
                  {output.isGroup && <span className="badge badge-xs badge-secondary mr-1">{t('outputs.badge_group')}</span>}
                  {output.isRemote && <span className="badge badge-xs badge-info mr-1">{t('outputs.badge_remote')}</span>}
                  {!output.isSaved && <span className="badge badge-xs badge-warning mr-1">{t('outputs.badge_unsaved')}</span>}
                  {output.name}
                </span>
                <span className="text-xs opacity-60">
                  ID: {output.id}
                  {output.device_id && ` • ${t('outputs.device_label')}: ${output.device_id}`}
                  {output.area && ` • ${t('outputs.area_label')}: ${getAreaName(output.area)}`}
                </span>
              </div>
            </SelectItem>
          ))
        )}
      </SelectContent>
    </Select>
  );
};

export default OutputSelectDropdown;
