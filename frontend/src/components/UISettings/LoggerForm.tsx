import React, { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';

interface LoggerFormProps {
  data: any;
  onChange: (data: any) => void;
}

const LOG_LEVELS = ['debug', 'info', 'warning', 'error', 'critical'];

/**
 * Custom form for Logger section configuration.
 * Fields: default (log level), logs (module-specific log levels)
 */
const LoggerForm: React.FC<LoggerFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const [newModule, setNewModule] = useState('');

  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleLogChange = (module: string, level: string) => {
    const logs = { ...(data?.logs || {}) };
    logs[module] = level;
    handleChange('logs', logs);
  };

  const handleAddModule = () => {
    if (newModule.trim() && !data?.logs?.[newModule.trim()]) {
      const logs = { ...(data?.logs || {}) };
      logs[newModule.trim()] = 'info';
      handleChange('logs', logs);
      setNewModule('');
    }
  };

  const handleRemoveModule = (module: string) => {
    const logs = { ...(data?.logs || {}) };
    delete logs[module];
    handleChange('logs', logs);
  };

  return (
    <div className="space-y-6">
      {/* Default Log Level */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('logger.default_level')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.default || 'info'}
          onChange={(e) => handleChange('default', e.target.value)}
        >
          {LOG_LEVELS.map((level) => (
            <option key={level} value={level}>
              {level.toUpperCase()}
            </option>
          ))}
        </select>
        <p className="text-xs text-base-content/60 mt-1">
          {t('logger.default_level_help')}
        </p>
      </div>

      {/* Module-specific Log Levels */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('logger.module_levels')}</span>
        </label>
        
        {/* Existing modules */}
        <div className="space-y-2">
          {Object.entries(data?.logs || {}).map(([module, level]) => (
            <div key={module} className="flex gap-2 items-center">
              <input
                type="text"
                className="input input-bordered flex-1"
                value={module}
                disabled
              />
              <select
                className="select select-bordered w-32"
                value={level as string}
                onChange={(e) => handleLogChange(module, e.target.value)}
              >
                {LOG_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {l.toUpperCase()}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-ghost btn-square btn-sm text-error"
                onClick={() => handleRemoveModule(module)}
                title={t('logger.remove_module')}
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>

        {/* Add new module */}
        <div className="flex gap-2 items-center mt-3">
          <input
            type="text"
            className="input input-bordered flex-1"
            placeholder="e.g., boneio.modbus, pymodbus"
            value={newModule}
            onChange={(e) => setNewModule(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddModule()}
          />
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handleAddModule}
            disabled={!newModule.trim()}
          >
            <Plus size={16} />
            {t('logger.add')}
          </button>
        </div>
        
        <p className="text-xs text-base-content/60 mt-1">
          {t('logger.module_levels_help')}
        </p>
      </div>
    </div>
  );
};

export default LoggerForm;
