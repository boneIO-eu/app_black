import React from 'react';
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
}

/**
 * OutputSelectDropdown - Uses shadcn/ui Select component
 * Displays output name, ID, and area in a dropdown format
 */
const OutputSelectDropdown: React.FC<OutputSelectDropdownProps> = ({
  value,
  onChange,
  allOutputs,
  allAreas,
  placeholder = 'Select output...',
  savedOutputs,
  savedOutputGroups,
}) => {
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

  // Normalize outputs to have consistent id field
  const normalizedOutputs = allOutputs.map((output) => {
    const id = output.id || output.boneio_output;
    const isGroup = output.isGroup || false;
    const isSaved = isOutputSaved(id, isGroup);
    return {
      ...output,
      id,
      name: output.name || id,
      isGroup,
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
                {selectedOutput.isGroup && <span className="badge badge-xs badge-secondary mr-1">Group</span>}
                {selectedOutput.name}
              </span>
              <span className="text-xs opacity-60">
                ID: {selectedOutput.id}
                {selectedOutput.area && ` • Area: ${getAreaName(selectedOutput.area)}`}
              </span>
            </div>
          ) : (
            <span className="opacity-50">{placeholder}</span>
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent className="bg-base-100">
        {normalizedOutputs.map((output) => (
          <SelectItem 
            key={output.id} 
            value={output.id}
            disabled={!output.isSaved}
            className={`focus:bg-base-200 hover:bg-base-200 data-highlighted:bg-base-200 ${!output.isSaved ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <div className="flex flex-col">
              <span className="font-medium">
                {output.isGroup && <span className="badge badge-xs badge-secondary mr-1">Group</span>}
                {!output.isSaved && <span className="badge badge-xs badge-warning mr-1">Niezapisane</span>}
                {output.name}
              </span>
              <span className="text-xs opacity-60">
                ID: {output.id}
                {output.area && ` • Area: ${getAreaName(output.area)}`}
              </span>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};

export default OutputSelectDropdown;
