import { useState, useContext } from 'react';
import axios from 'axios';
import { WebSocketContext } from '../App';
import ViewToggle from './ViewToggle';
import { isOutputEvent, isCoverEvent, isGroupEvent, CoverState } from '../hooks/useWebSocket';
import OutputItem from './OutputItem';
import CoverItem from './CoverItem';

export default function OutputsView({error}: {error: string | null}) {
  const [outputError, setError] = useState<string | null>(null);
  const { outputs, covers, groups } = useContext(WebSocketContext);
  console.log("outputs", outputs, covers, groups);
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('outputViewMode');
    return saved ? saved === 'grid' : true;
  });

  const validOutputs = outputs.filter(isOutputEvent).map(e => e.state);
  const validGroups = groups.filter(isGroupEvent).map(e => e.state);
  console.log("validOutputs", validOutputs, "validGroups", groups, validGroups);

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('outputViewMode', gridView ? 'grid' : 'list');
  };

  const toggleOutput = async (id: string, name: string, type: string) => {
    try {
      const response = await axios.post(`/api/outputs/${id}/toggle`);
      console.log("re", response, type)
      if (response.data.status === 'interlock') {
        setError(`${type} ${name} is locked by interlock`);
        return;
      }
      setError(null);
    } catch (error) {
      console.error('Error toggling output:', error);
      setError('Failed to toggle output');
    }
  };

  const actionCover = async (id: string, name: string, action: string) => {
    try {
      await axios.post(`/api/covers/${id}/action`, { action });
      setError(null);
    } catch (error) {
      console.error(`Error controlling cover ${name}:`, error);
      setError(`Failed to control cover ${name}`);
    }
  };

  const toggleGroup = async (id: string, name: string, type: string) => {
    try {
      const response = await axios.post(`/api/groups/${id}/toggle`);
      console.log("group toggle", response, type);
      if (response.data.status === 'interlock') {
        setError(`${type} ${name} is locked by interlock`);
        return;
      }
      setError(null);
    } catch (error) {
      console.error('Error toggling group:', error);
      setError('Failed to toggle group');
    }
  };

  return (
    <div className="container mx-auto p-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <h2 className="card-title">Controls</h2>
            <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
          </div>
          {/* Individual Outputs */}
          <div className={isGrid 
            ? "grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4"
            : "flex flex-col gap-4"
          }>
            {validOutputs.map((output) => (
              <OutputItem 
                key={output.id}
                output={output}
                onToggle={toggleOutput}
                isGrid={isGrid}
                error={error}
              />
            ))}
          </div>

          {/* Output Groups */}
          {validGroups.length > 0 && (
            <>
              <div className="divider">Groups</div>
              <div className={isGrid 
                ? "grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4"
                : "flex flex-col gap-4"
              }>
                {validGroups.map((group) => (
                  <OutputItem 
                    key={group.id}
                    output={{
                      id: group.id,
                      name: group.name,
                      state: group.state,
                      type: group.type,
                      expander_id: null,
                      pin: 0,
                      timestamp: group.timestamp
                    }}
                    onToggle={toggleGroup}
                    isGrid={isGrid}
                    error={error}
                  />
                ))}
              </div>
            </>
          )}

          {/* Covers */}
          <div className={isGrid 
            ? "grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4"
            : "flex flex-col gap-4"
          }>
            {covers.filter(cover => isCoverEvent(cover)).map((cover) => (
              <CoverItem 
                key={cover.entity_id}
                cover={cover.state as CoverState}
                action={actionCover}
                isGrid={isGrid}
                error={error}
              />
            ))}
          </div>
        </div>
      </div>
      {outputError && <div className='toast'><div className="alert alert-error">{outputError}</div></div>}
    </div>
  );
}
