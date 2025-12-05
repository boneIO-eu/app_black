import React, { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

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
          <span className="label-text font-medium">Default Log Level</span>
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
        <label className="label">
          <span className="label-text-alt text-base-content/60">
            Default logging level for the application
          </span>
        </label>
      </div>

      {/* Module-specific Log Levels */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Module-specific Log Levels</span>
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
                title="Remove module"
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
            Add
          </button>
        </div>
        
        <label className="label">
          <span className="label-text-alt text-base-content/60">
            Set custom log levels for specific Python modules (e.g., boneio.modbus, pymodbus.logging)
          </span>
        </label>
      </div>
    </div>
  );
};

export default LoggerForm;
