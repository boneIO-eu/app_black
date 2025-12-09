import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface Mcp23017Data {
  id: string;
  address: string | number;
  init_sleep?: string | number;
}

interface Mcp23017FormProps {
  data: Mcp23017Data[];
  onChange: (data: Mcp23017Data[]) => void;
}

/**
 * Convert address to hex string format (0x20, 0x21, etc.)
 * Handles both number (35, 36) and string ("0x23", "0x24") inputs.
 */
const toHexAddress = (address: string | number): string => {
  if (typeof address === 'number') {
    return `0x${address.toString(16)}`;
  }
  if (typeof address === 'string') {
    // Already hex format
    if (address.startsWith('0x')) {
      return address.toLowerCase();
    }
    // Decimal string
    const num = parseInt(address, 10);
    if (!isNaN(num)) {
      return `0x${num.toString(16)}`;
    }
  }
  return '0x20'; // fallback
};

/**
 * Form for editing MCP23017 I2C expander addresses.
 * 
 * Only allows editing addresses for mcp_left and mcp_right,
 * as these are the only IDs supported by the output configuration.
 */
const Mcp23017Form: React.FC<Mcp23017FormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  
  // Normalize entries - convert addresses to hex format
  const normalizeEntries = (entries: Mcp23017Data[]): Mcp23017Data[] => {
    return entries.map(entry => ({
      ...entry,
      address: toHexAddress(entry.address)
    }));
  };
  
  // Ensure we always have both mcp_left and mcp_right entries
  const ensureDefaultEntries = (entries: Mcp23017Data[]): Mcp23017Data[] => {
    const normalized = normalizeEntries(entries);
    
    const leftEntry = normalized.find(e => e.id === 'mcp_left');
    const rightEntry = normalized.find(e => e.id === 'mcp_right');
    
    // Only add defaults if no entries exist at all
    const result: Mcp23017Data[] = [];
    
    if (leftEntry) {
      result.push(leftEntry);
    } else if (normalized.length === 0) {
      result.push({ id: 'mcp_left', address: '0x20' });
    }
    
    if (rightEntry) {
      result.push(rightEntry);
    } else if (normalized.length === 0) {
      result.push({ id: 'mcp_right', address: '0x21' });
    }
    
    // Include any existing entries that are mcp_left or mcp_right
    return result.length > 0 ? result : normalized.filter(e => e.id === 'mcp_left' || e.id === 'mcp_right');
  };
  
  const mcpEntries = ensureDefaultEntries(data || []);
  
  // Get entry by ID with hex-formatted address
  const getEntry = (id: string): Mcp23017Data => {
    const entry = mcpEntries.find(e => e.id === id);
    if (entry) {
      return { ...entry, address: toHexAddress(entry.address) };
    }
    return { id, address: id === 'mcp_left' ? '0x20' : '0x21' };
  };
  
  // Update address for specific ID - always save both entries
  const updateAddress = (id: string, address: string) => {
    const leftAddr = id === 'mcp_left' ? address : toHexAddress(getEntry('mcp_left').address);
    const rightAddr = id === 'mcp_right' ? address : toHexAddress(getEntry('mcp_right').address);
    
    // Always output both mcp_left and mcp_right
    const newData: Mcp23017Data[] = [
      { id: 'mcp_left', address: leftAddr },
      { id: 'mcp_right', address: rightAddr }
    ];
    onChange(newData);
  };
  
  // Common I2C addresses for MCP23017
  const commonAddresses = [
    { value: '0x20', label: '0x20' },
    { value: '0x21', label: '0x21' },
    { value: '0x22', label: '0x22' },
    { value: '0x23', label: '0x23' },
    { value: '0x24', label: '0x24' },
    { value: '0x25', label: '0x25' },
    { value: '0x26', label: '0x26' },
    { value: '0x27', label: '0x27' },
  ];
  
  const leftEntry = getEntry('mcp_left');
  const rightEntry = getEntry('mcp_right');
  
  return (
    <div className="space-y-6">
      <div className="alert alert-info">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>
        <div>
          <p className="font-medium">{t('mcp.info_title')}</p>
          <p className="text-sm">{t('mcp.info_description')}</p>
        </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* MCP Left */}
        <div className="card bg-base-200 shadow-sm">
          <div className="card-body">
            <h3 className="card-title text-lg">
              <span className="badge badge-primary">mcp_left</span>
            </h3>
            <p className="text-sm text-base-content/70">{t('mcp.left_description')}</p>
            
            <div className="form-control mt-4">
              <label className="label">
                <span className="label-text font-medium">{t('mcp.address')}</span>
              </label>
              <select
                className="select select-bordered w-full"
                value={String(leftEntry.address)}
                onChange={(e) => updateAddress('mcp_left', e.target.value)}
              >
                {commonAddresses.map(addr => (
                  <option key={addr.value} value={addr.value}>
                    {addr.label}
                  </option>
                ))}
              </select>
              <label className="label">
                <span className="label-text-alt">{t('mcp.address_hint')}</span>
              </label>
            </div>
          </div>
        </div>
        
        {/* MCP Right */}
        <div className="card bg-base-200 shadow-sm">
          <div className="card-body">
            <h3 className="card-title text-lg">
              <span className="badge badge-secondary">mcp_right</span>
            </h3>
            <p className="text-sm text-base-content/70">{t('mcp.right_description')}</p>
            
            <div className="form-control mt-4">
              <label className="label">
                <span className="label-text font-medium">{t('mcp.address')}</span>
              </label>
              <select
                className="select select-bordered w-full"
                value={String(rightEntry.address)}
                onChange={(e) => updateAddress('mcp_right', e.target.value)}
              >
                {commonAddresses.map(addr => (
                  <option key={addr.value} value={addr.value}>
                    {addr.label}
                  </option>
                ))}
              </select>
              <label className="label">
                <span className="label-text-alt">{t('mcp.address_hint')}</span>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Mcp23017Form;
