import { useContext, useMemo, useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from '@/api/axios';
import type { AxiosError } from 'axios';
import { WebSocketContext } from '@/contexts/WebSocketContext';
import ViewToggle from './ViewToggle';
import { addGlobalMessageListener, isModbusDeviceEvent, isModbusStatusEvent, ModbusDeviceState } from '../hooks/useWebSocket';
import { useTranslation } from '../hooks/useTranslation';
import { useAuth } from '../hooks/useAuth';
import ModbusDeviceItem from './ModbusDeviceItem';
import { shouldRenderHistory, useModbusHistory } from '../hooks/useModbusHistory';
import { LongPressWrapper } from '@/components/ui/LongPressWrapper';
import { EntityGrid, EntityPanel, SENSOR_GRID_CLASS } from './EntityGrid';
import { FaCog, FaExclamationTriangle, FaMapMarkerAlt, FaSyncAlt } from 'react-icons/fa';
import EntityInfoCard from './entityCard/EntityInfoCard';
import GroupByAreaToggle from './GroupByAreaToggle';
import { useGroupByArea } from '@/hooks/useGroupByArea';
import { useAreas } from '@/hooks/useAreas';
import { groupByArea } from '@/utils/groupByArea';
import { Select as BaseSelect } from '@base-ui/react/select';
import { ChevronLeft, ChevronRight, ChevronsUpDown, Layers, Search, TriangleAlert } from 'lucide-react';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel } from '@/components/ui/select';

type ApiError = AxiosError<{ detail?: string }>;

interface GroupedModbusDevices {
  groupKey: string;
  groupName: string;
  area: string | null;
  sensors: ModbusDeviceState[];
  writeable: ModbusDeviceState[];
  accentColor: string;
  strokeColor: string;
  fillColor: string;
}

/** Rotating color palette for Modbus device groups */
const GROUP_COLORS = [
  { accentColor: 'border-blue-500',    strokeColor: '#3b82f6', fillColor: 'rgba(59, 130, 246, 0.10)' },
  { accentColor: 'border-emerald-500', strokeColor: '#10b981', fillColor: 'rgba(16, 185, 129, 0.10)' },
  { accentColor: 'border-amber-500',   strokeColor: '#f59e0b', fillColor: 'rgba(245, 158, 11, 0.10)' },
  { accentColor: 'border-rose-500',    strokeColor: '#f43f5e', fillColor: 'rgba(244, 63, 94, 0.10)' },
  { accentColor: 'border-violet-500',  strokeColor: '#8b5cf6', fillColor: 'rgba(139, 92, 246, 0.10)' },
  { accentColor: 'border-cyan-500',    strokeColor: '#06b6d4', fillColor: 'rgba(6, 182, 212, 0.10)' },
  { accentColor: 'border-orange-500',  strokeColor: '#f97316', fillColor: 'rgba(249, 115, 22, 0.10)' },
  { accentColor: 'border-pink-500',    strokeColor: '#ec4899', fillColor: 'rgba(236, 72, 153, 0.10)' },
];

/** Device picker values for every device and for the failing ones. */
const ALL = '__all__';
const FAILING = '__failing__';

// The device picker, styled as an iOS grouped list: on a phone the sheet is
// grey and each group a white card of rows; on a desktop it stays a dropdown.
const STEP_BUTTON_CLASS = 'grid place-items-center w-11 h-full shrink-0 text-base-content/60 outline-none transition-colors active:bg-base-200 first:rounded-l-2xl last:rounded-r-2xl focus-visible:bg-base-200';
const SHEET_GROUP_CLASS = '[&+&]:mt-0 [&+&]:border-t-0 [&+&]:pt-0 max-sm:mb-5 max-sm:last:mb-2 sm:[&+&]:mt-1 sm:[&+&]:border-t sm:[&+&]:pt-1';
const SHEET_CARD_CLASS = 'max-sm:overflow-hidden max-sm:rounded-2xl max-sm:bg-base-100';
const SHEET_LABEL_CLASS = 'px-4 pt-1 pb-2 sm:px-2 [&>span]:normal-case [&>span]:tracking-normal [&>span]:text-[13px] [&>span]:font-medium [&>span]:opacity-55';
const SHEET_ROW_CLASS = 'gap-3 rounded-lg pr-9 [&>*:last-child]:min-w-0 [&>*:last-child]:flex-1 [&_svg.lucide-check]:text-primary max-sm:rounded-none max-sm:px-4 max-sm:py-3.5 max-sm:pr-11 max-sm:after:absolute max-sm:after:right-0 max-sm:after:bottom-0 max-sm:after:left-12 max-sm:after:h-px max-sm:after:bg-base-content/8 max-sm:last:after:hidden';

