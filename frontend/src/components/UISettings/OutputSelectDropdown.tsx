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
}) => {
  // Normalize outputs to have consistent id field
  const normalizedOutputs = allOutputs.map((output) => ({
    ...output,
    id: output.id || output.boneio_output,
    name: output.name || output.id || output.boneio_output,
    isGroup: output.isGroup || false,
  }));

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
            className="focus:bg-base-200 hover:bg-base-200 data-highlighted:bg-base-200"
          >
            <div className="flex flex-col">
              <span className="font-medium">
                {output.isGroup && <span className="badge badge-xs badge-secondary mr-1">Group</span>}
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
