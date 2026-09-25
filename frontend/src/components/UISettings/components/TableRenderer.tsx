/**
 * TableRenderer - Renders the appropriate table component for a section type.
 * Extracted from ArrayTableWidget to simplify the rendering switch.
 */
import React from 'react';
import { formatTimeperiod } from '@/utils/formatters';
import AreasTable from '../tables/AreasTable';
import OutputTable from '../tables/OutputTable';
import OutputGroupTable from '../tables/OutputGroupTable';
import CoverTable from '../tables/CoverTable';
import BinarySensorEventTable from '../tables/BinarySensorEventTable';
import ModbusDeviceTable from '../tables/ModbusDeviceTable';
import SensorTable from '../tables/SensorTable';
import VirtualEnergySensorTable from '../tables/VirtualEnergySensorTable';
import RemoteDeviceTable from '../tables/RemoteDeviceTable';
import TemplateTable from '../tables/TemplateTable';
import ADCTable from '../tables/ADCTable';
import BoardSensorsTable from '../tables/BoardSensorsTable';
import RemoteOutputTable from '../tables/RemoteOutputTable';
import VirtualSwitchTable from '../tables/VirtualSwitchTable';
import ScheduleTable from '../tables/ScheduleTable';
import GenericTable from '../tables/GenericTable';
import type { AutodiscoveredDevice, RemoteDeviceRow } from '../tables/RemoteDeviceTable';
import type { AreaEntity, CoverEntity, OutputEntity, RemoteDeviceEntity } from '@/types/config';
import type { ConfigRecord } from '@/types/jsonSchema';
import type { SwitchEntry } from '../helpers/virtualSwitchEdges';
import type { ScheduleEntry } from '../helpers/scheduleTrigger';

/** Rows arrive as ConfigRecord. The template (`platform`), virtual switch,
 *  schedule and remote device (`id`) row types have required fields, so those
 *  rows are cast. TemplateTable does not export its row type. */
type TemplateRow = React.ComponentProps<typeof TemplateTable>['items'][number];

interface TableRendererProps {
  sectionType: string;
  items: ConfigRecord[];
  allAreas: AreaEntity[];
  allOutputs: OutputEntity[];
  allCovers: CoverEntity[];
  allRemoteDevices: RemoteDeviceEntity[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onDuplicate?: (index: number) => void;
  onAddFromDiscovery: (device: AutodiscoveredDevice) => void;
  /** True while the section has edits that have not been saved.
   *  Only the schedules table reads it, to keep "run now" off a draft. */
  isDirty?: boolean;
}

/**
 * Renders the correct table view for the given section type.
 */
const TableRenderer: React.FC<TableRendererProps> = ({
  sectionType,
  items,
  allAreas,
  allOutputs,
  allCovers,
  allRemoteDevices,
  onEdit,
  onDelete,
  onDuplicate,
  onAddFromDiscovery,
  isDirty,
}) => {
  const commonProps = { items, onEdit, onDelete };

  switch (sectionType) {
    case 'output':
      return <OutputTable {...commonProps} allAreas={allAreas} />;
    case 'output_group':
      return <OutputGroupTable {...commonProps} allAreas={allAreas} allCovers={allCovers} />;
    case 'cover':
      return <CoverTable {...commonProps} allAreas={allAreas} />;
    case 'binary_sensor':
    case 'event':
    case 'local_inputs':
    case 'remote_inputs':
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
      return <RemoteDeviceTable {...commonProps} items={items as RemoteDeviceRow[]} onAddFromDiscovery={onAddFromDiscovery} />;
    case 'template':
      return <TemplateTable {...commonProps} items={items as (ConfigRecord & TemplateRow)[]} allAreas={allAreas} onDuplicate={onDuplicate} />;
    case 'adc':
      return <ADCTable {...commonProps} allAreas={allAreas} />;
    case 'board_sensors':
      return <BoardSensorsTable {...commonProps} />;
    case 'remote_outputs':
      return <RemoteOutputTable {...commonProps} allAreas={allAreas} allRemoteDevices={allRemoteDevices} />;
    case 'virtual_switch':
      return <VirtualSwitchTable {...commonProps} items={items as SwitchEntry[]} allAreas={allAreas} />;
    case 'schedule':
      return <ScheduleTable {...commonProps} items={items as ScheduleEntry[]} isDirty={isDirty} />;
    default:
      return <GenericTable {...commonProps} />;
  }
};

export default TableRenderer;
