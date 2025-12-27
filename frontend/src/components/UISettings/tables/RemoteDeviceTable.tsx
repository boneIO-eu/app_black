import React, { useState, useEffect } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import { FaPlus, FaWifi, FaLink } from 'react-icons/fa';

interface AutodiscoveredDevice {
  id: string;
  name: string;
  protocol: string;
  device_type: string;
  outputs?: { id: string; name: string }[];
  covers?: { id: string; name: string }[];
}

interface ManagedByDevice {
  id: string;
  name: string;
  serial: string;
}

interface RemoteDeviceTableProps {
  items: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onAddFromDiscovery?: (device: AutodiscoveredDevice) => void;
}

const RemoteDeviceTable: React.FC<RemoteDeviceTableProps> = ({ items, onEdit, onDelete, onAddFromDiscovery }) => {
  const { t } = useTranslation();
  const [autodiscoveredDevices, setAutodiscoveredDevices] = useState<AutodiscoveredDevice[]>([]);
  const [managedByDevices, setManagedByDevices] = useState<ManagedByDevice[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Fetch autodiscovered devices and managed_by devices
  useEffect(() => {
    const fetchAutodiscovered = async () => {
      setIsLoading(true);
      try {
        const response = await fetch('/api/remote-devices/autodiscovered');
        if (response.ok) {
          const data = await response.json();
          setAutodiscoveredDevices(data.devices || []);
        }
      } catch (error) {
        console.error('Failed to fetch autodiscovered devices:', error);
      } finally {
        setIsLoading(false);
      }
    };

    const fetchManagedBy = async () => {
      try {
        const response = await fetch('/api/remote-devices/managed-by');
        if (response.ok) {
          const data = await response.json();
          setManagedByDevices(data.devices || []);
        }
      } catch (error) {
        console.error('Failed to fetch managed_by devices:', error);
      }
    };

    fetchAutodiscovered();
    fetchManagedBy();
    
    // Refresh every 30 seconds
    const interval = setInterval(() => {
      fetchAutodiscovered();
      fetchManagedBy();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Filter out devices that are already configured
  const configuredIds = new Set(items.map(item => item.id));
  const availableAutodiscovered = autodiscoveredDevices.filter(
    device => !configuredIds.has(device.id)
  );

  return (
    <div className="space-y-6">
      {/* Autodiscovered devices section */}
      {availableAutodiscovered.length > 0 && (
        <div className="bg-base-200 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <FaWifi className="text-success" />
            <h3 className="font-semibold">{t('remote_devices.autodiscovered_title')}</h3>
            <span className="badge badge-success badge-sm">{availableAutodiscovered.length}</span>
          </div>
          <p className="text-sm text-base-content/70 mb-3">
            {t('remote_devices.autodiscovered_hint')}
          </p>
          <div className="overflow-x-auto">
            <Table className="table table-zebra w-full">
              <Thead>
                <Tr>
                  <Th>{t('remote_devices.device_id')}</Th>
                  <Th>{t('remote_devices.device_name')}</Th>
                  <Th>{t('remote_devices.outputs')}</Th>
                  <Th>{t('remote_devices.covers')}</Th>
                  <Th>{t('outputs.actions')}</Th>
                </Tr>
              </Thead>
              <Tbody>
                {availableAutodiscovered.map((device) => (
                  <Tr key={device.id} className="hover:bg-base-300">
                    <Td className="font-mono">{device.id}</Td>
                    <Td>{device.name || device.id}</Td>
                    <Td>
                      <span className="badge badge-outline badge-sm">
                        {device.outputs?.length || 0}
                      </span>
                    </Td>
                    <Td>
                      <span className="badge badge-outline badge-sm">
                        {device.covers?.length || 0}
                      </span>
                    </Td>
                    <Td>
                      <button
                        className="btn btn-success btn-sm gap-1"
                        onClick={() => onAddFromDiscovery?.(device)}
                        title={t('remote_devices.add_from_discovery')}
                      >
                        <FaPlus className="w-3 h-3" />
                        {t('remote_devices.add')}
                      </button>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </div>
        </div>
      )}

      {isLoading && autodiscoveredDevices.length === 0 && (
        <div className="flex items-center gap-2 text-base-content/50">
          <span className="loading loading-spinner loading-sm"></span>
          {t('remote_devices.scanning')}
        </div>
      )}

      {/* Configured devices section */}
      <div className="overflow-x-auto">
        <Table className="table table-zebra w-full">
          <Thead>
            <Tr>
              <Th>{t('remote_devices.device_id')}</Th>
              <Th>{t('remote_devices.device_name')}</Th>
              <Th>{t('remote_devices.protocol')}</Th>
              <Th>{t('remote_devices.device_type')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {items.map((item, index) => (
              <Tr key={index}>
                <Td className="font-mono">{item.id || '-'}</Td>
                <Td>{item.name || '-'}</Td>
                <Td>
                  <span className="badge badge-primary badge-sm">
                    {item.protocol?.toUpperCase() || 'MQTT'}
                  </span>
                </Td>
                <Td>
                  <span className="badge badge-outline badge-sm">
                    {item.device_type === 'boneio_black' ? 'boneIO Black' : 
                     item.device_type === 'esphome' ? 'ESPHome' : 
                     item.device_type || 'generic'}
                  </span>
                </Td>
                <Td>
                  <TableActions
                    onEdit={() => onEdit(index)}
                    onDelete={() => onDelete(index)}
                    editTitle={t('remote_devices.edit')}
                    deleteTitle={t('remote_devices.delete')}
                  />
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </div>

      {/* Managed by section - shows which devices manage this boneIO */}
      {managedByDevices.length > 0 && (
        <div className="bg-base-200 rounded-lg p-4 mt-6">
          <div className="flex items-center gap-2 mb-3">
            <FaLink className="text-info" />
            <h3 className="font-semibold">{t('remote_devices.managed_by_title')}</h3>
            <span className="badge badge-info badge-sm">{managedByDevices.length}</span>
          </div>
          <p className="text-sm text-base-content/70 mb-3">
            {t('remote_devices.managed_by_hint')}
          </p>
          <div className="overflow-x-auto">
            <Table className="table table-zebra w-full">
              <Thead>
                <Tr>
                  <Th>{t('remote_devices.device_name')}</Th>
                  <Th>{t('remote_devices.serial')}</Th>
                </Tr>
              </Thead>
              <Tbody>
                {managedByDevices.map((device) => (
                  <Tr key={device.serial} className="hover:bg-base-300">
                    <Td>{device.name || device.id}</Td>
                    <Td className="font-mono text-sm">{device.serial}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </div>
        </div>
      )}
    </div>
  );
};

export default RemoteDeviceTable;
