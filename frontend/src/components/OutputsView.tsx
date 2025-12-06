import { useState, useContext, useMemo } from 'react';
import axios from 'axios';
import { WebSocketContext } from '../App';
import ViewToggle from './ViewToggle';
import { isOutputEvent, isCoverEvent, isGroupEvent, CoverState, OutputState } from '../hooks/useWebSocket';
import OutputItem from './OutputItem';
import CoverItem from './CoverItem';

// Output type categories
type OutputCategory = 'light' | 'switch' | 'valve' | 'cover' | 'group' | 'state_only';

/**
 * Categorize output by its type
 */
function categorizeOutput(type: string | undefined): OutputCategory {
  const t = (type || '').toLowerCase();
  
  if (t === 'light') return 'light';
  if (t === 'valve') return 'valve';
  if (t === 'cover' || t === 'none') return 'state_only';
  // Default to switch for relay, switch, or unknown types
  return 'switch';
}

/**
 * Category display configuration
 */
const categoryConfig: Record<OutputCategory, { label: string; order: number }> = {
  light: { label: 'Lights', order: 1 },
  switch: { label: 'Switches', order: 2 },
  valve: { label: 'Valves', order: 3 },
  cover: { label: 'Covers', order: 4 },
  group: { label: 'Groups', order: 5 },
  state_only: { label: 'State Only', order: 6 },
};

export default function OutputsView({error}: {error: string | null}) {
  const [outputError, setError] = useState<string | null>(null);
  const { outputs, covers, groups } = useContext(WebSocketContext);
  
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('outputViewMode');
    return saved ? saved === 'grid' : true;
  });

  // Filter and categorize outputs
  const { categorizedOutputs, stateOnlyOutputs } = useMemo(() => {
    const allOutputs = outputs
      .filter(isOutputEvent)
      .map(e => e.state);
    
    const categorized: Record<OutputCategory, OutputState[]> = {
      light: [],
      switch: [],
      valve: [],
      cover: [],
      group: [],
      state_only: [],
    };
    
    allOutputs.forEach(output => {
      const category = categorizeOutput(output.type);
      categorized[category].push(output);
    });
    
    return {
      categorizedOutputs: categorized,
      stateOnlyOutputs: categorized.state_only,
    };
  }, [outputs]);

  // Get valid groups
  const validGroups = useMemo(() => 
    groups.filter(isGroupEvent).map(e => e.state),
    [groups]
  );

  // Get valid covers
  const validCovers = useMemo(() => 
    covers.filter(isCoverEvent).map(c => c.state as CoverState),
    [covers]
  );

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('outputViewMode', gridView ? 'grid' : 'list');
  };

  const toggleOutput = async (id: string, name: string, type: string) => {
    try {
      const response = await axios.post(`/api/outputs/${id}/toggle`);
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

  const gridClass = "grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4";
  const listClass = "flex flex-col gap-4";

  /**
   * Render a section with outputs
   */
  const renderOutputSection = (
    category: OutputCategory,
    items: OutputState[],
    onToggle: (id: string, name: string, type: string) => void,
    isStateOnly: boolean = false
  ) => {
    if (items.length === 0) return null;
    
    return (
      <div key={category}>
        <div className="divider">{categoryConfig[category].label}</div>
        <div className={isGrid ? gridClass : listClass}>
          {items.map((output) => (
            <OutputItem 
              key={output.id}
              output={output}
              onToggle={isStateOnly ? undefined : onToggle}
              isGrid={isGrid}
              error={error}
              stateOnly={isStateOnly}
            />
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="container mx-auto p-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <h2 className="card-title">Controls</h2>
            <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
          </div>

          {/* Lights */}
          {renderOutputSection('light', categorizedOutputs.light, toggleOutput)}

          {/* Switches */}
          {renderOutputSection('switch', categorizedOutputs.switch, toggleOutput)}

          {/* Valves */}
          {renderOutputSection('valve', categorizedOutputs.valve, toggleOutput)}

          {/* Covers */}
          {validCovers.length > 0 && (
            <>
              <div className="divider">Covers</div>
              <div className={isGrid ? gridClass : listClass}>
                {validCovers.map((cover) => (
                  <CoverItem 
                    key={cover.id}
                    cover={cover}
                    action={actionCover}
                    isGrid={isGrid}
                    error={error}
                  />
                ))}
              </div>
            </>
          )}

          {/* Groups */}
          {validGroups.length > 0 && (
            <>
              <div className="divider">Groups</div>
              <div className={isGrid ? gridClass : listClass}>
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
                      timestamp: group.timestamp,
                      area: null,
                      interlock_groups: []
                    }}
                    onToggle={toggleGroup}
                    isGrid={isGrid}
                    error={error}
                    isGroup={true}
                  />
                ))}
              </div>
            </>
          )}

          {/* State Only (cover or none type outputs - no controls) */}
          {renderOutputSection('state_only', stateOnlyOutputs, toggleOutput, true)}

        </div>
      </div>
      {outputError && <div className='toast'><div className="alert alert-error">{outputError}</div></div>}
    </div>
  );
}