type DeviceStatus = 'ok' | 'failing' | 'paused';

function StatusDot({ status }: { status: DeviceStatus }) {
  const color = status === 'failing' ? 'bg-error' : status === 'paused' ? 'bg-base-content/25' : 'bg-success';
  return <span className={`block size-2.5 rounded-full ${color}`} />;
}

function PickerRow({ icon, name, count }: { icon: React.ReactNode; name: string; count: number }) {
  return (
    <span className="flex w-full min-w-0 items-center gap-3">
      <span className="grid place-items-center size-5 shrink-0">{icon}</span>
      <span className="min-w-0 flex-1 truncate">{name}</span>
      <span className="shrink-0 tabular-nums text-sm text-base-content/45">{count}</span>
    </span>
  );
}

function matchesQuery(device: ModbusDeviceState, needle: string): boolean {
  return [device.custom_label, device.name, device.id].some(v => v?.toLowerCase().includes(needle));
}

function isWriteableDevice(device: ModbusDeviceState): boolean {
  return device.entity_type?.includes('select') || device.entity_type === 'switch' || device.entity_type === 'number';
}

function compareDevices(a: ModbusDeviceState, b: ModbusDeviceState): number {
  const byCoordinator = (a.coordinator_id || '').localeCompare(b.coordinator_id || '');
  if (byCoordinator !== 0) {
    return byCoordinator;
  }

  const isAWritable = isWriteableDevice(a);
  const isBWritable = isWriteableDevice(b);
  if (isAWritable !== isBWritable) {
    return isAWritable ? 1 : -1;
  }

  // Use immutable id for stable sorting; labels can change during runtime.
  return a.id.localeCompare(b.id);
}

