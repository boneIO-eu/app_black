import { useState, useContext, useMemo, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from '@/api/axios';
import { WebSocketContext } from '@/contexts/WebSocketContext';
import ViewToggle from './ViewToggle';
import { isOutputEvent, isCoverEvent, isGroupEvent, CoverState, GroupState, OutputState } from '../hooks/useWebSocket';
import EntityCard from './EntityCard';
import type { EntityData } from './EntityCard';
import { EntityGrid, EntityPanel, ENTITY_GRID_CLASS, ENTITY_LIST_CLASS } from './EntityGrid';
import GroupByAreaToggle from './GroupByAreaToggle';
import { useGroupByArea } from '@/hooks/useGroupByArea';
import { useAreas } from '@/hooks/useAreas';
import { groupByArea } from '@/utils/groupByArea';
import CoverItem from './CoverItem';
import { useTranslation } from '../hooks/useTranslation';
import { useAuth } from '../hooks/useAuth';
import { FaExclamationTriangle, FaSortAmountDown, FaSortAlphaDown, FaClock, FaCog, FaWifi } from 'react-icons/fa';
import { HiSignal } from 'react-icons/hi2';
import MqttReferenceSheet from '@/components/MqttReferenceSheet';
import { cn } from '@/lib/utils';
import { MdBlinds, MdBlindsClosed } from 'react-icons/md';
import EntityInfoCard, { type EntityCardMenuItem } from './entityCard/EntityInfoCard';
import { OutputCardBody } from './entityCard/bodies';
import { historyFormatters } from './entityCard/format';
import { getIconAndOnColor } from './EntityCard';
import { historyKey } from '@/utils/entityHistory';

import type { OutputCategory, SortMode } from '@/types/outputs';

/** One entry of `/api/remote-devices/all`, as far as this view reads it. */
interface RemoteDeviceStatus {
  id: string;
  name: string;
  protocol?: string;
  outputs?: Array<{ id: string; name: string; state: string; type?: string }>;
  covers?: Array<{
    id: string;
    name: string;
    state: string;
    position?: number;
    kind?: string;
    tilt?: number;
    current_operation?: string;
  }>;
}

/** One tile of the by-area view: the three kinds share a room's panel. */
type AreaTile =
  | { kind: 'output'; output: OutputState; stateOnly: boolean }
  | { kind: 'group'; group: GroupState }
  | { kind: 'cover'; cover: CoverState };

/** Tile order inside an area: the same order the category sections use. */
const AREA_TILE_CATEGORIES: OutputCategory[] = ['light', 'switch', 'virtual_switch', 'valve'];

/**
 * Categorize output by its type
 */
function categorizeOutput(type: string | undefined): OutputCategory {
  const typeStr = (type || '').toLowerCase();
  
  if (typeStr === 'virtual_switch') return 'virtual_switch';
  if (typeStr === 'light') return 'light';
  if (typeStr === 'valve') return 'valve';
  if (typeStr === 'cover' || typeStr === 'none') return 'state_only';
  // Default to switch for relay, switch, or unknown types
  return 'switch';
}

export default function OutputsView({error}: {error: string | null}) {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
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
  const areas = useAreas();
  const [groupedByArea, setGroupedByArea] = useGroupByArea('outputGroupByArea', areas.length > 0);
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
      virtual_switch: t('outputs.categories.virtual_switches'),
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
  const [remoteDevices, setRemoteDevices] = useState<RemoteDeviceStatus[]>([]);

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
        device.outputs.forEach((out) => {
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
      virtual_switch: [],
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
        device.covers.forEach((cov) => {
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

  // Long-press card. Only which entity it is about: the entity itself is
  // looked up on every render, so the card follows it live.
  const [card, setCard] = useState<{
    open: boolean;
    id: string | null;
    type: 'output' | 'output_group' | 'cover' | 'remote_outputs';
  }>({
    open: false,
    id: null,
    type: 'output'
  });

  const handleLongPress = useCallback((output: EntityData) => {
    setCard({ open: true, id: output.id, type: 'output' });
  }, []);

  const handleGroupLongPress = useCallback((output: EntityData) => {
    setCard({ open: true, id: output.id, type: 'output_group' });
  }, []);

  const handleCoverLongPress = useCallback((cover: CoverState) => {
    setCard({ open: true, id: cover.id, type: 'cover' });
  }, []);

  const handleRemoteOutputLongPress = useCallback((output: EntityData) => {
    setCard({ open: true, id: output.id, type: 'remote_outputs' });
  }, []);

  const closeCard = useCallback(() => setCard(prev => ({ ...prev, open: false })), []);

  const handleGoToSettings = useCallback(() => {
    if (!card.id) return;
    // A virtual switch is drawn and long-pressed as an output, but it is
    // configured in a section of its own.
    const section = card.type === 'output'
      && categorizedOutputs.virtual_switch.some(o => o.id === card.id)
      ? 'virtual_switch'
      : card.type;
    navigate(`/settings/${section}?edit=${encodeURIComponent(card.id)}`);
    closeCard();
  }, [card.id, card.type, categorizedOutputs, navigate, closeCard]);

  // MQTT Reference dialog state
  const [mqttRef, setMqttRef] = useState<{
    open: boolean;
    entityType: string;
    entityId: string;
    entityName: string;
  }>({ open: false, entityType: '', entityId: '', entityName: '' });

  const handleOpenMqttRef = useCallback((name: string) => {
    if (!card.id) return;
    setMqttRef({
      open: true,
      entityType: card.type,
      entityId: card.id,
      entityName: name,
    });
    closeCard();
  }, [card.id, card.type, closeCard]);

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

      // A virtual switch has no relay and no interlock, so it takes its own
      // endpoint rather than pretending to be an output that happens to work.
      if (type === 'virtual_switch') {
        await axios.post(`/api/virtual_switch/${id}/toggle`);
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



  const areaNames = useMemo(() => new Map(areas.map((a) => [a.id, a.name])), [areas]);
  const areaLabelOf = (area: string | null | undefined) =>
    groupedByArea ? null : (area ? areaNames.get(area) || area : undefined);

  const renderOutputCard = (output: OutputState, isStateOnly = false) => (
    <EntityCard
      key={output.id}
      output={output}
      onToggle={isStateOnly ? undefined : toggleOutput}
      onDurationChange={handleDurationChange}
      onBrightnessChange={handleBrightnessChange}
      isGrid={isGrid}
      error={error}
      stateOnly={isStateOnly}
      isHighlighted={recentlyChanged.has(output.id)}
      onLongPress={handleLongPress}
      areaLabel={areaLabelOf(output.area)}
    />
  );

  const renderGroupCard = (group: GroupState) => (
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
      areaLabel={areaLabelOf(group.area)}
    />
  );

  const renderCoverCard = (cover: CoverState) => (
    <CoverItem
      key={cover.id}
      cover={cover}
      action={actionCover}
      isGrid={isGrid}
      error={error}
      onLongPress={handleCoverLongPress}
    />
  );

  // Everything local, room by room. Remote (CAN) outputs carry no area and
  // keep their own panel either way.
  const areaGroups = useMemo(() => {
    if (!groupedByArea) return [];
    const tiles: AreaTile[] = [
      ...AREA_TILE_CATEGORIES.flatMap((category) =>
        categorizedOutputs[category].map((output): AreaTile => ({ kind: 'output', output, stateOnly: false })),
      ),
      ...validGroups.map((group): AreaTile => ({ kind: 'group', group })),
      ...stateOnlyOutputs.map((output): AreaTile => ({ kind: 'output', output, stateOnly: true })),
      ...validCovers.map((cover): AreaTile => ({ kind: 'cover', cover })),
    ];
    return groupByArea(
      tiles,
      (tile) => (tile.kind === 'output' ? tile.output.area : tile.kind === 'group' ? tile.group.area : tile.cover.area),
      areas,
    );
  }, [groupedByArea, categorizedOutputs, validGroups, stateOnlyOutputs, validCovers, areas]);

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
        <EntityGrid isGrid={isGrid} title={getCategoryLabel(category)}>
          {items.map((output) => renderOutputCard(output, isStateOnly || !onToggle))}
        </EntityGrid>
      </div>
    );
  };

  /**
   * The long-press card for whatever `card` points at, drawn from the same
   * lists the tiles are, so it moves when the tile does.
   */
  const renderCard = () => {
    if (!card.id) return null;
    const allOutputs = [...Object.values(categorizedOutputs).flat(), ...remoteOutputs];

    const menu: EntityCardMenuItem[] = [];
    const addMenu = (name: string) => {
      menu.push({
        key: 'mqtt',
        label: t('mqtt_reference.button'),
        icon: <HiSignal />,
        onSelect: () => handleOpenMqttRef(name),
      });
      // Hidden for a read-only account: the route refuses it, and a
      // button that leads to "administrators only" is a button that
      // should not have been offered.
      if (isAdmin) {
        menu.push({ key: 'settings', label: t('outputs.go_to_settings'), icon: <FaCog />, onSelect: handleGoToSettings });
      }
    };

    if (card.type === 'cover') {
      const cover = validCovers.find(c => c.id === card.id);
      if (!cover) return null;
      addMenu(cover.name);
      const CoverIcon = cover.state === 'open' ? MdBlinds : MdBlindsClosed;
      return (
        <EntityInfoCard
          open={card.open}
          onOpenChange={(open) => !open && closeCard()}
          icon={<CoverIcon className={cover.state === 'open' ? 'text-yellow-400' : 'text-base-content/40'} />}
          title={cover.name}
          subtitle={[cover.id, cover.area].filter(Boolean).join(' · ')}
          menu={menu}
          historyKey={historyKey('cover', cover.id)}
          formatValue={historyFormatters.cover(t)}
        >
          <CoverItem cover={cover} action={actionCover} isGrid error={error} embedded />
        </EntityInfoCard>
      );
    }

    const isGroup = card.type === 'output_group';
    const output: EntityData | undefined = isGroup
      ? validGroups
        .filter(g => g.id === card.id)
        .map(g => ({ id: g.id, name: g.name, state: g.state, type: g.type, timestamp: g.timestamp, area: null, interlock_groups: [] }))[0]
      : allOutputs.find(o => o.id === card.id);
    if (!output) return null;
    addMenu(output.name);
    const { Icon, onColor } = getIconAndOnColor(output.type, isGroup);
    const stateOnly = !isGroup && categorizeOutput(output.type) === 'state_only';
    return (
      <EntityInfoCard
        open={card.open}
        onOpenChange={(open) => !open && closeCard()}
        icon={<Icon className={output.state === 'ON' ? onColor : 'text-base-content/40'} />}
        title={output.name}
        subtitle={[output.id, output.area].filter(Boolean).join(' · ')}
        menu={menu}
        historyKey={historyKey(isGroup ? 'group' : 'output', output.id)}
        formatValue={historyFormatters.output(t)}
      >
        <OutputCardBody
          output={output}
          onToggle={isGroup ? toggleGroup : toggleOutput}
          onDurationChange={handleDurationChange}
          onBrightnessChange={handleBrightnessChange}
          error={error}
          stateOnly={stateOnly}
        />
      </EntityInfoCard>
    );
  };

  return (
    <div className="container mx-auto p-4">
      {/* No panel around the list any more. The page is a tinted field and
          the entities are the cards on it — one surface less to look
          through, and the same rule the settings screens follow. */}
      <div>
        <div className="flex flex-col gap-2">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold tracking-tight">{t('outputs.title')}</h2>
            <div className="flex items-center gap-2">
              {/* Sort dropdown */}
              <div className="dropdown dropdown-end">
                <label tabIndex={0} className="btn btn-sm gap-1">
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
              {areas.length > 0 && (
                <GroupByAreaToggle active={groupedByArea} onToggle={setGroupedByArea} />
              )}
              <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
            </div>
          </div>

          {groupedByArea && areaGroups.map((group) => {
            const tiles = group.items.filter((tile) => tile.kind !== 'cover');
            const areaCovers = group.items.flatMap((tile) => (tile.kind === 'cover' ? [tile.cover] : []));
            return (
              <EntityPanel key={group.id ?? ''} title={group.name ?? t('common.without_area')}>
                {tiles.length > 0 && (
                  <div className={isGrid ? ENTITY_GRID_CLASS : ENTITY_LIST_CLASS}>
                    {tiles.map((tile) =>
                      tile.kind === 'group'
                        ? renderGroupCard(tile.group)
                        : tile.kind === 'output'
                          ? renderOutputCard(tile.output, tile.stateOnly)
                          : null,
                    )}
                  </div>
                )}
                {areaCovers.length > 0 && (
                  <div className={cn(isGrid ? cn(ENTITY_GRID_CLASS, 'grid-cols-1') : ENTITY_LIST_CLASS, tiles.length > 0 && 'mt-4')}>
                    {areaCovers.map(renderCoverCard)}
                  </div>
                )}
              </EntityPanel>
            );
          })}

          {!groupedByArea && (<>
          {/* Lights */}
          {renderOutputSection('light', categorizedOutputs.light, toggleOutput)}

          {/* Switches */}
          {renderOutputSection('switch', categorizedOutputs.switch, toggleOutput)}

          {/* Modes and flags. After the relays: they are what the relays are
              conditioned on, not another thing the board drives. */}
          {renderOutputSection('virtual_switch', categorizedOutputs.virtual_switch, toggleOutput)}

          {/* Valves */}
          {renderOutputSection('valve', categorizedOutputs.valve, toggleOutput)}

          {/* Covers */}
          {validCovers.length > 0 && (
            <>
              <EntityGrid
                isGrid={isGrid}
                title={getCategoryLabel('cover')}
                gridClassName={cn(ENTITY_GRID_CLASS, "grid-cols-1")}
              >
                {validCovers.map(renderCoverCard)}
              </EntityGrid>
            </>
          )}

          {/* Groups */}
          {validGroups.length > 0 && (
            <>
              <EntityGrid isGrid={isGrid} title={getCategoryLabel('group')}>
                {validGroups.map(renderGroupCard)}
              </EntityGrid>
            </>
          )}

          {/* State Only (cover or none type outputs - no controls) */}
          {renderOutputSection('state_only', stateOnlyOutputs, toggleOutput, true)}
          </>)}

          {/* Remote Outputs */}
          {remoteOutputs.length > 0 && (
            <>
              <EntityGrid
                isGrid={isGrid}
                title={
                  <>
                    <FaWifi className="text-primary" />
                    {t('sections.remote_outputs')}
                  </>
                }
              >
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

      {/* Long-press card: live state, controls, recent events; the rest behind ⋮ */}
      {renderCard()}

      {/* MQTT Reference Sheet */}
      <MqttReferenceSheet
        open={mqttRef.open}
        onOpenChange={(open) => setMqttRef(prev => ({ ...prev, open }))}
        entityType={mqttRef.entityType}
        entityId={mqttRef.entityId}
        entityName={mqttRef.entityName}
      />
    </div>
  );
}
