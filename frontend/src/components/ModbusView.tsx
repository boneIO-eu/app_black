import { useContext, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from '@/api/axios';
import { WebSocketContext } from '../App';
import ViewToggle from './ViewToggle';
import { isModbusDeviceEvent, ModbusDeviceState } from '../hooks/useWebSocket';
import { useTranslation } from '../hooks/useTranslation';
import ModbusDeviceItem from './ModbusDeviceItem';
import { shouldRenderHistory, useModbusHistory } from '../hooks/useModbusHistory';
import { LongPressWrapper } from '@/components/ui/LongPressWrapper';
import { FaCog } from 'react-icons/fa';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

interface GroupedModbusDevices {
  groupKey: string;
  groupName: string;
  sensors: ModbusDeviceState[];
  writeable: ModbusDeviceState[];
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
  const navigate = useNavigate();
  const { modbus_devices } = useContext(WebSocketContext);
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('modbusViewMode');
    return saved ? saved === 'grid' : true;
  });
  const [error, setError] = useState<string | null>(null);

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

    const grouped = Array.from(byCoordinator.entries()).map(([coordId, devices]) => {
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

      return {
        groupKey: coordId,
        groupName,
        sensors,
        writeable,
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

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('modbusViewMode', gridView ? 'grid' : 'list');
  };

  const handleValueChange = async (coordinatorId: string, entityId: string, value: string | number) => {
    try {
      await axios.post(`/api/modbus/${coordinatorId}/${entityId}/set_value`, { value });
      setError(null);
    } catch (err: any) {
      console.error('Error setting modbus value:', err);
      setError(err.response?.data?.detail || t('modbus_view.error_setting_value'));
    }
  };

  // Long press dialog state
  const [longPressDialog, setLongPressDialog] = useState<{
    open: boolean;
    device: ModbusDeviceState | null;
  }>({
    open: false,
    device: null,
  });

  const handleLongPress = useCallback((device: ModbusDeviceState) => {
    setLongPressDialog({ open: true, device });
  }, []);

  const handleGoToSettings = useCallback(() => {
    if (!longPressDialog.device) return;
    // Use device name for matching config entries (coordinator_id is a runtime group id, not a config field)
    const editKey = longPressDialog.device.coordinator_id;
    navigate(`/settings/modbus_devices?edit=${encodeURIComponent(editKey)}`);
    setLongPressDialog({ open: false, device: null });
  }, [longPressDialog.device, navigate]);

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">{t('modbus_view.title')}</h2>
        <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
      </div>

      {error && (
        <div className="alert alert-error mb-4">
          <span>{error}</span>
        </div>
      )}

      {/* Grouped Modbus Devices */}
      {sortedGroupedEntries.length === 0 ? (
        <div className="text-center py-8 text-base-content/60">
          {t('modbus_view.no_devices')}
        </div>
      ) : (
        sortedGroupedEntries.map(({ groupKey, groupName, sensors, writeable }) => {
          return (
            <div key={groupKey} className="card bg-base-200/80 shadow-lg mb-6">
              <div className="card-body">
                <h3 className="card-title text-lg font-semibold text-base-content/80 mb-4">{groupName}</h3>

                {/* Sensors Section */}
                {sensors.length > 0 && (
                  <div className="mb-6">
                    <h4 className="text-md font-medium text-base-content/70 mb-3">{t('modbus_view.sensors')}</h4>
                    <div className={isGrid
                      ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
                      : "flex flex-col gap-4"
                    }>
                      {sensors.map((device) => (
                        <LongPressWrapper key={device.id} onLongPress={() => handleLongPress(device)} className={isGrid ? 'h-full' : undefined}>
                          <ModbusDeviceItem
                            device={device}
                            isGrid={isGrid}
                            historyPoints={shouldRenderHistory(device) ? (historyByDeviceId.get(device.id) || []) : undefined}
                            onValueChange={handleValueChange}
                          />
                        </LongPressWrapper>
                      ))}
                    </div>
                  </div>
                )}

                {/* Writeable Entities Section */}
                {writeable.length > 0 && (
                  <div>
                    <h4 className="text-md font-medium text-base-content/70 mb-3">{t('modbus_view.controls')}</h4>
                    <div className={isGrid
                      ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
                      : "flex flex-col gap-4"
                    }>
                      {writeable.map((device) => (
                        <LongPressWrapper key={device.id} onLongPress={() => handleLongPress(device)} className={isGrid ? 'h-full' : undefined}>
                          <ModbusDeviceItem
                            device={device}
                            isGrid={isGrid}
                            historyPoints={shouldRenderHistory(device) ? (historyByDeviceId.get(device.id) || []) : undefined}
                            onValueChange={handleValueChange}
                          />
                        </LongPressWrapper>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })
      )}

      {/* Long press dialog - go to settings */}
      <Dialog open={longPressDialog.open} onOpenChange={(open) => setLongPressDialog({ open, device: open ? longPressDialog.device : null })}>
        <DialogContent className="sm:max-w-md bg-base-200">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FaCog className="w-5 h-5" />
              {t('modbus_view.go_to_settings')}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p>{t('modbus_view.go_to_settings_confirm')}</p>
            <p className="font-semibold mt-2">{longPressDialog.device?.custom_label || longPressDialog.device?.name}</p>
            {longPressDialog.device?.coordinator_id && (
              <p className="text-sm text-base-content/60">{longPressDialog.device.coordinator_id}</p>
            )}
          </div>
          <DialogFooter className="gap-2">
            <button
              className="btn btn-ghost"
              onClick={() => setLongPressDialog({ open: false, device: null })}
            >
              {t('common.cancel')}
            </button>
            <button
              className="btn btn-primary"
              onClick={handleGoToSettings}
            >
              {t('modbus_view.go_to_settings')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
