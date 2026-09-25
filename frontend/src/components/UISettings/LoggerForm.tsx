import React, { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';
import { NoticeCallout } from './ui';

/** The `logger` section as edited here (other keys pass through untouched). */
interface LoggerFormData {
  [key: string]: unknown;
  default?: string;
  /** Module name -> log level. */
  logs?: Record<string, string>;
}

interface LoggerFormProps {
  data: LoggerFormData;
  onChange: (data: LoggerFormData) => void;
}

const LOG_LEVELS = ['debug', 'info', 'warning', 'error', 'critical'];

// Common modules with recommended log levels
const COMMON_MODULES = [
  { module: 'boneio.relay', level: 'info', description: 'Output/relay control' },
  { module: 'boneio.modbus', level: 'warning', description: 'Modbus communication' },
  { module: 'boneio.input', level: 'info', description: 'Input events' },
  { module: 'boneio.cover', level: 'info', description: 'Cover control' },
  { module: 'pymodbus.client', level: 'warning', description: 'Modbus client library' },
  { module: 'pymodbus.logging', level: 'error', description: 'Modbus logging (verbose)' },
  { module: 'asyncio', level: 'warning', description: 'Async operations' },
  { module: 'aiohttp', level: 'warning', description: 'HTTP client/server' },
];

/**
 * Custom form for Logger section configuration.
 * Fields: default (log level), logs (module-specific log levels)
 */
const LoggerForm: React.FC<LoggerFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const [newModule, setNewModule] = useState('');
  const [showExamples, setShowExamples] = useState(false);

  const handleChange = (field: string, value: unknown) => {
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

  const handleAddCommonModule = (module: string, level: string) => {
    if (!data?.logs?.[module]) {
      const logs = { ...(data?.logs || {}) };
      logs[module] = level;
      handleChange('logs', logs);
    }
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

      {/* Common Modules - Quick Add */}
      <div className="stg-card collapse collapse-arrow">
        <input 
          type="checkbox" 
          checked={showExamples}
          onChange={() => setShowExamples(!showExamples)}
        />
        <div className="collapse-title font-medium">
          💡 {t('logger.common_modules_title')}
          <p className="text-xs text-base-content/60 font-normal mt-1">
            {t('logger.common_modules_description')}
          </p>
        </div>
        <div className="collapse-content">
          <NoticeCallout
            variant="warning"
            className="mb-3"
            message={<span dangerouslySetInnerHTML={{ __html: t('logger.debug_warning') }} />}
          />

          <div className="space-y-2">
            {COMMON_MODULES.map(({ module, level, description }) => {
              const isAdded = !!data?.logs?.[module];
              return (
                <div 
                  key={module}
                  className={`stg-inset card ${isAdded ? 'border-success/50' : ''}`}
                >
                  <div className="card-body p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-sm font-semibold truncate">{module}</div>
                        <div className="text-xs text-base-content/60">{description}</div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <div className="badge badge-outline">{level.toUpperCase()}</div>
                        {isAdded ? (
                          <div className="badge badge-success gap-1">
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                            {t('logger.module_added')}
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={() => handleAddCommonModule(module, level)}
                          >
                            <Plus size={14} />
                            {t('logger.module_add')}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Module-specific Log Levels */}
      <div className="">
        <label className="label">
          <span className="label-text font-medium">{t('logger.module_levels')}</span>
        </label>
        
        {/* Existing modules */}
        <div className="space-y-2">
          {Object.entries(data?.logs || {}).map(([module, level]) => (
            <div key={module} className="flex gap-2 items-center">
              <input
                type="text"
                className="input input-bordered flex-1 min-w-0 font-mono text-sm"
                value={module}
                disabled
              />
              <select
                className="select select-bordered w-1/2 shrink-0"
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
                className="btn btn-ghost btn-square btn-sm text-error shrink-0"
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
