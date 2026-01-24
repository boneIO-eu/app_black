import React, { useState, useEffect } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import { FaPlus, FaWifi, FaLink, FaSync, FaSearch, FaTrash } from 'react-icons/fa';

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
  onUpdateItem?: (index: number, updatedItem: any) => void;
}

const RemoteDeviceTable: React.FC<RemoteDeviceTableProps> = ({ items, onEdit, onDelete, onAddFromDiscovery, onUpdateItem }) => {
  const { t } = useTranslation();
  const [autodiscoveredDevices, setAutodiscoveredDevices] = useState<AutodiscoveredDevice[]>([]);
  const [managedByDevices, setManagedByDevices] = useState<ManagedByDevice[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [discoveringIndex, setDiscoveringIndex] = useState<number | null>(null);
  const [scanningNetwork, setScanningNetwork] = useState(false);
  const [scannedEsphomeDevices, setScannedEsphomeDevices] = useState<{name: string; host: string; ip: string; port: number}[]>([]);
  const [scanningWled, setScanningWled] = useState(false);
  const [scannedWledDevices, setScannedWledDevices] = useState<{name: string; host: string; ip: string; port: number}[]>([]);
  const [removingDeviceId, setRemovingDeviceId] = useState<string | null>(null);

  // Fetch autodiscovered devices and managed_by devices
  useEffect(() => {
    const fetchAutodiscovered = async () => {
      setIsLoading(true);
      try {
        const { data } = await axios.get('/api/remote-devices/autodiscovered');
        setAutodiscoveredDevices(data.devices || []);
      } catch (error) {
        console.error('Failed to fetch autodiscovered devices:', error);
      } finally {
        setIsLoading(false);
      }
    };

    const fetchManagedBy = async () => {
      try {
        const { data } = await axios.get('/api/remote-devices/managed-by');
        setManagedByDevices(data.devices || []);
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
  
  console.log('RemoteDeviceTable debug:', {
    autodiscoveredDevices,
    configuredIds: Array.from(configuredIds),
    availableAutodiscovered,
    items
  });

  /**
   * Remove an autodiscovered device and clear MQTT retained messages
   */
  const removeAutodiscoveredDevice = async (deviceId: string) => {
    const confirmMessage = t('remote_devices.remove_autodiscovered_confirm') || 
      'This will clear MQTT retained messages for this device. Continue?';
    
    if (!confirm(confirmMessage)) {
      return;
    }

    setRemovingDeviceId(deviceId);
    try {
      await axios.delete(`/api/remote-devices/autodiscovered/${deviceId}`);
      // Refresh the autodiscovered devices list
      const { data } = await axios.get('/api/remote-devices/autodiscovered');
      setAutodiscoveredDevices(data.devices || []);
    } catch (error) {
      console.error('Failed to remove autodiscovered device:', error);
      alert('Failed to remove device. Please try again.');
    } finally {
      setRemovingDeviceId(null);
    }
  };

  /**
   * Scan network for ESPHome devices via mDNS
   */
  const scanEsphomeNetwork = async () => {
    setScanningNetwork(true);
    setScannedEsphomeDevices([]);
    try {
      const { data } = await axios.get('/api/remote-devices/scan-esphome?timeout=3');
      setScannedEsphomeDevices(data.devices || []);
    } catch (error) {
      console.error('Failed to scan ESPHome network:', error);
    } finally {
      setScanningNetwork(false);
    }
  };

  /**
   * Scan network for WLED devices via mDNS
   */
  const scanWledNetwork = async () => {
    setScanningWled(true);
    setScannedWledDevices([]);
    try {
      const { data } = await axios.get('/api/remote-devices/scan-wled?timeout=3');
      setScannedWledDevices(data.devices || []);
    } catch (error) {
      console.error('Failed to scan WLED network:', error);
    } finally {
      setScanningWled(false);
    }
  };

  /**
   * Discover entities for an ESPHome device
   */
  const discoverEsphomeEntities = async (index: number, item: any) => {
    const esphomeConfig = item?.esphome_api;
    if (!esphomeConfig?.host) {
      console.error('No host configured for ESPHome device');
      return;
    }

    setDiscoveringIndex(index);
    try {
      const { data: result } = await axios.post('/api/remote-devices/discover-esphome', {
        host: esphomeConfig.host,
        port: esphomeConfig.port || 6053,
        password: esphomeConfig.password || '',
        encryption_key: esphomeConfig.encryption_key || '',
      });
      
      // Update the item with discovered entities
      const updatedItem = {
        ...item,
        esphome_api: {
          ...esphomeConfig,
          switches: result.switches || [],
          lights: result.lights || [],
          covers: result.covers || [],
        },
      };
      
      onUpdateItem?.(index, updatedItem);
    } catch (error) {
      console.error('ESPHome discovery failed:', error);
    } finally {
      setDiscoveringIndex(null);
    }
  };

  /**
   * Get entity counts for an ESPHome device
   */
  const getEsphomeEntityCounts = (item: any) => {
    const esphome = item?.esphome_api;
    if (!esphome) return null;
    const switches = esphome.switches?.length || 0;
    const lights = esphome.lights?.length || 0;
    const covers = esphome.covers?.length || 0;
    return { switches, lights, covers, total: switches + lights + covers };
  };

  // Check if we have any discovered devices (BoneIO, ESPHome, or WLED)
  const hasDiscoveredDevices = availableAutodiscovered.length > 0 || scannedEsphomeDevices.length > 0 || scannedWledDevices.length > 0;
  const totalDiscovered = availableAutodiscovered.length + scannedEsphomeDevices.length + scannedWledDevices.length;

  return (
    <div className="space-y-6">
      {/* Autodiscovered devices section - includes both BoneIO and ESPHome */}
      <div className="bg-base-200 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <FaWifi className="text-success" />
          <h3 className="font-semibold">{t('remote_devices.autodiscovered_title')}</h3>
          {totalDiscovered > 0 && (
            <span className="badge badge-success badge-sm">{totalDiscovered}</span>
          )}
          <div className="grow" />
          <button
            className={`btn btn-sm btn-secondary gap-1 ${scanningNetwork ? 'loading' : ''}`}
            onClick={scanEsphomeNetwork}
            disabled={scanningNetwork}
            title={t('remote_devices.scan_network') || 'Scan for ESPHome devices'}
          >
            <FaSearch className="w-3 h-3" />
            {scanningNetwork ? (t('remote_devices.scanning') || 'Scanning...') : (t('remote_devices.scan_esphome') || 'Scan ESPHome')}
          </button>
          <button
            className={`btn btn-sm btn-accent gap-1 ${scanningWled ? 'loading' : ''}`}
            onClick={scanWledNetwork}
            disabled={scanningWled}
            title={t('remote_devices.scan_wled') || 'Scan for WLED devices'}
          >
            <FaSearch className="w-3 h-3" />
            {scanningWled ? (t('remote_devices.scanning') || 'Scanning...') : (t('remote_devices.scan_wled') || 'Scan WLED')}
          </button>
        </div>
        <p className="text-sm text-base-content/70 mb-3">
          {t('remote_devices.autodiscovered_hint')}
        </p>
        
        {(isLoading || scanningNetwork) && !hasDiscoveredDevices && (
          <div className="flex items-center gap-2 text-base-content/50 py-4">
            <span className="loading loading-spinner loading-sm"></span>
            {t('remote_devices.scanning')}
          </div>
        )}

        {hasDiscoveredDevices && (
          <div className="overflow-x-auto">
            <Table className="table table-zebra w-full">
              <Thead>
                <Tr>
                  <Th>{t('remote_devices.device_id')}</Th>
                  <Th>{t('remote_devices.device_name')}</Th>
                  <Th>{t('remote_devices.protocol')}</Th>
                  <Th>{t('remote_devices.outputs')}/{t('remote_devices.covers')}</Th>
                  <Th>{t('outputs.actions')}</Th>
                </Tr>
              </Thead>
              <Tbody>
                {/* BoneIO Black autodiscovered devices */}
                {availableAutodiscovered.map((device) => (
                  <Tr key={device.id} className="hover:bg-base-300">
                    <Td className="font-mono">{device.id}</Td>
                    <Td>{device.name || device.id}</Td>
                    <Td>
                      <span className="badge badge-primary badge-sm">MQTT</span>
                    </Td>
                    <Td>
                      <span className="badge badge-outline badge-sm mr-1">
                        {device.outputs?.length || 0} out
                      </span>
                      <span className="badge badge-outline badge-sm">
                        {device.covers?.length || 0} cov
                      </span>
                    </Td>
                    <Td>
                      <div className="flex gap-1">
                        <button
                          className="btn btn-success btn-sm gap-1"
                          onClick={() => onAddFromDiscovery?.(device)}
                          title={t('remote_devices.add_from_discovery')}
                        >
                          <FaPlus className="w-3 h-3" />
                          {t('remote_devices.add')}
                        </button>
                        <button
                          className={`btn btn-error btn-sm gap-1 ${removingDeviceId === device.id ? 'loading' : ''}`}
                          onClick={() => removeAutodiscoveredDevice(device.id)}
                          disabled={removingDeviceId === device.id}
                          title={t('remote_devices.remove_autodiscovered') || 'Remove'}
                        >
                          <FaTrash className="w-3 h-3" />
                        </button>
                      </div>
                    </Td>
                  </Tr>
                ))}
                {/* ESPHome scanned devices */}
                {scannedEsphomeDevices.map((device, idx) => (
                  <Tr key={`esphome-${idx}`} className="hover:bg-base-300">
                    <Td className="font-mono text-xs">
                      <div className="flex flex-col">
                        <span>{device.host}</span>
                        {device.ip && device.ip !== device.host && (
                          <span className="text-xs opacity-50">IP: {device.ip}</span>
                        )}
                      </div>
                    </Td>
                    <Td>{device.name}</Td>
                    <Td>
                      <span className="badge badge-secondary badge-sm">ESPHome</span>
                    </Td>
                    <Td>
                      <span className="text-xs opacity-60">:{device.port}</span>
                    </Td>
                    <Td>
                      <button
                        className="btn btn-success btn-sm gap-1"
                        onClick={() => onAddFromDiscovery?.({
                          id: device.name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
                          name: device.name,
                          protocol: 'esphome_api',
                          device_type: 'esphome',
                          outputs: [],
                          covers: [],
                          // Pass ESPHome specific data - use hostname (mDNS) instead of IP for stability
                          esphome_api: {
                            host: device.host,
                            port: device.port,
                          }
                        } as any)}
                        title={t('remote_devices.add_from_discovery')}
                      >
                        <FaPlus className="w-3 h-3" />
                        {t('remote_devices.add')}
                      </button>
                    </Td>
                  </Tr>
                ))}
                {/* WLED scanned devices */}
                {scannedWledDevices.map((device, idx) => (
                  <Tr key={`wled-${idx}`} className="hover:bg-base-300">
                    <Td className="font-mono text-xs">
                      <div className="flex flex-col">
                        <span>{device.host}</span>
                        {device.ip && device.ip !== device.host && (
                          <span className="text-xs opacity-50">IP: {device.ip}</span>
                        )}
                      </div>
                    </Td>
                    <Td>{device.name}</Td>
                    <Td>
                      <span className="badge badge-accent badge-sm">WLED</span>
                    </Td>
                    <Td>
                      <span className="text-xs opacity-60">:{device.port}</span>
                    </Td>
                    <Td>
                      <button
                        className="btn btn-success btn-sm gap-1"
                        onClick={() => onAddFromDiscovery?.({
                          id: device.name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
                          name: device.name,
                          protocol: 'wled',
                          device_type: 'wled',
                          outputs: [],
                          covers: [],
                          wled: {
                            host: device.host,
                            port: device.port,
                          }
                        } as any)}
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
        )}

        {!isLoading && !scanningNetwork && !scanningWled && !hasDiscoveredDevices && (
          <p className="text-sm text-base-content/50 py-2">
            {t('remote_devices.no_discovered') || 'No devices discovered. BoneIO devices appear automatically, click "Scan ESPHome" or "Scan WLED" to find devices.'}
          </p>
        )}
      </div>

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
                  <div className="flex items-center gap-2">
                    {/* Discover button for ESPHome devices */}
                    {item.protocol === 'esphome_api' && (
                      <button
                        className={`btn btn-xs btn-secondary ${discoveringIndex === index ? 'loading' : ''}`}
                        onClick={() => discoverEsphomeEntities(index, item)}
                        disabled={discoveringIndex === index}
                        title={t('remote_devices.discover_entities') || 'Discover Entities'}
                      >
                        {discoveringIndex !== index && <FaSync className="w-3 h-3" />}
                        {(() => {
                          const counts = getEsphomeEntityCounts(item);
                          if (counts && counts.total > 0) {
                            return (
                              <span className="badge badge-xs badge-success ml-1">
                                {counts.total}
                              </span>
                            );
                          }
                          return null;
                        })()}
                      </button>
                    )}
                    <TableActions
                      onEdit={() => onEdit(index)}
                      onDelete={() => onDelete(index)}
                      editTitle={t('remote_devices.edit')}
                      deleteTitle={t('remote_devices.delete')}
                    />
                  </div>
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
