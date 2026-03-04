import React, { useState, useEffect, useRef } from 'react';
import axios from '@/api/axios';
import { FaPlus, FaDownload, FaUpload } from 'react-icons/fa';
import * as yaml from 'js-yaml';
import { useTranslation } from '../../hooks/useTranslation';
import BinarySensorForm from './BinarySensorForm';
import EventForm from './EventForm';
import OutputForm from './OutputForm';
import OutputGroupForm from './OutputGroupForm';
import CoverForm from './CoverForm';
import ModbusDeviceForm from './ModbusDeviceForm';
import AreasForm from './AreasForm';
import SensorForm from './SensorForm';
import VirtualEnergySensorForm from './VirtualEnergySensorForm';
import RemoteDeviceForm from './RemoteDeviceForm';
import TemplateForm from './TemplateForm';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import AreasTable from './tables/AreasTable';
import OutputTable from './tables/OutputTable';
import OutputGroupTable from './tables/OutputGroupTable';
import CoverTable from './tables/CoverTable';
import BinarySensorEventTable from './tables/BinarySensorEventTable';
import ModbusDeviceTable from './tables/ModbusDeviceTable';
import SensorTable from './tables/SensorTable';
import VirtualEnergySensorTable from './tables/VirtualEnergySensorTable';
import RemoteDeviceTable from './tables/RemoteDeviceTable';
import TemplateTable from './tables/TemplateTable';
import GenericTable from './tables/GenericTable';

interface Area {
  id: string;
  name: string;
}

export interface ArrayTableWidgetProps {
  value: any[];
  onChange: (value: any[]) => void;
  schema: any;
  title?: string;
  uiSchema?: any;
  sectionType?: 'binary_sensor' | 'event' | 'output' | 'output_group' | 'cover' | 'modbus_devices' | 'areas' | 'sensor' | 'virtual_energy_sensor' | 'remote_devices' | 'template' | 'other';
  deviceType?: string;
  allBinarySensors?: any[];
  allEvents?: any[];
  allOutputs?: any[];
  allOutputGroups?: any[];
  allCovers?: any[];
  allAreas?: Area[];
  allSensors?: any[];
  allModbusDevices?: any[];
  allVirtualEnergySensors?: any[];
  allRemoteDevices?: any[];
  /** Saved (committed) data for comparison - items not in saved are shown as disabled */
  savedOutputs?: any[];
  savedOutputGroups?: any[];
  savedCovers?: any[];
  /** Callback to update events when orphaned actions need to be removed */
  onUpdateEvents?: (newEvents: any[]) => void;
  /** Callback to update binary_sensors when orphaned actions need to be removed */
  onUpdateBinarySensors?: (newBinarySensors: any[]) => void;
  /** Callback to save a section after orphaned actions are removed.
   * If data is provided, it will be saved directly instead of using formData.
   */
  onSaveSection?: (sectionName: string, data?: any) => Promise<void>;
  /** Name of item to auto-open for editing (from URL query param) */
  editItemName?: string;
  /** Callback when edit item has been opened (to clear URL query param) */
  onEditItemOpened?: () => void;
}

/**
 * Custom table widget for array sections (e.g. event, binary_sensor) with modal editing.
 * Uses regular table with Edit buttons, @rjsf form only appears in modal.
 * This prevents automatic onChange calls during editing.
 */
