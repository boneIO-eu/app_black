import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  MCP_ADDRESS_OPTIONS,
  MANAGED_EXPANDER_IDS,
  DEFAULT_ADDRESSES,
  DEFAULT_ADDRESS_INTEGERS,
  isExpanderOutput,
  type McpAddress,
  type ManagedExpanderId,
} from './modules/expander';

interface Mcp23017Data {
  id: string;
  address: string | number;
  init_sleep?: string | number;
}

interface Mcp23017FormProps {
  data: Mcp23017Data[];
  onChange: (data: Mcp23017Data[]) => void;
  allOutputs?: any[];
}

const toHexAddress = (address: string | number, fallback: McpAddress = '0x20'): string => {
  if (typeof address === 'number') return `0x${address.toString(16)}`;
  if (typeof address === 'string') {
    if (address.startsWith('0x')) return address.toLowerCase();
    const num = parseInt(address, 10);
    if (!isNaN(num)) return `0x${num.toString(16)}`;
  }
  return fallback;
};

const Mcp23017Form: React.FC<Mcp23017FormProps> = ({ data, onChange, allOutputs = [] }) => {
  const { t } = useTranslation();

  // Expander is configured when there are EX_* outputs in the config
  const hasExpander = allOutputs.some(isExpanderOutput);

  const getAddress = (id: ManagedExpanderId): string => {
    const entry = data.find(e => e.id === id);
    return entry ? toHexAddress(entry.address, DEFAULT_ADDRESSES[id]) : DEFAULT_ADDRESSES[id];
  };

  const updateAddress = (id: ManagedExpanderId, address: string) => {
    const ids: ManagedExpanderId[] = hasExpander
      ? ['mcp_left', 'mcp_right', 'expander_left', 'expander_right']
      : ['mcp_left', 'mcp_right'];
    onChange(
      ids.map(eid => ({ id: eid, address: eid === id ? address : getAddress(eid) }))
    );
  };

  const AddressCard = ({ id, label, description }: { id: ManagedExpanderId; label: string; description: string }) => (
    <div className="card bg-base-200 shadow-sm">
      <div className="card-body py-4">
        <div className="flex items-center gap-2">
          <span className="badge badge-outline badge-sm font-mono">{id}</span>
          <span className="font-medium text-sm">{label}</span>
        </div>
        <p className="text-xs text-base-content/60">{description}</p>
        <div className="form-control mt-2">
          <select
            className="select select-bordered select-sm w-full"
            value={getAddress(id)}
            onChange={e => updateAddress(id, e.target.value)}
          >
            {MCP_ADDRESS_OPTIONS.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="alert alert-info py-2 text-sm">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-5 h-5">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>{t('mcp.info_description')}</span>
      </div>

      {/* Onboard MCP chips */}
      <div>
        <h3 className="font-semibold text-sm text-base-content/70 uppercase tracking-wide mb-3">
          {t('mcp.section_onboard')}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <AddressCard id="mcp_left"  label={t('mcp.chip_left')}  description={t('mcp.left_description')} />
          <AddressCard id="mcp_right" label={t('mcp.chip_right')} description={t('mcp.right_description')} />
        </div>
      </div>

      {/* Expander chips (only when expander is configured) */}
      {hasExpander && (
        <div>
          <h3 className="font-semibold text-sm text-base-content/70 uppercase tracking-wide mb-3">
            {t('mcp.section_expander')}
          </h3>
          <p className="text-xs text-base-content/60 mb-3">{t('mcp.expander_managed_in_boneio')}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <AddressCard id="expander_left"  label={t('mcp.expander_chip_left')}  description={t('mcp.expander_left_description')} />
            <AddressCard id="expander_right" label={t('mcp.expander_chip_right')} description={t('mcp.expander_right_description')} />
          </div>
        </div>
      )}
    </div>
  );
};

export default Mcp23017Form;

// Backwards-compatible re-exports — old consumers may import from this file.
// The canonical source is `modules/expander`; remove these re-exports once all
// upstream files have migrated to the module API.
export { DEFAULT_ADDRESSES, DEFAULT_ADDRESS_INTEGERS, MANAGED_EXPANDER_IDS };
export type { ManagedExpanderId };
