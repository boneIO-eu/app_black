import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import HelpLabel from './components/HelpLabel';

interface LoxFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for Lox UDP section configuration.
 * Fields: host, send_port, listen_port + download template button.
 */
const LoxForm: React.FC<LoxFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();

  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleDownloadTemplate = () => {
    window.open('/api/config/lox-template', '_blank');
  };

  const handleViewCommands = async () => {
    window.open('/api/config/lox-commands', '_blank');
  };

  return (
    <div className="space-y-4">
      {/* Host */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('lox_config.host')} <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.host || ''}
          onChange={(e) => handleChange('host', e.target.value)}
          placeholder="192.168.1.100"
          required
        />
        <HelpLabel>{t('lox_config.host_help')}</HelpLabel>
      </div>

      {/* Send Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('lox_config.send_port')}</span>
        </label>
        <input
          type="number"
          className="input input-bordered w-full"
          value={data?.send_port ?? 4444}
          onChange={(e) => handleChange('send_port', parseInt(e.target.value) || 4444)}
          placeholder="4444"
        />
        <HelpLabel>{t('lox_config.send_port_help')}</HelpLabel>
      </div>

      {/* Listen Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('lox_config.listen_port')}</span>
        </label>
        <input
          type="number"
          className="input input-bordered w-full"
          value={data?.listen_port ?? 4445}
          onChange={(e) => handleChange('listen_port', parseInt(e.target.value) || 4445)}
          placeholder="4445"
        />
        <HelpLabel>{t('lox_config.listen_port_help')}</HelpLabel>
      </div>

      {/* Lox Config Template Actions */}
      <div className="divider">{t('lox_config.template_section')}</div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={handleDownloadTemplate}
        >
          📥 {t('lox_config.download_template')}
        </button>

        <button
          type="button"
          className="btn btn-outline btn-sm btn-ghost"
          onClick={handleViewCommands}
        >
          📋 {t('lox_config.view_commands')}
        </button>
      </div>

      <HelpLabel>{t('lox_config.template_help')}</HelpLabel>
    </div>
  );
};

export default LoxForm;