const ArrayTableWidget: React.FC<ArrayTableWidgetProps> = ({ value = [], onChange, schema, title, uiSchema, sectionType = 'other', deviceType, allBinarySensors = [], allEvents = [], allOutputs = [], allOutputGroups = [], allCovers = [], allAreas = [], allSensors = [], allModbusDevices = [], allVirtualEnergySensors = [], allRemoteDevices = [], savedOutputs, savedOutputGroups, savedCovers, onUpdateEvents, onUpdateBinarySensors, onSaveSection, editItemName, onEditItemOpened }) => {
  const { t } = useTranslation();
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [hasValidationErrors, setHasValidationErrors] = useState(false);
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);
  const [interlockGroups, setInterlockGroups] = useState<string[]>([]);
  const [availableDallasSensors, setAvailableDallasSensors] = useState<{ address: string, type: string }[]>([]);

  // State for delete confirmation dialog
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);

  // State for import dialog
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importData, setImportData] = useState<any[] | null>(null);
  const [importMode, setImportMode] = useState<'replace' | 'merge'>('merge');
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [affectedActions, setAffectedActions] = useState<{ type: string, name: string, actionType: string }[]>([]);
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const editItemProcessedRef = useRef<string | null>(null);

  // Auto-open edit modal when editItemName is provided (from URL query param)
  useEffect(() => {
    // Wait for data to load before trying to find the item
    if (!editItemName || value.length === 0) {
      return;
    }

    // Don't process the same item twice
    if (editItemProcessedRef.current === editItemName) {
      return;
    }

    // Find item by name, id, boneio_input, boneio_output, or auto-generated cover id
    const index = value.findIndex((item: any) => {
      if (item.name === editItemName) return true;
      if (item.id === editItemName) return true;
      if (item.boneio_input === editItemName) return true;
      if (item.boneio_output === editItemName) return true;
      // For covers: match auto-generated id format (cover_{open_relay}_{close_relay})
      if (sectionType === 'cover' && item.open_relay && item.close_relay) {
        const generatedId = `cover_${item.open_relay}_${item.close_relay}`.toLowerCase().replace(/ /g, '_');
        if (generatedId === editItemName) return true;
      }
      return false;
    });

    console.log('🔍 ArrayTableWidget: Looking for item to edit:', editItemName, 'found at index:', index, 'in', value.length, 'items');

    if (index !== -1) {
      editItemProcessedRef.current = editItemName;
      const item = { ...value[index] };
      // Migrate legacy 'id' field to 'name' for binary_sensor and event sections
      if ((sectionType === 'binary_sensor' || sectionType === 'event') && item.id && !item.name) {
        item.name = item.id;
        delete item.id;
      }
      console.log('🔧 ArrayTableWidget: Auto-opening edit modal for:', item.name || item.id);
      setEditingItem(item);
      setEditingIndex(index);
      setAttemptedSubmit(false);
      setIsModalOpen(true);
      onEditItemOpened?.();
    }
  }, [editItemName, value, sectionType, onEditItemOpened]);

  // Fetch interlock groups for output section
  useEffect(() => {
    if (sectionType === 'output') {
      axios.get('/api/interlock-groups')
        .then(res => {
          setInterlockGroups(res.data.groups || []);
        })
        .catch(err => {
          console.error('Failed to fetch interlock groups:', err);
        });
    }
  }, [sectionType]);

  // Callback to add new interlock group to local cache (before saving to backend)
  const handleInterlockGroupCreated = (groupName: string) => {
    setInterlockGroups(prev => {
      if (!prev.includes(groupName)) {
        return [...prev, groupName];
      }
      return prev;
    });
  };

  // Fetch available Dallas sensors for sensor section
  useEffect(() => {
    if (sectionType === 'sensor') {
      axios.get('/api/dallas/available')
        .then(res => {
          setAvailableDallasSensors(res.data.sensors || []);
        })
        .catch(err => {
          console.error('Failed to fetch Dallas sensors:', err);
        });
    }
  }, [sectionType]);

  // Format timeperiod to human-readable time
  // Accepts number (ms), string ("30s"), or TimePeriod object from backend
  const formatTimeperiod = (value: number | string | { milliseconds?: number; seconds?: number; minutes?: number; hours?: number; _total_in_seconds?: number }): string => {
    let ms: number;

    // If string with unit, return as-is
    if (typeof value === 'string') {
      if (/^\d+(\.\d+)?\s*(ms|s|sec|min|h|hours?)$/i.test(value)) {
        return value;
      }
      ms = parseFloat(value) || 0;
    }
    // If number, treat as milliseconds
    else if (typeof value === 'number') {
      ms = value;
    }
    // If TimePeriod object from backend
    else if (typeof value === 'object' && value !== null) {
      if (value.hours !== undefined && value.hours > 0) {
        return `${value.hours}h`;
      }
      if (value.minutes !== undefined && value.minutes > 0) {
        return `${value.minutes}min`;
      }
      if (value.seconds !== undefined && value.seconds > 0) {
        return `${value.seconds}s`;
      }
      if (value.milliseconds !== undefined && value.milliseconds > 0) {
        return `${value.milliseconds}ms`;
      }
      // Fallback: use _total_in_seconds
      if (value._total_in_seconds !== undefined) {
        ms = value._total_in_seconds * 1000;
      } else {
        return '0ms';
      }
    } else {
      return '0ms';
    }

    // Format milliseconds to best unit
    if (ms >= 60000) {
      const minutes = ms / 60000;
      return minutes % 1 === 0 ? `${minutes}min` : `${ms}ms`;
    } else if (ms >= 1000) {
      const seconds = ms / 1000;
      return seconds % 1 === 0 ? `${seconds}s` : `${ms}ms`;
    }
    return `${ms}ms`;
  };

  const handleEdit = (index: number) => {
    console.log('🔧 ArrayTableWidget: handleEdit called for index:', index);
    // Deep copy to prevent mutations from affecting original data when user cancels
    const item = JSON.parse(JSON.stringify(value[index]));

    // Migrate legacy 'id' field to 'name' for binary_sensor and event sections
    // This prevents duplicate fields when user edits old config with 'id' and form uses 'name'
    if ((sectionType === 'binary_sensor' || sectionType === 'event') && item.id && !item.name) {
      item.name = item.id;
      delete item.id;
    }

    setEditingItem(item);
    setEditingIndex(index);
    setAttemptedSubmit(false); // Reset przy otwieraniu modala
    setIsModalOpen(true);
  };

  const handleAdd = () => {
    console.log('➕ ArrayTableWidget: handleAdd called');
    setEditingIndex(null);
    // Set default values for remote_devices
    if (sectionType === 'remote_devices') {
      setEditingItem({ protocol: 'mqtt', device_type: 'boneio_black' });
      setAttemptedSubmit(false);
      setIsModalOpen(true);
    } else if (sectionType === 'template') {
      // Show platform picker first
      setShowTemplatePicker(true);
    } else {
      setEditingItem({});
      setAttemptedSubmit(false);
      setIsModalOpen(true);
    }
  };

  const handleTemplatePlatformSelect = (platform: string) => {
    setShowTemplatePicker(false);
    setEditingItem({ platform, _autoId: true });
    setAttemptedSubmit(false);
    setIsModalOpen(true);
  };

  // Handle adding remote device from autodiscovery
  const handleAddFromDiscovery = (device: any) => {
    console.log('➕ ArrayTableWidget: handleAddFromDiscovery called', device);
    setEditingIndex(null);

    // Check if this is an ESPHome device
    if (device.protocol === 'esphome_api' || device.esphome_api) {
      // Pre-fill form with ESPHome device data
      setEditingItem({
        id: device.id,
        name: device.name || device.id,
        protocol: 'esphome_api',
        device_type: 'esphome',
        esphome_api: {
          host: device.esphome_api?.host || '',
          port: device.esphome_api?.port || 6053,
          password: device.esphome_api?.password || '',
          encryption_key: device.esphome_api?.encryption_key || '',
          switches: device.esphome_api?.switches || [],
          lights: device.esphome_api?.lights || [],
          covers: device.esphome_api?.covers || [],
        },
      });
    } else if (device.protocol === 'wled' || device.wled) {
      // Pre-fill form with WLED device data
      setEditingItem({
        id: device.id,
        name: device.name || device.id,
        protocol: 'wled',
        device_type: 'wled',
        wled: {
          host: device.wled?.host || '',
          port: device.wled?.port || 80,
          segments: device.wled?.segments || [],
        },
      });
    } else {
      // Pre-fill form with MQTT/BoneIO device data
      setEditingItem({
        id: device.id,
        name: device.name || device.id,
        protocol: device.protocol || 'mqtt',
        device_type: device.device_type || 'boneio_black',
        mqtt: {
          outputs: device.outputs || [],
          covers: device.covers || [],
        },
      });
    }
    setAttemptedSubmit(false);
    setIsModalOpen(true);
  };

  // Check if all outputs/inputs are used
  const areAllItemsUsed = () => {
    if (sectionType === 'output') {
      // Get available outputs based on device type
      const getOutputCount = (deviceType: string) => {
        const type = deviceType?.toLowerCase() || '';
        if (type.includes('32') || type.includes('cm')) {
          return 32; // 32x10A, Cover, Cover Mix
        } else if (type.includes('24')) {
          return 24; // 24x16A
        }
        return 49; // default fallback
      };

      const outputCount = getOutputCount(deviceType || '');
      const usedOutputs = value.filter(output => output.boneio_output).length;

      return usedOutputs >= outputCount;
    } else if (sectionType === 'binary_sensor' || sectionType === 'event') {
      // Check if all inputs are used (shared between binary_sensor and event)
      const usedInputsFromBinarySensors = allBinarySensors
        .filter(sensor => sensor.boneio_input)
        .map(sensor => sensor.boneio_input);

      const usedInputsFromEvents = allEvents
        .filter(event => event.boneio_input)
        .map(event => event.boneio_input);

      const allUsedInputs = [...new Set([...usedInputsFromBinarySensors, ...usedInputsFromEvents])];

      // Get total available inputs from schema (assuming it's the same for both)
      const totalInputs = (schema as any)?.items?.properties?.boneio_input?.enum?.length || 0;

      return allUsedInputs.length >= totalInputs;
    } else if (sectionType === 'output_group') {
      // Output groups don't have a fixed limit, so always allow adding
      return false;
    } else if (sectionType === 'cover') {
      // Covers don't have a fixed limit, so always allow adding
      return false;
    } else if (sectionType === 'modbus_devices') {
      // Modbus devices don't have a fixed limit, so always allow adding
      return false;
    } else if (sectionType === 'remote_devices') {
      // Remote devices don't have a fixed limit, so always allow adding
      return false;
    }

    return false;
  };

  const handleSave = (e?: any) => {
    console.log('💾 ArrayTableWidget: handleSave called, calling onChange');

    // Oznacz że użytkownik próbował zapisać
    setAttemptedSubmit(true);

    // Block save if there are validation errors from child form
    if (hasValidationErrors) {
      console.log('❌ ArrayTableWidget: Save blocked due to validation errors');
      alert(t('array_table_widget.fix_validation_errors_before_saving'));
      return;
    }

    // If called from @rjsf onSubmit, e.formData contains the data
    const dataToSave = e?.formData || editingItem;

    // Validate required fields based on section type
    let isValid = false;
    let errorMessage = '';

    if (sectionType === 'binary_sensor') {
      isValid = !!dataToSave.boneio_input;
      errorMessage = t('array_table_widget.boneio_input_required');
    } else if (sectionType === 'event') {
      isValid = !!dataToSave.boneio_input;
      errorMessage = t('array_table_widget.boneio_input_required');
    } else if (sectionType === 'output') {
      isValid = !!dataToSave.boneio_output;
      errorMessage = t('array_table_widget.boneio_output_required');
    } else if (sectionType === 'output_group') {
      const hasId = !!dataToSave.id;
      const hasOutputs = !!dataToSave.outputs && (Array.isArray(dataToSave.outputs) ? dataToSave.outputs.length > 0 : true);
      isValid = hasId && hasOutputs;
      errorMessage = !hasId ? t('array_table_widget.id_required') : t('array_table_widget.at_least_one_output_required');
    } else if (sectionType === 'cover') {
      // ID is now optional (auto-generated from relays)
      isValid = !!dataToSave.open_relay && !!dataToSave.close_relay && !!dataToSave.open_time && !!dataToSave.close_time;
      errorMessage = t('array_table_widget.cover_fields_required');
    } else if (sectionType === 'modbus_devices') {
      // ID is now optional (auto-generated from address and model)
      isValid = !!dataToSave.address && !!dataToSave.model;
      errorMessage = t('array_table_widget.address_and_model_required');

      // Validate update_interval minimum (1 second = 1000ms)
      if (isValid && dataToSave.update_interval) {
        const interval = typeof dataToSave.update_interval === 'number'
          ? dataToSave.update_interval
          : parseInt(dataToSave.update_interval);

        if (interval < 1000) {
          isValid = false;
          errorMessage = t('array_table_widget.update_interval_minimum');
        }
      }
    } else if (sectionType === 'remote_devices') {
      // Remote device requires id, name, protocol
      isValid = !!dataToSave.id && !!dataToSave.name && !!dataToSave.protocol;

      // ESPHome API also requires host
      if (isValid && dataToSave.protocol === 'esphome_api') {
        isValid = !!dataToSave.esphome_api?.host;
        if (!isValid) {
          errorMessage = t('remote_devices.esphome_host_required') || 'ESPHome host is required';
        }
      }

      if (!errorMessage) {
        errorMessage = t('array_table_widget.remote_device_fields_required');
      }
      console.log('Remote device validation:', dataToSave, 'isValid:', isValid);
    } else if (sectionType === 'template') {
      const hasPlatform = !!dataToSave.platform;
      if (dataToSave.platform === 'thermostat') {
        isValid = hasPlatform && !!dataToSave.sensor_id && !!dataToSave.output_id;
        errorMessage = t('template.thermostat_fields_required');
      } else if (dataToSave.platform === 'alarm_control_panel') {
        isValid = hasPlatform;
        errorMessage = t('template.alarm_fields_required');
      } else if (dataToSave.platform === 'gate_cover') {
        const mode = dataToSave.control_mode || 'cycle';
        if (mode === 'separate') {
          isValid = hasPlatform && !!dataToSave.id && (!!dataToSave.open_output || !!dataToSave.close_output);
        } else {
          isValid = hasPlatform && !!dataToSave.id && !!dataToSave.pulse_output;
        }
        errorMessage = t('template.gate_cover_fields_required');
      } else {
        isValid = hasPlatform;
        errorMessage = t('template.platform_required');
      }
    } else {
      // For other sections, allow saving (or add specific validation)
      isValid = true;
    }

    if (!isValid) {
      alert(errorMessage);
      return;
    }

    // For binary_sensor and event, ensure we don't have both 'id' and 'name' fields
    // Remove legacy 'id' field if 'name' exists
    let cleanedData = { ...dataToSave };
    if ((sectionType === 'binary_sensor' || sectionType === 'event') && cleanedData.name && cleanedData.id) {
      delete cleanedData.id;
    }
    // Auto-generate unique ID for template entries (only if user didn't provide one)
    if (sectionType === 'template') {
      delete cleanedData._autoId;
      if (!cleanedData.id) {
        const baseName = (cleanedData.name || cleanedData.platform || 'template').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
        const existingIds = new Set(
          value
            .filter((_: any, i: number) => i !== editingIndex)
            .map((item: any) => item.id)
        );
        let candidateId = baseName;
        let suffix = 2;
        while (existingIds.has(candidateId)) {
          candidateId = `${baseName}_${suffix}`;
          suffix++;
        }
        cleanedData.id = candidateId;
      }
    }

    const newValue = [...value];
    if (editingIndex !== null) {
      newValue[editingIndex] = cleanedData;
    } else {
      newValue.push(cleanedData);
    }
    // Only call onChange when actually saving, not during editing
    console.log('🔄 ArrayTableWidget: calling onChange with:', newValue);
    onChange(newValue);
    setIsModalOpen(false);
    setEditingItem(null);
    setEditingIndex(null);
  };

  /**
   * Find all items that use the given area ID.
   * Returns list of affected items with their section type and name.
   */
  const findItemsUsingArea = (areaId: string): { type: string, name: string, actionType: string }[] => {
    const affected: { type: string, name: string, actionType: string }[] = [];

    // Check outputs
    allOutputs.forEach((item: any) => {
      if (item.area === areaId) {
        affected.push({
          type: t('navigation.outputs'),
          name: item.id || item.name || item.boneio_output || t('array_table_widget.unknown'),
          actionType: item.boneio_output || ''
        });
      }
    });

    // Check output groups
    allOutputGroups.forEach((item: any) => {
      if (item.area === areaId) {
        affected.push({
          type: t('outputs.output_group'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: ''
        });
      }
    });

    // Check covers
    allCovers.forEach((item: any) => {
      if (item.area === areaId) {
        affected.push({
          type: t('covers.title'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: `${item.open_relay} / ${item.close_relay}`
        });
      }
    });

    // Check binary sensors
    allBinarySensors.forEach((item: any) => {
      if (item.area === areaId) {
        affected.push({
          type: t('navigation.inputs'),
          name: item.name || item.boneio_input || t('array_table_widget.unknown'),
          actionType: item.boneio_input || ''
        });
      }
    });

    // Check events
    allEvents.forEach((item: any) => {
      if (item.area === areaId) {
        affected.push({
          type: t('event_form.title'),
          name: item.name || item.boneio_input || t('array_table_widget.unknown'),
          actionType: item.boneio_input || ''
        });
      }
    });

    // Check sensors
    allSensors.forEach((item: any) => {
      if (item.area === areaId) {
        affected.push({
          type: t('navigation.sensors'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: item.address || ''
        });
      }
    });

    // Check modbus devices
    allModbusDevices.forEach((item: any) => {
      if (item.area === areaId) {
        affected.push({
          type: t('navigation.modbus'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: `${item.model} @ ${item.address}`
        });
      }
    });

    // Check virtual energy sensors
    allVirtualEnergySensors.forEach((item: any) => {
      if (item.area === areaId) {
        affected.push({
          type: t('virtual_energy_sensor.title'),
          name: item.id || item.name || t('array_table_widget.unknown'),
          actionType: ''
        });
      }
    });

    return affected;
  };

  /**
   * Find all actions in events and binary_sensors that reference the given item ID.
   * Returns list of affected actions with their source (event/binary_sensor name and action type).
   * For remote_devices, checks remote_device field in remote_output and remote_cover actions.
   */
  const findAffectedActions = (itemId: string, isRemoteDevice: boolean = false): { type: string, name: string, actionType: string }[] => {
    const affected: { type: string, name: string, actionType: string }[] = [];

    // Check events
    allEvents.forEach((event: any) => {
      const eventName = event.name || event.boneio_input || t('array_table_widget.unknown_event');
      ['single', 'double', 'long'].forEach((pressType) => {
        const actions = event.actions?.[pressType] || [];
        actions.forEach((action: any) => {
          if (isRemoteDevice) {
            // For remote_devices, check remote_device field
            if (action.remote_device === itemId) {
              affected.push({
                type: t('array_table_widget.event'),
                name: eventName,
                actionType: `${pressType} → ${action.action || 'remote_output'}`
              });
            }
          } else {
            // For output/cover, check pin and boneio_output
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

    // Check binary_sensors
    allBinarySensors.forEach((sensor: any) => {
      const sensorName = sensor.name || sensor.boneio_input || t('array_table_widget.unknown_sensor');
      ['pressed', 'released'].forEach((pressType) => {
        const actions = sensor.actions?.[pressType] || [];
        actions.forEach((action: any) => {
          if (isRemoteDevice) {
            // For remote_devices, check remote_device field
            if (action.remote_device === itemId) {
              affected.push({
                type: t('array_table_widget.binary_sensor'),
                name: sensorName,
                actionType: `${pressType} → ${action.action || 'remote_output'}`
              });
            }
          } else {
            // For output/cover, check pin and boneio_output
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
    console.log("Affected actions:", affected);

    return affected;
  };

  /**
   * Remove actions that reference the given item ID from events and binary_sensors.
   * Returns the updated data for immediate saving.
   * For remote_devices, removes actions where remote_device matches itemId.
   */
  const removeOrphanedActions = (itemId: string, isRemoteDevice: boolean = false): { updatedEvents: any[] | null, updatedSensors: any[] | null } => {
    console.log('🗑️ removeOrphanedActions called with itemId:', itemId, 'isRemoteDevice:', isRemoteDevice);

    let updatedEvents: any[] | null = null;
    let updatedSensors: any[] | null = null;

    // Update events
    if (onUpdateEvents) {
      updatedEvents = allEvents.map((event: any) => {
        const updatedActions: any = {};
        ['single', 'double', 'long'].forEach((pressType) => {
          const actions = event.actions?.[pressType] || [];
          const filtered = actions.filter((action: any) => {
            let shouldKeep: boolean;
            if (isRemoteDevice) {
              // For remote_devices, check remote_device field
              shouldKeep = action.remote_device !== itemId;
              if (!shouldKeep) {
                console.log(`🗑️ Removing remote action from event ${event.name || event.boneio_input}: ${pressType} -> remote_device=${action.remote_device}`);
              }
            } else {
              // For output/cover, check pin and boneio_output
              shouldKeep = action.pin !== itemId && action.boneio_output !== itemId;
              if (!shouldKeep) {
                console.log(`🗑️ Removing action from event ${event.name || event.boneio_input}: ${pressType} -> boneio_output=${action.boneio_output}`);
              }
            }
            return shouldKeep;
          });
          updatedActions[pressType] = filtered;
        });
        return { ...event, actions: updatedActions };
      });
      console.log('🗑️ Updated events:', updatedEvents);
      onUpdateEvents(updatedEvents);
    }

    // Update binary_sensors
    if (onUpdateBinarySensors) {
      updatedSensors = allBinarySensors.map((sensor: any) => {
        const updatedActions: any = {};
        ['pressed', 'released'].forEach((pressType) => {
          const actions = sensor.actions?.[pressType] || [];
          const filtered = actions.filter((action: any) => {
            let shouldKeep: boolean;
            if (isRemoteDevice) {
              // For remote_devices, check remote_device field
              shouldKeep = action.remote_device !== itemId;
              if (!shouldKeep) {
                console.log(`🗑️ Removing remote action from sensor ${sensor.name || sensor.boneio_input}: ${pressType} -> remote_device=${action.remote_device}`);
              }
            } else {
              // For output/cover, check pin and boneio_output
              shouldKeep = action.pin !== itemId && action.boneio_output !== itemId;
              if (!shouldKeep) {
                console.log(`🗑️ Removing action from sensor ${sensor.name || sensor.boneio_input}: ${pressType} -> boneio_output=${action.boneio_output}`);
              }
            }
            return shouldKeep;
          });
          updatedActions[pressType] = filtered;
        });
        return { ...sensor, actions: updatedActions };
      });
      console.log('🗑️ Updated sensors:', updatedSensors);
      onUpdateBinarySensors(updatedSensors);
    }

    return { updatedEvents, updatedSensors };
  };

  /**
   * Get the ID of an item being deleted based on section type.
   */
  const getItemId = (item: any): string => {
    if (sectionType === 'output') {
      return item.id || item.boneio_output || '';
    } else if (sectionType === 'output_group') {
      return item.id || '';
    } else if (sectionType === 'cover') {
      return item.id || (item.open_relay && item.close_relay
        ? `cover_${item.open_relay}_${item.close_relay}`.toLowerCase()
        : '');
    } else if (sectionType === 'remote_devices') {
      return item.id || '';
    }
    return '';
  };

  const handleDelete = (index: number) => {
    const item = value[index];

    // Check for affected items when deleting an area
    if (sectionType === 'areas') {
      const areaId = item.id;
      const affected = findItemsUsingArea(areaId);

      if (affected.length > 0) {
        // Show confirmation dialog - but for areas we just warn, don't auto-remove
        setDeleteIndex(index);
        setAffectedActions(affected);
        setDeleteConfirmOpen(true);
        return;
      }
    }

    // Only check for affected actions when deleting output, output_group, cover, or remote_devices
    if (sectionType === 'output' || sectionType === 'output_group' || sectionType === 'cover' || sectionType === 'remote_devices') {
      const itemId = getItemId(item);
      const isRemoteDevice = sectionType === 'remote_devices';
      const affected = findAffectedActions(itemId, isRemoteDevice);

      if (affected.length > 0) {
        // Show confirmation dialog
        setDeleteIndex(index);
        setAffectedActions(affected);
        setDeleteConfirmOpen(true);
        return;
      }
    }

    // No affected actions, delete directly
    const newValue = value.filter((_, i) => i !== index);
    onChange(newValue);
  };

  const confirmDelete = async () => {
    if (deleteIndex === null) return;

    const item = value[deleteIndex];

    // For areas, just delete without removing references (user is warned)
    if (sectionType === 'areas') {
      const newValue = value.filter((_, i) => i !== deleteIndex);
      onChange(newValue);

      // Close dialog
      setDeleteConfirmOpen(false);
      setDeleteIndex(null);
      setAffectedActions([]);

      // Save the areas section
      if (onSaveSection) {
        console.log(`🔄 Auto-saving ${sectionType} section with item removed:`, newValue);
        await onSaveSection(sectionType, newValue);
      }
      return;
    }

    const itemId = getItemId(item);
    const isRemoteDevice = sectionType === 'remote_devices';

    // Check which sections have affected actions
    const hasEventActions = affectedActions.some(a => a.type === t('array_table_widget.event'));
    const hasBinarySensorActions = affectedActions.some(a => a.type === t('array_table_widget.binary_sensor'));

    // Remove orphaned actions first and get updated data
    const { updatedEvents, updatedSensors } = removeOrphanedActions(itemId, isRemoteDevice);

    // Delete the item and get updated value
    const newValue = value.filter((_, i) => i !== deleteIndex);
    onChange(newValue);

    // Close dialog
    setDeleteConfirmOpen(false);
    setDeleteIndex(null);
    setAffectedActions([]);

    // Save all affected sections with the updated data directly
    if (onSaveSection) {
      // First save the current section (output/output_group/cover/remote_devices) with the item removed
      console.log(`🔄 Auto-saving ${sectionType} section with item removed:`, newValue);
      await onSaveSection(sectionType, newValue);

      // Then save event and binary_sensor sections with orphaned actions removed
      if (hasEventActions && updatedEvents) {
        console.log('🔄 Auto-saving event section with updated data:', updatedEvents);
        await onSaveSection('event', updatedEvents);
      }
      if (hasBinarySensorActions && updatedSensors) {
        console.log('🔄 Auto-saving binary_sensor section with updated data:', updatedSensors);
        await onSaveSection('binary_sensor', updatedSensors);
      }
    }
  };

  const cancelDelete = () => {
    setDeleteConfirmOpen(false);
    setDeleteIndex(null);
    setAffectedActions([]);
  };

  const handleCancel = () => {
    setIsModalOpen(false);
    setEditingItem(null);
    setEditingIndex(null);
  };

  /**
   * Export current section data as YAML file
   */
  const handleExport = () => {
    const exportData = {
      section: sectionType,
      version: '1.0',
      exported_at: new Date().toISOString(),
      data: value
    };

    const yamlContent = yaml.dump(exportData, { indent: 2, lineWidth: -1, noRefs: true });
    const blob = new Blob([yamlContent], { type: 'application/x-yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `boneio_${sectionType}_${new Date().toISOString().split('T')[0]}.yaml`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  /**
   * Handle file selection for import (supports YAML and JSON)
   */
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        let parsed: any;

        // Try YAML first (also handles JSON since JSON is valid YAML)
        try {
          parsed = yaml.load(content);
        } catch {
          // Fallback to JSON parse for better error messages
          parsed = JSON.parse(content);
        }

        // Validate structure
        if (!parsed.data || !Array.isArray(parsed.data)) {
          setImportError(t('import_export.invalid_format'));
          setImportData(null);
          setImportDialogOpen(true);
          return;
        }

        // Check section type match (warning only)
        if (parsed.section && parsed.section !== sectionType) {
          console.warn(`Import section mismatch: expected ${sectionType}, got ${parsed.section}`);
        }

        setImportData(parsed.data);
        setImportError(null);
        setImportDialogOpen(true);
      } catch {
        setImportError(t('import_export.parse_error'));
        setImportData(null);
        setImportDialogOpen(true);
      }
    };
    reader.readAsText(file);

    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  /**
   * Confirm import with selected mode
   */
  const confirmImport = () => {
    if (!importData) return;

    if (importMode === 'replace') {
      onChange(importData);
    } else {
      // Merge: add new items, skip duplicates by id/name
      const existingIds = new Set(value.map(item => item.id || item.name || item.boneio_output || item.boneio_input));
      const newItems = importData.filter(item => {
        const itemId = item.id || item.name || item.boneio_output || item.boneio_input;
        return !existingIds.has(itemId);
      });
      onChange([...value, ...newItems]);
    }

    setImportDialogOpen(false);
    setImportData(null);
    setImportMode('merge');
  };

  /**
   * Cancel import
   */
  const cancelImport = () => {
    setImportDialogOpen(false);
    setImportData(null);
    setImportError(null);
    setImportMode('merge');
  };

  // Render appropriate table component based on section type
  const renderTable = () => {
    const commonProps = {
      items: value,
      onEdit: handleEdit,
      onDelete: handleDelete,
    };

    switch (sectionType) {
      case 'output':
        return <OutputTable {...commonProps} allAreas={allAreas} />;
      case 'output_group':
        return <OutputGroupTable {...commonProps} allAreas={allAreas} allCovers={allCovers} />;
      case 'cover':
        return <CoverTable {...commonProps} allAreas={allAreas} />;
      case 'binary_sensor':
      case 'event':
        return <BinarySensorEventTable {...commonProps} allAreas={allAreas} allOutputs={allOutputs} allCovers={allCovers} allRemoteDevices={allRemoteDevices} />;
      case 'modbus_devices':
        return <ModbusDeviceTable {...commonProps} allAreas={allAreas} formatTimeperiod={formatTimeperiod} />;
      case 'areas':
        return <AreasTable {...commonProps} />;
      case 'sensor':
        return <SensorTable {...commonProps} allAreas={allAreas} />;
      case 'virtual_energy_sensor':
        return <VirtualEnergySensorTable {...commonProps} allAreas={allAreas} />;
      case 'remote_devices':
        return <RemoteDeviceTable {...commonProps} onAddFromDiscovery={handleAddFromDiscovery} />;
      case 'template':
        return <TemplateTable {...commonProps} allAreas={allAreas} />;
      default:
        return <GenericTable {...commonProps} />;
    }
  };


  return (
    <div className="space-y-4">
      {/* Hidden file input for import */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        accept=".yaml,.yml,.json"
        className="hidden"
      />

      <div className="flex justify-between items-center flex-wrap gap-2">
        <h3 className="text-lg font-semibold">{title || t('array_table_widget.items')}</h3>
        <div className="flex gap-2 flex-wrap">
          {/* Export button */}
          <div className="tooltip tooltip-bottom" data-tip={t('import_export.export')}>
            <button
              onClick={handleExport}
              className="btn btn-ghost btn-sm"
              disabled={value.length === 0}
            >
              <FaDownload />
              <span className="hidden sm:inline ml-1">{t('import_export.export')}</span>
            </button>
          </div>

          {/* Import button */}
          <div className="tooltip tooltip-bottom" data-tip={t('import_export.import')}>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="btn btn-ghost btn-sm"
            >
              <FaUpload />
              <span className="hidden sm:inline ml-1">{t('import_export.import')}</span>
            </button>
          </div>

          {/* Add new button */}
          <div className={`tooltip tooltip-left ${areAllItemsUsed() ? 'tooltip-warning' : 'tooltip-info'}`}
            data-tip={areAllItemsUsed() ? (sectionType === 'output' ? t('outputs.all_outputs_used') : t('inputs.all_inputs_used')) : t('settings.add_new')}>
            <button
              onClick={handleAdd}
              className="btn btn-primary btn-sm"
              disabled={areAllItemsUsed()}
            >
              <FaPlus className="mr-2" />
              {t('settings.add_new')}
            </button>
          </div>
        </div>
      </div>

      {value.length > 0 || sectionType === 'remote_devices' ? (
        renderTable()
      ) : (
        <div className="text-center py-8 text-base-content/60">
          <p>{t('settings.no_items')}</p>
          <p className="text-sm">{t('settings.click_add_new')}</p>
        </div>
      )}

      {/* Template Platform Picker Dialog */}
      <Dialog open={showTemplatePicker} onOpenChange={setShowTemplatePicker}>
        <DialogContent className="max-w-md bg-base-100">
          <DialogHeader>
            <DialogTitle>{t('template.select_platform_title')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-4">
            <button
              type="button"
              className="w-full p-4 rounded-lg border border-base-300 hover:border-primary hover:bg-primary/5 transition-colors text-left flex items-start gap-3"
              onClick={() => handleTemplatePlatformSelect('thermostat')}
            >
              <span className="text-2xl">🌡️</span>
              <div>
                <div className="font-semibold">{t('template.platform_thermostat')}</div>
                <div className="text-sm text-base-content/60">{t('template.platform_thermostat_hint')}</div>
              </div>
            </button>
            <button
              type="button"
              className="w-full p-4 rounded-lg border border-base-300 hover:border-primary hover:bg-primary/5 transition-colors text-left flex items-start gap-3"
              onClick={() => handleTemplatePlatformSelect('alarm_control_panel')}
            >
              <span className="text-2xl">🚨</span>
              <div>
                <div className="font-semibold">{t('template.platform_alarm_control_panel')}</div>
                <div className="text-sm text-base-content/60">{t('template.platform_alarm_hint')}</div>
              </div>
            </button>
            <button
              type="button"
              className="w-full p-4 rounded-lg border border-base-300 hover:border-primary hover:bg-primary/5 transition-colors text-left flex items-start gap-3"
              onClick={() => handleTemplatePlatformSelect('gate_cover')}
            >
              <span className="text-2xl">🚪</span>
              <div>
                <div className="font-semibold">{t('template.platform_gate_cover')}</div>
                <div className="text-sm text-base-content/60">{t('template.platform_gate_cover_hint')}</div>
              </div>
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Modal */}
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent className="max-w-4xl sm:max-w-3xl lg:w-[120vw] max-h-[80vh] flex flex-col gap-0 bg-base-100">
          <DialogHeader>
            <DialogTitle>
              {editingIndex !== null ? (
                <>
                  {t('settings.edit_item')}
                  {editingItem && (editingItem.id || editingItem.name || editingItem.boneio_output || editingItem.boneio_input) && (
                    <span className="font-normal text-base-content/70">
                      {' - '}
                      {editingItem.id || editingItem.name || ''}
                      {(editingItem.id || editingItem.name) && (editingItem.boneio_output || editingItem.boneio_input) && ' '}
                      {editingItem.boneio_output && <span className="text-sm">({editingItem.boneio_output})</span>}
                      {editingItem.boneio_input && <span className="text-sm">({editingItem.boneio_input})</span>}
                    </span>
                  )}
                </>
              ) : t('settings.add_new_item')}
            </DialogTitle>
          </DialogHeader>

          {/* Scrollable content area */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden -mx-6 px-6 wrap-break-words [&_.label-text]:whitespace-normal [&_.label-text]:wrap-break-words [&_.label-text-alt]:whitespace-normal [&_.label-text-alt]:wrap-break-words [&_.form-control]:min-w-0">
            {/* Only render form when editingItem is not null */}
            {editingItem && (
              <>
                {/* Use custom form for binary_sensor/event/output, @rjsf for others */}
                {sectionType === 'binary_sensor' ? (
                  <BinarySensorForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    allBinarySensors={allBinarySensors}
                    allEvents={allEvents}
                    allOutputs={allOutputs}
                    allOutputGroups={allOutputGroups}
                    allCovers={allCovers}
                    allAreas={allAreas}
                    allRemoteDevices={allRemoteDevices}
                    editingIndex={editingIndex}
                    onValidationChange={setHasValidationErrors}
                    attemptedSubmit={attemptedSubmit}
                    savedOutputs={savedOutputs}
                    savedOutputGroups={savedOutputGroups}
                    savedCovers={savedCovers}
                  />
                ) : sectionType === 'event' ? (
                  <EventForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    allBinarySensors={allBinarySensors}
                    allEvents={allEvents}
                    allOutputs={allOutputs}
                    allOutputGroups={allOutputGroups}
                    allCovers={allCovers}
                    allAreas={allAreas}
                    allRemoteDevices={allRemoteDevices}
                    editingIndex={editingIndex}
                    onValidationChange={setHasValidationErrors}
                    attemptedSubmit={attemptedSubmit}
                    savedOutputs={savedOutputs}
                    savedOutputGroups={savedOutputGroups}
                    savedCovers={savedCovers}
                  />
                ) : sectionType === 'output' ? (
                  <OutputForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    uiSchema={uiSchema}
                    deviceType={deviceType}
                    allOutputs={value}
                    allAreas={allAreas}
                    editingIndex={editingIndex}
                    interlockGroups={interlockGroups}
                    onInterlockGroupCreated={handleInterlockGroupCreated}
                    allCovers={allCovers}
                  />
                ) : sectionType === 'output_group' ? (
                  <OutputGroupForm
                    data={editingItem}
                    onChange={setEditingItem}
                    schema={schema}
                    allOutputs={allOutputs}
                    allAreas={allAreas}
                  />
                ) : sectionType === 'cover' ? (
                  <CoverForm
                    data={editingItem}
                    onChange={setEditingItem}
                    schema={schema}
                    allOutputs={allOutputs}
                    allAreas={allAreas}
                  />
                ) : sectionType === 'modbus_devices' ? (
                  <ModbusDeviceForm
                    data={editingItem}
                    onChange={setEditingItem}
                    schema={schema}
                    areas={allAreas}
                  />
                ) : sectionType === 'areas' ? (
                  <AreasForm
                    data={editingItem}
                    onChange={setEditingItem}
                  />
                ) : sectionType === 'sensor' ? (
                  <SensorForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    allAreas={allAreas}
                    availableSensors={availableDallasSensors}
                    existingSensors={value}
                    editingIndex={editingIndex}
                    onValidationChange={setHasValidationErrors}
                  />
                ) : sectionType === 'virtual_energy_sensor' ? (
                  <VirtualEnergySensorForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    allAreas={allAreas}
                    allOutputs={allOutputs}
                    existingSensors={value}
                    editingIndex={editingIndex}
                    onValidationChange={setHasValidationErrors}
                  />
                ) : sectionType === 'remote_devices' ? (
                  <RemoteDeviceForm
                    data={editingItem}
                    onChange={setEditingItem}
                  />
                ) : sectionType === 'template' ? (
                  <TemplateForm
                    data={editingItem}
                    onChange={setEditingItem}
                    schema={schema}
                    allOutputs={allOutputs}
                    allAreas={allAreas}
                    allSensors={allSensors}
                    allModbusDevices={allModbusDevices}
                    allInputs={allBinarySensors || []}
                    onValidationChange={setHasValidationErrors}
                  />
                ) : (
                  <div className="alert alert-warning">
                    <span>{t('array_table_widget.no_form_available').replace('{sectionType}', sectionType)}</span>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Action buttons - fixed at bottom */}
          <DialogFooter className="shrink-0 mt-2">
            <button
              type="button"
              onClick={handleCancel}
              className="btn btn-ghost"
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="btn btn-primary"
              disabled={hasValidationErrors}
              title={hasValidationErrors ? t('settings.fix_validation_errors') : ''}
            >
              {editingIndex !== null ? t('settings.save_changes') : t('settings.add_item')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="max-w-md bg-base-100">
          <DialogHeader>
            <DialogTitle className="text-warning flex items-center gap-2">
              ⚠️ {sectionType === 'areas' ? t('settings.area_in_use_title') : t('settings.delete_warning_title')}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p className="mb-4">
              {sectionType === 'areas'
                ? t('settings.area_in_use_message')
                : t('settings.delete_warning_message')}
            </p>
            <div className="bg-base-200 rounded-lg p-3 max-h-48 overflow-y-auto">
              <p className="font-medium mb-2">
                {sectionType === 'areas'
                  ? t('settings.items_using_area')
                  : t('settings.affected_actions')} ({affectedActions.length}):
              </p>
              <ul className="space-y-1 text-sm">
                {affectedActions.map((action, idx) => (
                  <li key={idx} className="flex items-center gap-2 flex-wrap">
                    <span className="badge badge-xs badge-outline">{action.type}</span>
                    <span className="font-medium">{action.name}</span>
                    {action.actionType && <span className="text-base-content/60">({action.actionType})</span>}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <DialogFooter>
            <button
              type="button"
              onClick={cancelDelete}
              className="btn btn-ghost"
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              onClick={confirmDelete}
              className="btn btn-error"
            >
              {sectionType === 'areas' ? t('settings.delete_anyway') : t('settings.delete_and_remove_actions')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Import Confirmation Dialog */}
      <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
        <DialogContent className="max-w-md bg-base-100">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              📥 {t('import_export.import_title')}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            {importError ? (
              <div className="alert alert-error">
                <span>{importError}</span>
              </div>
            ) : (
              <>
                <p>{t('import_export.import_confirm').replace('{count}', String(importData?.length || 0))}</p>

                <div className="form-control">
                  <label className="label cursor-pointer justify-start gap-3">
                    <input
                      type="radio"
                      name="importMode"
                      className="radio radio-primary"
                      checked={importMode === 'merge'}
                      onChange={() => setImportMode('merge')}
                    />
                    <div>
                      <span className="label-text font-medium">{t('import_export.mode_merge')}</span>
                      <p className="text-xs text-base-content/60">{t('import_export.mode_merge_desc')}</p>
                    </div>
                  </label>
                </div>

                <div className="form-control">
                  <label className="label cursor-pointer justify-start gap-3">
                    <input
                      type="radio"
                      name="importMode"
                      className="radio radio-warning"
                      checked={importMode === 'replace'}
                      onChange={() => setImportMode('replace')}
                    />
                    <div>
                      <span className="label-text font-medium">{t('import_export.mode_replace')}</span>
                      <p className="text-xs text-base-content/60">{t('import_export.mode_replace_desc')}</p>
                    </div>
                  </label>
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <button
              type="button"
              onClick={cancelImport}
              className="btn btn-ghost"
            >
              {t('common.cancel')}
            </button>
            {!importError && (
              <button
                type="button"
                onClick={confirmImport}
                className={`btn ${importMode === 'replace' ? 'btn-warning' : 'btn-primary'}`}
              >
                {t('import_export.confirm_import')}
              </button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ArrayTableWidget;
