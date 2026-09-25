/**
 * useItemActions - Hook for finding and removing orphaned actions
 * when deleting outputs, covers, areas, or remote devices.
 */
import { useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import type {
  BinarySensorActions,
  BinarySensorEntity,
  CoverEntity,
  EventActions,
  EventEntity,
  OutputEntity,
} from '@/types/config';
import type { ConfigRecord } from '@/types/jsonSchema';
import type { OutputGroupRecord } from '../ActionFields/types';

interface AffectedAction {
  type: string;
  name: string;
  actionType: string;
}

/** The fields of a group / sensor / modbus / virtual energy entry read here. */
type AreaItem = {
  id?: string;
  name?: string;
  area?: string;
  address?: string;
  model?: string;
};

interface UseItemActionsProps {
  allEvents: EventEntity[];
  allBinarySensors: BinarySensorEntity[];
  allOutputs: OutputEntity[];
  allOutputGroups: OutputGroupRecord[];
  allCovers: CoverEntity[];
  allSensors: ConfigRecord[];
  allModbusDevices: ConfigRecord[];
  allVirtualEnergySensors: ConfigRecord[];
  onUpdateEvents?: (newEvents: EventEntity[]) => void;
  onUpdateBinarySensors?: (newBinarySensors: BinarySensorEntity[]) => void;
}

/**
 * Hook providing action lookup and orphan cleanup for cross-section references.
 */
export function useItemActions({
  allEvents,
  allBinarySensors,
  allOutputs,
  allOutputGroups,
  allCovers,
  allSensors,
  allModbusDevices,
  allVirtualEnergySensors,
  onUpdateEvents,
  onUpdateBinarySensors,
}: UseItemActionsProps) {
  const { t } = useTranslation();

  /**
   * Find all items that use the given area ID.
   */
  const findItemsUsingArea = useCallback((areaId: string): AffectedAction[] => {
    const affected: AffectedAction[] = [];

    allOutputs.forEach((item) => {
      if (item.area === areaId) {
        affected.push({
          type: t('navigation.outputs'),
          name: item.id || item.name || item.boneio_output || t('array_table_widget.unknown'),
          actionType: item.boneio_output || ''
        });
      }
    });

    (allOutputGroups as AreaItem[]).forEach((item) => {
      if (item.area === areaId) {
        affected.push({
          type: t('outputs.output_group'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: ''
        });
      }
    });

    allCovers.forEach((item) => {
      if (item.area === areaId) {
        affected.push({
          type: t('covers.title'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: `${item.open_relay} / ${item.close_relay}`
        });
      }
    });

    allBinarySensors.forEach((item) => {
      if (item.area === areaId) {
        affected.push({
          type: t('navigation.inputs'),
          name: item.name || item.boneio_input || t('array_table_widget.unknown'),
          actionType: item.boneio_input || ''
        });
      }
    });

    allEvents.forEach((item) => {
      if (item.area === areaId) {
        affected.push({
          type: t('event_form.title'),
          name: item.name || item.boneio_input || t('array_table_widget.unknown'),
          actionType: item.boneio_input || ''
        });
      }
    });

    (allSensors as AreaItem[]).forEach((item) => {
      if (item.area === areaId) {
        affected.push({
          type: t('navigation.sensors'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: item.address || ''
        });
      }
    });

    (allModbusDevices as AreaItem[]).forEach((item) => {
      if (item.area === areaId) {
        affected.push({
          type: t('navigation.modbus'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: `${item.model} @ ${item.address}`
        });
      }
    });

    (allVirtualEnergySensors as AreaItem[]).forEach((item) => {
      if (item.area === areaId) {
        affected.push({
          type: t('virtual_energy_sensor.title'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: ''
        });
      }
    });

    return affected;
  }, [allOutputs, allOutputGroups, allCovers, allBinarySensors, allEvents, allSensors, allModbusDevices, allVirtualEnergySensors, t]);

  /**
   * Find all actions in events and binary_sensors that reference the given item ID.
   * For remote_devices, checks remote_device field in remote_output and remote_cover actions.
   */
  const findAffectedActions = useCallback((itemId: string, isRemoteDevice: boolean = false): AffectedAction[] => {
    const affected: AffectedAction[] = [];

    allEvents.forEach((event) => {
      const eventName = event.name || event.boneio_input || t('array_table_widget.unknown_event');
      ['single', 'double', 'long'].forEach((pressType) => {
        const actions = event.actions?.[pressType] || [];
        actions.forEach((action) => {
          if (isRemoteDevice) {
            if (action.remote_device === itemId) {
              affected.push({
                type: t('array_table_widget.event'),
                name: eventName,
                actionType: `${pressType} → ${action.action || 'remote_output'}`
              });
            }
          } else {
            if (action.pin === itemId || action.boneio_output === itemId) {
              affected.push({
                type: t('array_table_widget.event'),
                name: eventName,
                actionType: `${pressType} → ${action.action || 'output'}`
              });
            }
          }
        });
      });
    });

    allBinarySensors.forEach((sensor) => {
      const sensorName = sensor.name || sensor.boneio_input || t('array_table_widget.unknown_sensor');
      ['pressed', 'released'].forEach((pressType) => {
        const actions = sensor.actions?.[pressType] || [];
        actions.forEach((action) => {
          if (isRemoteDevice) {
            if (action.remote_device === itemId) {
              affected.push({
                type: t('array_table_widget.binary_sensor'),
                name: sensorName,
                actionType: `${pressType} → ${action.action || 'remote_output'}`
              });
            }
          } else {
            if (action.pin === itemId || action.boneio_output === itemId) {
              affected.push({
                type: t('array_table_widget.binary_sensor'),
                name: sensorName,
                actionType: `${pressType} → ${action.action || 'output'}`
              });
            }
          }
        });
      });
    });

    return affected;
  }, [allEvents, allBinarySensors, t]);

  /**
   * Remove actions that reference the given item ID from events and binary_sensors.
   * Returns the updated data for immediate saving.
   */
  const removeOrphanedActions = useCallback((itemId: string, isRemoteDevice: boolean = false): { updatedEvents: EventEntity[] | null, updatedSensors: BinarySensorEntity[] | null } => {
    let updatedEvents: EventEntity[] | null = null;
    let updatedSensors: BinarySensorEntity[] | null = null;

    if (onUpdateEvents) {
      updatedEvents = allEvents.map((event) => {
        const updatedActions: EventActions = {};
        ['single', 'double', 'long'].forEach((pressType) => {
          const actions = event.actions?.[pressType] || [];
          updatedActions[pressType] = actions.filter((action) => {
            if (isRemoteDevice) return action.remote_device !== itemId;
            return action.pin !== itemId && action.boneio_output !== itemId;
          });
        });
        return { ...event, actions: updatedActions };
      });
      onUpdateEvents(updatedEvents);
    }

    if (onUpdateBinarySensors) {
      updatedSensors = allBinarySensors.map((sensor) => {
        const updatedActions: BinarySensorActions = {};
        ['pressed', 'released'].forEach((pressType) => {
          const actions = sensor.actions?.[pressType] || [];
          updatedActions[pressType] = actions.filter((action) => {
            if (isRemoteDevice) return action.remote_device !== itemId;
            return action.pin !== itemId && action.boneio_output !== itemId;
          });
        });
        return { ...sensor, actions: updatedActions };
      });
      onUpdateBinarySensors(updatedSensors);
    }

    return { updatedEvents, updatedSensors };
  }, [allEvents, allBinarySensors, onUpdateEvents, onUpdateBinarySensors]);

  return { findItemsUsingArea, findAffectedActions, removeOrphanedActions };
}

export type { AffectedAction };