export default function ModbusView() {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const { modbus_devices } = useContext(WebSocketContext);
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('modbusViewMode');
    return saved ? saved === 'grid' : true;
  });
  const [error, setError] = useState<string | null>(null);
  const [pollingState, setPollingState] = useState<Record<string, boolean>>({});
  const [failing, setFailing] = useState<Record<string, boolean>>({});
  // '' is every device, FAILING the failing ones, anything else one device.
  const [selected, setSelected] = useState(() => localStorage.getItem('modbusDevice') || '');
  const [query, setQuery] = useState('');

  // Fetch initial polling state from API
  useEffect(() => {
    // Subscribed before the fetch so a change in between is not lost; what
    // the socket has already said wins over the older snapshot.
    const unsubscribe = addGlobalMessageListener((data) => {
      if (isModbusStatusEvent(data)) {
        setFailing(prev => ({ ...prev, [data.entity_id]: data.failing }));
      }
    });
    const fetchPollingState = async () => {
      try {
        const { data } = await axios.get('/api/modbus/status');
        if (data.coordinators) {
          const state: Record<string, boolean> = {};
          const failingState: Record<string, boolean> = {};
          for (const [id, info] of Object.entries(data.coordinators)) {
            const { polling_enabled, failing } = info as { polling_enabled: boolean; failing?: boolean };
            state[id] = polling_enabled;
            failingState[id] = Boolean(failing);
          }
          setPollingState(state);
          setFailing(prev => ({ ...failingState, ...prev }));
        }
      } catch {
        // Non-critical — polling state defaults to enabled
      }
    };
    fetchPollingState();
    return unsubscribe;
  }, []);

  const handlePollingToggle = useCallback(async (coordinatorId: string, enabled: boolean) => {
    try {
      const { data } = await axios.post(`/api/modbus/${coordinatorId}/polling`, { enabled });
      setPollingState(prev => ({ ...prev, [coordinatorId]: data.polling_enabled }));
      setError(null);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      console.error('Error toggling polling:', err);
      setError(apiErr.response?.data?.detail || t('modbus_view.error_setting_value'));
    }
  }, [t]);

  const validModbusDevices = useMemo(
    () => modbus_devices.filter(isModbusDeviceEvent).map(e => e.state),
    [modbus_devices]
  );
  const historyByDeviceId = useModbusHistory(validModbusDevices, 300, 2 * 60 * 60);

  const sortedGroupedEntries = useMemo<GroupedModbusDevices[]>(() => {
    const sortedDevices = [...validModbusDevices].sort(compareDevices);
    const byCoordinator = new Map<string, ModbusDeviceState[]>();

    for (const device of sortedDevices) {
      const key = device.coordinator_id || t('modbus_view.other_group');
      const devices = byCoordinator.get(key);

      if (devices) {
        devices.push(device);
      } else {
        byCoordinator.set(key, [device]);
      }
    }

    const groupNameCount = new Map<string, number>();
    for (const [coordId, devices] of byCoordinator.entries()) {
      const baseName = devices[0]?.device_group || coordId;
      groupNameCount.set(baseName, (groupNameCount.get(baseName) || 0) + 1);
    }

    const grouped = Array.from(byCoordinator.entries()).map(([coordId, devices], index) => {
      const sensors: ModbusDeviceState[] = [];
      const writeable: ModbusDeviceState[] = [];

      for (const device of devices) {
        if (isWriteableDevice(device)) {
          writeable.push(device);
        } else {
          sensors.push(device);
        }
      }

      const baseName = devices[0]?.device_group || coordId;
      const duplicateCount = groupNameCount.get(baseName) || 0;
      const groupName = duplicateCount > 1 ? `${baseName} (${coordId})` : baseName;
      const color = GROUP_COLORS[index % GROUP_COLORS.length];

      return {
        groupKey: coordId,
        groupName,
        area: devices[0]?.area || null,
        sensors,
        writeable,
        ...color,
      };
    });

    return grouped.sort((a, b) => {
      const byName = a.groupName.localeCompare(b.groupName);
      if (byName !== 0) {
        return byName;
      }
      return a.groupKey.localeCompare(b.groupKey);
    });
  }, [validModbusDevices, t]);

  const areas = useAreas();
  const [groupedByArea, setGroupedByArea] = useGroupByArea('modbusGroupByArea', areas.length > 0);
  // By area, the picker and the arrows follow the page: area by area.
  const areaSections = useMemo(
    () => groupedByArea
      ? groupByArea(sortedGroupedEntries, g => g.area, areas)
      : [{ id: null, name: null, items: sortedGroupedEntries }],
    [groupedByArea, sortedGroupedEntries, areas],
  );
  const orderedGroups = useMemo(() => areaSections.flatMap(s => s.items), [areaSections]);

  // Filtered after grouping, so a device keeps its color and the history
  // above keeps every device's points while it is hidden.
  const activeSelected = selected === FAILING || sortedGroupedEntries.some(g => g.groupKey === selected) ? selected : '';
  const failingCount = sortedGroupedEntries.filter(g => failing[g.groupKey]).length;
  const visibleSections = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const visible = (group: GroupedModbusDevices): GroupedModbusDevices[] => {
      if (activeSelected === FAILING ? !failing[group.groupKey] : activeSelected && group.groupKey !== activeSelected) {
        return [];
      }
      if (!needle || group.groupName.toLowerCase().includes(needle)) {
        return [group];
      }
      const sensors = group.sensors.filter(d => matchesQuery(d, needle));
      const writeable = group.writeable.filter(d => matchesQuery(d, needle));
      return sensors.length || writeable.length ? [{ ...group, sensors, writeable }] : [];
    };
    return areaSections
      .map(section => ({ ...section, items: section.items.flatMap(visible) }))
      .filter(section => section.items.length > 0);
  }, [areaSections, activeSelected, failing, query]);

  // "Failing only" is not remembered: on a healthy system the next visit
  // would open on an empty page.
  const selectDevice = (key: string) => {
    setSelected(key);
    localStorage.setItem('modbusDevice', key === FAILING ? '' : key);
  };

  // From "all" or "failing" the arrows start at either end; past the last
  // device they wrap around.
  const stepDevice = (delta: 1 | -1) => {
    const keys = orderedGroups.map(g => g.groupKey);
    const index = keys.indexOf(activeSelected);
    const next = index === -1 ? (delta === 1 ? 0 : keys.length - 1) : (index + delta + keys.length) % keys.length;
    selectDevice(keys[next]);
  };

  const statusOf = (key: string): DeviceStatus =>
    failing[key] ? 'failing' : pollingState[key] === false ? 'paused' : 'ok';
  const areaNames = new Map(areas.map(a => [a.id, a.name || a.id]));
  const pickedGroup = sortedGroupedEntries.find(g => g.groupKey === activeSelected);
  const picked = pickedGroup ? {
    icon: <StatusDot status={statusOf(pickedGroup.groupKey)} />,
    title: pickedGroup.groupName,
    alert: Boolean(failing[pickedGroup.groupKey]),
    subtitle: failing[pickedGroup.groupKey]
      ? t('modbus_view.failing')
      : pickedGroup.area
        ? areaNames.get(pickedGroup.area) ?? pickedGroup.area
        : t('modbus_view.entities_count', { count: pickedGroup.sensors.length + pickedGroup.writeable.length }),
  } : activeSelected === FAILING ? {
    icon: <TriangleAlert className="size-4 text-error" />,
    title: t('modbus_view.only_failing'),
    alert: false,
    subtitle: t('modbus_view.devices_count', { count: failingCount }),
  } : {
    icon: <Layers className="size-4 text-base-content/60" />,
    title: t('modbus_view.all_devices'),
    alert: failingCount > 0,
    subtitle: failingCount > 0
      ? t('modbus_view.failing_count', { count: failingCount })
      : t('modbus_view.devices_count', { count: sortedGroupedEntries.length }),
  };

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('modbusViewMode', gridView ? 'grid' : 'list');
  };

  const handleValueChange = async (coordinatorId: string, entityId: string, value: string | number) => {
    try {
      await axios.post(`/api/modbus/${coordinatorId}/${entityId}/set_value`, { value });
      setError(null);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      console.error('Error setting modbus value:', err);
      setError(apiErr.response?.data?.detail || t('modbus_view.error_setting_value'));
    }
  };

  // Long-press card. It shows the entity live, so it opens for a viewer too;
  // only the settings entry behind ⋮ is for administrators. Only the id is
  // kept, so the card follows the value as it is polled.
  const [card, setCard] = useState<{ open: boolean; id: string | null }>({ open: false, id: null });
  const cardDevice = card.id ? validModbusDevices.find(d => d.id === card.id) : undefined;
  const cardGroup = cardDevice ? sortedGroupedEntries.find(g => g.groupKey === (cardDevice.coordinator_id || t('modbus_view.other_group'))) : undefined;
  const closeCard = useCallback(() => setCard(prev => ({ ...prev, open: false })), []);

  const handleLongPress = useCallback((device: ModbusDeviceState) => {
    setCard({ open: true, id: device.id });
  }, []);

  const handleGoToSettings = useCallback(() => {
    if (!cardDevice) return;
    // Use device name for matching config entries (coordinator_id is a runtime group id, not a config field)
    const editKey = cardDevice.coordinator_id;
    navigate(`/settings/modbus_devices?edit=${encodeURIComponent(editKey)}`);
    closeCard();
  }, [cardDevice, navigate, closeCard]);

  return (
    <div className="container mx-auto p-4">
      {/* No panel around the list: the page is a tinted field and the
          entities are the cards on it. */}
      <div>
        <div className="flex flex-col gap-2">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold tracking-tight">{t('modbus_view.title')}</h2>
            <div className="flex items-center gap-2">
              {areas.length > 0 && (
                <GroupByAreaToggle active={groupedByArea} onToggle={setGroupedByArea} />
              )}
              <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
            </div>
          </div>

          {error && (
            <div className="alert alert-error mb-4">
              <span>{error}</span>
            </div>
          )}

          {sortedGroupedEntries.length > 0 && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
              <div className="flex items-stretch h-14 min-w-0 sm:flex-1 rounded-2xl bg-base-100 ring-1 ring-base-content/8 shadow-sm">
                <button
                  className={STEP_BUTTON_CLASS}
                  onClick={() => stepDevice(-1)}
                  title={t('modbus_view.previous_device')}
                  aria-label={t('modbus_view.previous_device')}
                >
                  <ChevronLeft className="size-5" />
                </button>
                <Select value={activeSelected || ALL} onValueChange={(v) => selectDevice(v === ALL ? '' : v)}>
                  <BaseSelect.Trigger
                    aria-label={t('modbus_view.device')}
                    className="flex flex-1 min-w-0 items-center gap-3 px-3 border-x border-base-content/8 text-left outline-none transition-colors active:bg-base-200 focus-visible:bg-base-200"
                  >
                    <span className="grid place-items-center size-5 shrink-0">{picked.icon}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-semibold leading-tight">{picked.title}</span>
                      <span className={`block truncate text-xs leading-tight mt-0.5 ${picked.alert ? 'text-error' : 'text-base-content/55'}`}>
                        {picked.subtitle}
                      </span>
                    </span>
                    <ChevronsUpDown className="size-4 shrink-0 text-base-content/40" />
                  </BaseSelect.Trigger>
                  <SelectContent className="sm:min-w-[320px] sm:rounded-2xl sm:p-1.5 sm:shadow-xl max-sm:!bg-base-300 max-sm:!border-0 max-sm:!rounded-t-[28px]">
                    <SelectGroup className={SHEET_GROUP_CLASS}>
                      <div className={SHEET_CARD_CLASS}>
                        <SelectItem value={ALL} label={t('modbus_view.all_devices')} className={SHEET_ROW_CLASS}>
                          <PickerRow icon={<Layers className="size-4 text-base-content/60" />} name={t('modbus_view.all_devices')} count={sortedGroupedEntries.length} />
                        </SelectItem>
                        <SelectItem value={FAILING} label={t('modbus_view.only_failing')} className={SHEET_ROW_CLASS}>
                          <PickerRow
                            icon={<TriangleAlert className={`size-4 ${failingCount ? 'text-error' : 'text-base-content/40'}`} />}
                            name={t('modbus_view.only_failing')}
                            count={failingCount}
                          />
                        </SelectItem>
                      </div>
                    </SelectGroup>
                    {areaSections.map(section => (
                      <SelectGroup key={section.id ?? ''} className={SHEET_GROUP_CLASS}>
                        {groupedByArea && (
                          <SelectLabel className={SHEET_LABEL_CLASS}>{section.name ?? t('common.without_area')}</SelectLabel>
                        )}
                        <div className={SHEET_CARD_CLASS}>
                          {section.items.map(g => (
                            <SelectItem key={g.groupKey} value={g.groupKey} label={g.groupName} className={SHEET_ROW_CLASS}>
                              <PickerRow icon={<StatusDot status={statusOf(g.groupKey)} />} name={g.groupName} count={g.sensors.length + g.writeable.length} />
                            </SelectItem>
                          ))}
                        </div>
                      </SelectGroup>
                    ))}
                  </SelectContent>
                </Select>
                <button
                  className={STEP_BUTTON_CLASS}
                  onClick={() => stepDevice(1)}
                  title={t('modbus_view.next_device')}
                  aria-label={t('modbus_view.next_device')}
                >
                  <ChevronRight className="size-5" />
                </button>
              </div>
              <label className="flex items-center gap-2 h-10 sm:h-14 sm:w-72 px-3.5 rounded-xl sm:rounded-2xl bg-base-content/6 focus-within:ring-2 focus-within:ring-primary/40">
                <Search className="size-4 shrink-0 text-base-content/45" />
                <input
                  type="search"
                  className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-base-content/45"
                  placeholder={t('modbus_view.search_placeholder')}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
            </div>
          )}

          {/* Grouped Modbus Devices */}
          {sortedGroupedEntries.length === 0 ? (
            <div className="text-center py-8 text-base-content/60">
              {t('modbus_view.no_devices')}
            </div>
          ) : visibleSections.length === 0 ? (
            <div className="text-center py-8 text-base-content/60">
              {t('modbus_view.no_matches')}
            </div>
          ) : (
            visibleSections.map(section => (
              <div key={section.id ?? ''}>
                {groupedByArea && (
                  <h3 className="flex items-center gap-1.5 mb-2 text-sm font-semibold text-base-content/60">
                    <FaMapMarkerAlt className="w-3 h-3" />
                    {section.name ?? t('common.without_area')}
                  </h3>
                )}
                {section.items.map(({ groupKey, groupName, sensors, writeable, accentColor, strokeColor, fillColor }) => {
                  return (
                  /* One panel per device: the thing you reason about here is
                     "what is this meter doing", and its sensors and controls
                     are two lists inside that, not two peers of it. */
                  <EntityPanel
                    key={groupKey}
                    title={
                      <>
                        {failing[groupKey] && (
                          <FaExclamationTriangle className="w-3.5 h-3.5 shrink-0 text-error" title={t('modbus_view.failing')} />
                        )}
                        <span className="wrap-break-word min-w-0">{groupName}</span>
                      </>
                    }
                    action={
                      <label
                        className="flex items-center gap-1.5 cursor-pointer shrink-0"
                        title={pollingState[groupKey] === false ? t('modbus_view.polling_disabled') : t('modbus_view.polling_enabled')}
                      >
                        <FaSyncAlt className={`w-3 h-3 transition-colors ${
                          pollingState[groupKey] === false ? 'text-base-content/30' : 'text-success'
                        }`} />
                        <input
                          type="checkbox"
                          className="toggle toggle-xs toggle-success"
                          checked={pollingState[groupKey] !== false}
                          onChange={(e) => handlePollingToggle(groupKey, e.target.checked)}
                        />
                      </label>
                    }
                  >

                    {/* Sensors Section */}
                    {sensors.length > 0 && (
                      <>
                        {writeable.length > 0 && (
                          <p className="text-xs font-medium text-base-content/50 mb-2">
                            {t('modbus_view.sensors')}
                          </p>
                        )}
                        <EntityGrid isGrid={isGrid} gridClassName={SENSOR_GRID_CLASS}>
                          {sensors.map((device) => (
                            <LongPressWrapper key={device.id} onLongPress={() => handleLongPress(device)} className={isGrid ? 'h-full' : undefined}>
                              <ModbusDeviceItem
                                device={device}
                                isGrid={isGrid}
                                historyPoints={shouldRenderHistory(device) ? (historyByDeviceId.get(device.id) || []) : undefined}
                                onValueChange={handleValueChange}
                                accentColor={accentColor}
                                strokeColor={strokeColor}
                                fillColor={fillColor}
                              />
                            </LongPressWrapper>
                          ))}
                        </EntityGrid>
                      </>
                    )}

                    {/* Writeable Entities Section */}
                    {writeable.length > 0 && (
                      <>
                        <p className="text-xs font-medium text-base-content/50 mt-4 mb-2">
                          {t('modbus_view.controls')}
                        </p>
                        <EntityGrid isGrid={isGrid} gridClassName={SENSOR_GRID_CLASS}>
                          {writeable.map((device) => (
                            <LongPressWrapper key={device.id} onLongPress={() => handleLongPress(device)} className={isGrid ? 'h-full' : undefined}>
                              <ModbusDeviceItem
                                device={device}
                                isGrid={isGrid}
                                historyPoints={shouldRenderHistory(device) ? (historyByDeviceId.get(device.id) || []) : undefined}
                                onValueChange={handleValueChange}
                                accentColor={accentColor}
                                strokeColor={strokeColor}
                                fillColor={fillColor}
                              />
                            </LongPressWrapper>
                          ))}
                        </EntityGrid>
                      </>
                    )}
                  </EntityPanel>
                );
              })}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Long-press card: the entity with room for its graph and controls */}
      {cardDevice && (
        <EntityInfoCard
          open={card.open}
          onOpenChange={(open) => !open && closeCard()}
          icon={<FaCog className="text-base-content/50" />}
          title={cardDevice.custom_label || cardDevice.name}
          subtitle={[cardGroup?.groupName, cardDevice.id].filter(Boolean).join(' · ')}
          menu={isAdmin ? [{ key: 'settings', label: t('modbus_view.go_to_settings'), icon: <FaCog />, onSelect: handleGoToSettings }] : []}
          maxWidthClass="sm:max-w-xl"
        >
          <ModbusDeviceItem
            device={cardDevice}
            isGrid
            historyPoints={shouldRenderHistory(cardDevice) ? (historyByDeviceId.get(cardDevice.id) || []) : undefined}
            onValueChange={handleValueChange}
            accentColor={cardGroup?.accentColor}
            strokeColor={cardGroup?.strokeColor}
            fillColor={cardGroup?.fillColor}
          />
        </EntityInfoCard>
      )}
    </div>
  );
}
