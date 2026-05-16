/**
 * MCP hardware override fields — Presentational layer.
 *
 * All state and side-effects live in `useMcpHardware`. This component only
 * renders the collapsible "Advanced → Hardware" panel inside OutputForm.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import {
  MCP_DEFAULT_VALUE,
  useMcpHardware,
  type UseMcpHardwareArgs,
} from '../hooks/useMcpHardware';

export interface McpHardwareFieldsProps extends UseMcpHardwareArgs {
  disabled?: boolean;
  getFieldDescription: (fieldName: string) => string;
}

const McpHardwareFields: React.FC<McpHardwareFieldsProps> = ({
  data,
  mcp23017,
  isNew = false,
  disabled,
  onChange,
  getFieldDescription,
}) => {
  const { t } = useTranslation();
  const h = useMcpHardware({ data, mcp23017, isNew, onChange });

  const toggleDisabled = disabled || (h.isExpanderOutput && !isNew);

  return (
    <div className="col-span-full">
      <div className="bg-base-200 rounded-box overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2 font-medium text-sm">
            {t('outputs.divider_hardware')}
            <span className="text-base-content/50 font-normal"> - {t('settings.advanced_settings')}</span>
            {h.hasOverride && (
              <span className="badge badge-primary badge-sm">
                {data.mcp_id} / {t('outputs.mcp_pin_short')} {h.pinValue}
              </span>
            )}
          </div>
          <input
            type="checkbox"
            className="toggle toggle-primary toggle-sm"
            checked={h.expanded}
            onChange={h.toggle}
            disabled={toggleDisabled}
            title={h.isExpanderOutput && !isNew ? t('outputs.mcp_expander_output_locked') : undefined}
          />
        </div>

        {h.expanded && (
          <div className="px-4 pb-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('outputs.mcp_id')}</span>
                </label>
                <Select
                  value={h.hasOverride ? data.mcp_id : MCP_DEFAULT_VALUE}
                  onValueChange={h.setMcpId}
                  disabled={disabled}
                >
                  <SelectTrigger className={`w-full ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}>
                    <SelectValue placeholder={t('outputs.mcp_id_placeholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={MCP_DEFAULT_VALUE}>{t('outputs.mcp_id_board_default')}</SelectItem>
                    {h.mcpIdOptions.map((mcpId) => (
                      <SelectItem key={mcpId} value={mcpId}>{mcpId}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <label className="label">
                  <span className="label-text-alt whitespace-normal wrap-break-word">
                    {getFieldDescription('mcp_id') || t('outputs.mcp_id_hint')}
                  </span>
                </label>
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('outputs.mcp_pin')}</span>
                </label>
                <Select
                  value={h.pinValue}
                  onValueChange={h.setPin}
                  disabled={disabled || !h.hasOverride}
                >
                  <SelectTrigger
                    className={`w-full ${disabled || !h.hasOverride ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <SelectValue placeholder={t('outputs.mcp_pin_placeholder')}>
                      {h.pinValue}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {h.pinOptions.map((pin) => (
                      <SelectItem key={pin} value={String(pin)}>
                        {String(pin)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <label className="label">
                  <span className="label-text-alt whitespace-normal wrap-break-word">
                    {getFieldDescription('pin') || t('outputs.mcp_pin_hint')}
                  </span>
                </label>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default McpHardwareFields;
