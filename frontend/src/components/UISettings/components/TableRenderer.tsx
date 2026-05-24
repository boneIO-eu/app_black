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
import GenericTable from '../tables/GenericTable';

interface TableRendererProps {
  sectionType: string;
  items: any[];
  allAreas: any[];
  allOutputs: any[];
  allCovers: any[];
  allRemoteDevices: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onDuplicate?: (index: number) => void;
  onAddFromDiscovery: (device: any) => void;
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
      return <RemoteDeviceTable {...commonProps} onAddFromDiscovery={onAddFromDiscovery} />;
    case 'template':
      return <TemplateTable {...commonProps} allAreas={allAreas} onDuplicate={onDuplicate} />;
    case 'adc':
      return <ADCTable {...commonProps} allAreas={allAreas} />;
    case 'board_sensors':
      return <BoardSensorsTable {...commonProps} />;
    case 'remote_outputs':
      return <RemoteOutputTable {...commonProps} allAreas={allAreas} allRemoteDevices={allRemoteDevices} />;
    default:
      return <GenericTable {...commonProps} />;
  }
};

export default TableRenderer;
