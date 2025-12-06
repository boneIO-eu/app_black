import { useContext, memo, useState } from 'react';
import { WebSocketContext } from '../App';
import { formatTimestamp } from '../utils/formatters';
import ViewToggle from './ViewToggle';
import { isInputEvent, InputEvent } from '../hooks/useWebSocket';
import clsx from 'clsx';

// Separate component for individual input
const InputItem = memo(({ inputEvent, isGrid }: {
  inputEvent: InputEvent;
  isGrid: boolean;
}) => (
  <div
    className={`bg-base-200 text-secondary-content shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4' : 'border-l-8'} border-blue-500`}
  >
    <div className={`flex ${isGrid ? 'justify-between items-start' : 'flex-col gap-2'}`}>
      <div>
        <h3 className="font-semibold text-lg">{inputEvent.state.name}</h3>
        <p className="text-xs text-gray-500">{inputEvent.entity_id}</p>
        <p className="text-sm">Type: {inputEvent.state.type === "input" ? "Event entity" : "Binary sensor"}</p>
        <p className="text-xs text-gray-400">Area: {inputEvent.state.area || 'No area'}</p>
      </div>
      <div className={`${isGrid ? 'text-right' : ''}`}>
        <span
          className={clsx('px-4 py-2 rounded-lg font-semibold',
            inputEvent.state.state === 'ON' ? 'bg-primary text-white' :
            inputEvent.state.state === 'single' ? 'bg-success text-black' :
            inputEvent.state.state === 'double' ? 'bg-warning text-black' :
            inputEvent.state.state === 'long' ? 'bg-info text-white' :
            'bg-base-200 text-base-content'
          )}
        >
          {inputEvent.state.state}
        </span>
        <p className="text-gray-500 text-xs mt-2">
          {formatTimestamp(inputEvent.state.timestamp)}
        </p>
      </div>
    </div>
  </div>
));

export default function InputsView() {
  const { inputs } = useContext(WebSocketContext);
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('inputViewMode');
    return saved ? saved === 'grid' : true;
  });

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('inputViewMode', gridView ? 'grid' : 'list');
  };

  // Filter inputs to only include InputState objects
  const validInputs = inputs.filter(isInputEvent);
  console.log(validInputs);
  if (validInputs.length === 0) {
    return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Inputs</h2>
      </div>
      <div>
        No inputs configured.
      </div>
    </div>)
  }
  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Inputs</h2>
        <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
      </div>
      <div className={isGrid 
        ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
        : "flex flex-col gap-4"
      }>
        {validInputs.map((inputEvent: InputEvent) => (
          <InputItem key={inputEvent.entity_id} inputEvent={inputEvent} isGrid={isGrid} />
        ))}
      </div>
    </div>
  );
}
