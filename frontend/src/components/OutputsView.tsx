import { useState, useContext, useMemo, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from '@/api/axios';
import { WebSocketContext } from '../App';
import ViewToggle from './ViewToggle';
import { isOutputEvent, isCoverEvent, isGroupEvent, CoverState, OutputState } from '../hooks/useWebSocket';
import EntityCard from './EntityCard';
import type { EntityData } from './EntityCard';
import { EntityGrid, ENTITY_GRID_CLASS } from './EntityGrid';
import CoverItem from './CoverItem';
import { useTranslation } from '../hooks/useTranslation';
import { FaExclamationTriangle, FaSortAmountDown, FaSortAlphaDown, FaClock, FaCog, FaWifi } from 'react-icons/fa';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

import type { OutputCategory, SortMode } from '@/types/outputs';

/**
 * Categorize output by its type
 */
function categorizeOutput(type: string | undefined): OutputCategory {
  const typeStr = (type || '').toLowerCase();
  
  if (typeStr === 'light') return 'light';
  if (typeStr === 'valve') return 'valve';
  if (typeStr === 'cover' || typeStr === 'none') return 'state_only';
  // Default to switch for relay, switch, or unknown types
  return 'switch';
}

export default function OutputsView({error}: {error: string | null}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [outputError, setError] = useState<string | null>(null);
  const { outputs, covers, groups } = useContext(WebSocketContext);
  const [hardwareErrorsCount, setHardwareErrorsCount] = useState<number>(0);
  
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('outputViewMode');
    return saved ? saved === 'grid' : true;
  });
  const [sortMode, setSortMode] = useState<SortMode>(() => {
    const saved = localStorage.getItem('outputSortMode');
    return (saved as SortMode) || 'name';
  });
  const [recentlyChanged, setRecentlyChanged] = useState<Set<string>>(new Set());
  const prevOutputsRef = useRef<Map<string, { state: string; timestamp: number }>>(new Map());
  const isInitializedRef = useRef(false);

  // Fetch hardware errors count
  useEffect(() => {
    const fetchHardwareErrors = async () => {
      try {
        const { data } = await axios.get('/api/hardware/errors');
        setHardwareErrorsCount(data.errors?.length || 0);
      } catch (err) {
        console.error('Failed to fetch hardware errors:', err);
      }
    };

    fetchHardwareErrors();
    // Poll every 30 seconds
    const interval = setInterval(fetchHardwareErrors, 30000);
    return () => clearInterval(interval);
  }, []);

  // Get translated category labels
  const getCategoryLabel = (category: OutputCategory): string => {
    const labels: Record<OutputCategory, string> = {
      light: t('outputs.categories.lights'),
      switch: t('outputs.categories.switches'),
      valve: t('outputs.categories.valves'),
      cover: t('outputs.categories.covers'),
      group: t('outputs.categories.groups'),
      state_only: t('outputs.categories.state_only'),
    };
    return labels[category];
  };

  // Sort function for outputs
  const sortOutputs = (items: OutputState[]): OutputState[] => {
    const sorted = [...items];
    if (sortMode === 'recent') {
      sorted.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
    } else {
      sorted.sort((a, b) => a.name.localeCompare(b.name));
    }
    return sorted;
  };

  // Fetch remote devices
  const [remoteDevices, setRemoteDevices] = useState<any[]>([]);

  useEffect(() => {
    const fetchRemoteDevices = async () => {
      try {
        const { data } = await axios.get('/api/remote-devices/all');
        setRemoteDevices(data.devices || []);
      } catch (err) {
        console.error('Failed to fetch remote devices', err);
      }
    };
    fetchRemoteDevices();
    const interval = setInterval(fetchRemoteDevices, 10000);
    return () => clearInterval(interval);
  }, []);

  // Filter and categorize outputs (local vs remote)
  const { categorizedOutputs, stateOnlyOutputs, remoteOutputs } = useMemo(() => {
    const allOutputs = outputs
      .filter(isOutputEvent)
      .map(e => e.state);

    // Add remote device outputs (only CAN devices — legacy approach)
    remoteDevices.forEach(device => {
      if (device.protocol === 'can' && device.outputs) {
        device.outputs.forEach((out: any) => {
          allOutputs.push({
            id: `remote_${device.id}_${out.id}`,
            name: `${device.name} - ${out.name}`,
            state: out.state,
            type: out.type || 'switch',
            expander_id: null,
            pin: 0,
            timestamp: null,
            area: null,
            interlock_groups: [],
            remote: true,
          });
        });
      }
    });

    // Separate local and remote outputs
    const localOutputs = allOutputs.filter(o => !o.remote);
    const remote = sortOutputs(allOutputs.filter(o => !!o.remote));
    
    const categorized: Record<OutputCategory, OutputState[]> = {
      light: [],
      switch: [],
      valve: [],
      cover: [],
      group: [],
      state_only: [],
    };
    
    localOutputs.forEach(output => {
      const category = categorizeOutput(output.type);
      categorized[category].push(output);
    });

    // Sort each category
    Object.keys(categorized).forEach(key => {
      categorized[key as OutputCategory] = sortOutputs(categorized[key as OutputCategory]);
    });
    
    return {
      categorizedOutputs: categorized,
      stateOnlyOutputs: categorized.state_only,
      remoteOutputs: remote,
    };
  }, [outputs, sortMode]);

  // Get valid groups
  const validGroups = useMemo(() => 
    groups.filter(isGroupEvent).map(e => e.state),
    [groups]
  );

  // Get valid covers
  const validCovers = useMemo(() => {
    const allCovers = covers.filter(isCoverEvent).map(c => c.state as CoverState);
    remoteDevices.forEach(device => {
      if (device.protocol === 'can' && device.covers) {
        device.covers.forEach((cov: any) => {
          allCovers.push({
            id: `remote_${device.id}_${cov.id}`,
            name: `${device.name} - ${cov.name}`,
            state: cov.state,
            position: cov.position || 0,
            kind: cov.kind || 'standard',
            timestamp: null,
            tilt: cov.tilt || 0,
            current_operation: cov.current_operation || 'stopped'
          });
        });
      }
    });
    return allCovers;
  }, [covers, remoteDevices]);

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('outputViewMode', gridView ? 'grid' : 'list');
  };

  const handleSortChange = (mode: SortMode) => {
    setSortMode(mode);
    localStorage.setItem('outputSortMode', mode);
  };

  // Long press dialog state
  const [longPressDialog, setLongPressDialog] = useState<{ 
    open: boolean; 
    output: OutputState | CoverState | null;
    type: 'output' | 'output_group' | 'cover' | 'remote_outputs';
  }>({
    open: false,
    output: null,
    type: 'output'
  });

  const handleLongPress = useCallback((output: EntityData) => {
    setLongPressDialog({ open: true, output: output as OutputState, type: 'output' });
  }, []);

  const handleGroupLongPress = useCallback((output: EntityData) => {
    setLongPressDialog({ open: true, output: output as OutputState, type: 'output_group' });
  }, []);

  const handleCoverLongPress = useCallback((cover: CoverState) => {
    setLongPressDialog({ open: true, output: cover, type: 'cover' });
  }, []);

  const handleRemoteOutputLongPress = useCallback((output: EntityData) => {
    setLongPressDialog({ open: true, output: output as OutputState, type: 'remote_outputs' });
  }, []);

  const handleGoToSettings = useCallback(() => {
    if (!longPressDialog.output) return;
    // Use id for filtering instead of name to avoid duplicates
    const outputId = longPressDialog.output.id;
    const section = longPressDialog.type;
    navigate(`/settings/${section}?edit=${encodeURIComponent(outputId)}`);
    setLongPressDialog({ open: false, output: null, type: 'output' });
  }, [longPressDialog.output, longPressDialog.type, navigate]);

  // Track recently changed outputs for highlight effect
  useEffect(() => {
    const allOutputs = outputs.filter(isOutputEvent).map(e => e.state);
    const now = Date.now() / 1000; // Current time in seconds
    
    if (!isInitializedRef.current) {
      allOutputs.forEach(output => {
        prevOutputsRef.current.set(output.id, {
          state: output.state,
          timestamp: output.timestamp || 0
        });
      });
      isInitializedRef.current = true;
      return;
    }
    
    allOutputs.forEach(output => {
      const prevData = prevOutputsRef.current.get(output.id);
      const currentTimestamp = output.timestamp || 0;
      // Only highlight if event is recent (within last 5 seconds) to avoid stale events on page load
      const isRecent = currentTimestamp > 0 && (now - currentTimestamp) < 5;
      const hasChanged = prevData && prevData.timestamp !== currentTimestamp && isRecent;
      
      if (hasChanged) {
        setRecentlyChanged(prev => new Set(prev).add(output.id));
        setTimeout(() => {
          setRecentlyChanged(prev => {
            const next = new Set(prev);
            next.delete(output.id);
            return next;
          });
        }, 2000);
      }
      
      // Always update the ref
      prevOutputsRef.current.set(output.id, {
        state: output.state,
        timestamp: currentTimestamp
      });
    });
  }, [outputs]);

  const toggleOutput = async (id: string, name: string, type: string) => {
    try {
      if (id.startsWith('remote_')) {
        // remote_{device_id}_{output_id}
        const parts = id.split('_');
        const deviceId = parts.slice(1, -1).join('_');
        const outputId = parts[parts.length - 1];
        await axios.post(`/api/remote-devices/${deviceId}/output/${outputId}/action`, {
          action: 'TOGGLE'
        });
        setError(null);
        return;
      }

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
      if (id.startsWith('remote_')) {
        const parts = id.split('_');
        const deviceId = parts.slice(1, -1).join('_');
        const coverId = parts[parts.length - 1];
        await axios.post(`/api/remote-devices/${deviceId}/cover/${coverId}/action`, {
          action: action
        });
        setError(null);
        return;
      }
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

  const handleDurationChange = useCallback(async (id: string, value: number) => {
    try {
      await axios.post(`/api/outputs/${id}/set_duration`, { value });
    } catch (err) {
      console.error('Error setting duration:', err);
      setError('Failed to set duration');
    }
  }, []);

  const handleBrightnessChange = useCallback(async (id: string, value: number) => {
    try {
      await axios.post(`/api/outputs/${id}/set_brightness`, { brightness: value });
    } catch (err) {
      console.error('Error setting brightness:', err);
      setError('Failed to set brightness');
    }
  }, []);



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
        <div className="divider">{getCategoryLabel(category)}</div>
        <EntityGrid isGrid={isGrid}>
          {items.map((output) => (
            <EntityCard 
              key={output.id}
              output={output}
              onToggle={isStateOnly ? undefined : onToggle}
              onDurationChange={handleDurationChange}
              onBrightnessChange={handleBrightnessChange}
              isGrid={isGrid}
              error={error}
              stateOnly={isStateOnly}
              isHighlighted={recentlyChanged.has(output.id)}
              onLongPress={handleLongPress}
            />
          ))}
        </EntityGrid>
      </div>
    );
  };

  return (
    <div className="container mx-auto p-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <h2 className="card-title">{t('outputs.title')}</h2>
            <div className="flex items-center gap-2">
              {/* Sort dropdown */}
              <div className="dropdown dropdown-end">
                <label tabIndex={0} className="btn btn-sm btn-ghost gap-1">
                  {sortMode === 'recent' ? <FaClock /> : <FaSortAlphaDown />}
                  <span className="hidden sm:inline">{t(`outputs.sort_${sortMode}`)}</span>
                  <FaSortAmountDown className="w-3 h-3" />
                </label>
                <ul tabIndex={0} className="dropdown-content z-1 menu p-2 shadow bg-base-100 rounded-box w-52">
                  <li>
                    <button 
                      onClick={() => handleSortChange('name')}
                      className={sortMode === 'name' ? 'active' : ''}
                    >
                      <FaSortAlphaDown /> {t('outputs.sort_name')}
                    </button>
                  </li>
                  <li>
                    <button 
                      onClick={() => handleSortChange('recent')}
                      className={sortMode === 'recent' ? 'active' : ''}
                    >
                      <FaClock /> {t('outputs.sort_recent')}
                    </button>
                  </li>
                </ul>
              </div>
              <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
            </div>
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
              <div className="divider">{getCategoryLabel('cover')}</div>
              <EntityGrid isGrid={isGrid} gridClassName={cn(ENTITY_GRID_CLASS, "grid-cols-1")}>
                {validCovers.map((cover) => (
                  <CoverItem 
                    key={cover.id}
                    cover={cover}
                    action={actionCover}
                    isGrid={isGrid}
                    error={error}
                    onLongPress={handleCoverLongPress}
                  />
                ))}
              </EntityGrid>
            </>
          )}

          {/* Groups */}
          {validGroups.length > 0 && (
            <>
              <div className="divider">{getCategoryLabel('group')}</div>
              <EntityGrid isGrid={isGrid}>
                {validGroups.map((group) => (
                  <EntityCard 
                    key={group.id}
                    output={{
                      id: group.id,
                      name: group.name,
                      state: group.state,
                      type: group.type,
                      timestamp: group.timestamp,
                      area: null,
                      interlock_groups: []
                    }}
                    onToggle={toggleGroup}
                    isGrid={isGrid}
                    error={error}
                    isGroup={true}
                    onLongPress={handleGroupLongPress}
                  />
                ))}
              </EntityGrid>
            </>
          )}

          {/* State Only (cover or none type outputs - no controls) */}
          {renderOutputSection('state_only', stateOnlyOutputs, toggleOutput, true)}

          {/* Remote Outputs */}
          {remoteOutputs.length > 0 && (
            <>
              <div className="divider">
                <span className="flex items-center gap-2">
                  <FaWifi className="text-primary" />
                  {t('sections.remote_outputs')}
                </span>
              </div>
              <EntityGrid isGrid={isGrid}>
                {remoteOutputs.map((output) => (
                  <EntityCard
                    key={output.id}
                    output={output}
                    onToggle={toggleOutput}
                    onDurationChange={handleDurationChange}
                    onBrightnessChange={handleBrightnessChange}
                    isGrid={isGrid}
                    error={error}
                    isHighlighted={recentlyChanged.has(output.id)}
                    onLongPress={handleRemoteOutputLongPress}
                  />
                ))}
              </EntityGrid>
            </>
          )}

        </div>
      </div>
      {outputError && <div className='toast'><div className="alert alert-error">{outputError}</div></div>}
      
      {/* Hardware Errors Toast */}
      {hardwareErrorsCount > 0 && (
        <div className="toast toast-top toast-center z-50">
          <div className="alert alert-error shadow-lg">
            <FaExclamationTriangle />
            <div>
              <h3 className="font-bold">{t('system_update.hardware_errors_title')}</h3>
              <div className="text-xs">
                {hardwareErrorsCount} {t('outputs.hardware_errors_found')}
              </div>
            </div>
            <a href="/system" className="btn btn-sm btn-outline">
              {t('outputs.view_details')}
            </a>
          </div>
        </div>
      )}

      {/* Long press dialog - go to settings */}
      <Dialog open={longPressDialog.open} onOpenChange={(open) => setLongPressDialog({ open, output: open ? longPressDialog.output : null, type: longPressDialog.type })}>
        <DialogContent className="sm:max-w-md bg-base-200">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FaCog className="w-5 h-5" />
              {t('outputs.go_to_settings')}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p>{t('outputs.go_to_settings_confirm')}</p>
            <p className="font-semibold mt-2">{longPressDialog.output?.name}</p>
          </div>
          <DialogFooter className="gap-2">
            <button 
              className="btn btn-ghost" 
              onClick={() => setLongPressDialog({ open: false, output: null, type: 'output' })}
            >
              {t('common.cancel')}
            </button>
            <button 
              className="btn btn-primary" 
              onClick={handleGoToSettings}
            >
              {t('outputs.go_to_settings')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
