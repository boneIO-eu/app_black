import { useTranslation } from '@/hooks/useTranslation';
import { FaTrash, FaPlay, FaCheck, FaPlus, FaTimes } from 'react-icons/fa';
import { NumericInput } from '@/components/ui/NumericInput';
import { Register, REGISTER_TYPES, UNITS_OF_MEASUREMENT, VALUE_TYPES, DEVICE_CLASSES, STATE_CLASSES } from './types';

interface RegisterItemProps {
  register: Register;
  testing: string | null;
  onUpdate: (updates: Partial<Register>) => void;
  onRemove: () => void;
  onTest: () => void;
}

export default function RegisterItem({
  register,
  testing,
  onUpdate,
  onRemove,
  onTest,
}: RegisterItemProps) {
  const { t } = useTranslation();

  const removeFilter = (filterIndex: number) => {
    const newFilters = register.filters.filter((_, i) => i !== filterIndex);
    onUpdate({ filters: newFilters });
  };

  return (
    <div className="card bg-base-300">
      <div className="card-body p-4">
        {/* Main fields - 2 rows on mobile, responsive on larger screens */}
        <div className="flex flex-col gap-3">
          {/* Row 1: Name, Address, Register Type */}
          <div className="grid grid-cols-3 gap-2">
            <div className="form-control">
              <label className="label py-0">
                <span className="label-text text-xs">{t('modbus_creator.name')}</span>
              </label>
              <input
                type="text"
                className={`input input-bordered input-sm w-full ${!register.name ? 'input-error' : ''}`}
                value={register.name}
                onChange={(e) => onUpdate({ name: e.target.value })}
                placeholder="Temperature"
              />
            </div>
            
            <div className="form-control">
              <label className="label py-0">
                <span className="label-text text-xs">{t('modbus_creator.address')}</span>
              </label>
              <NumericInput
                className="input-sm"
                value={register.address}
                onChange={(v) => onUpdate({ address: v === '' ? 0 : v })}
              />
            </div>
            
            <div className="form-control">
              <label className="label py-0">
                <span className="label-text text-xs">{t('modbus_creator.register_type')}</span>
              </label>
              <select
                className="select select-bordered select-sm w-full"
                value={register.register_type}
                onChange={(e) => onUpdate({ register_type: e.target.value })}
              >
                {REGISTER_TYPES.map(type => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>
          </div>
          
          {/* Row 2: Unit, Value Type, Device Class, State Class + Actions */}
          <div className="flex gap-2 items-end">
            <div className="grid grid-cols-4 gap-2 flex-1">
              <div className="form-control">
                <label className="label py-0">
                  <span className="label-text text-xs">{t('modbus_creator.unit')}</span>
                </label>
                <select
                  className={`select select-bordered select-sm w-full ${!register.unit_of_measurement ? 'select-error' : ''}`}
                  value={UNITS_OF_MEASUREMENT.includes(register.unit_of_measurement) ? register.unit_of_measurement : '__custom__'}
                  onChange={(e) => {
                    if (e.target.value === '__custom__') {
                      const custom = prompt(t('modbus_creator.enter_custom_unit'));
                      if (custom !== null) {
                        onUpdate({ unit_of_measurement: custom });
                      }
                    } else {
                      onUpdate({ unit_of_measurement: e.target.value });
                    }
                  }}
                >
                  <option value="" disabled>{t('modbus_creator.select_unit')}</option>
                  {UNITS_OF_MEASUREMENT.filter(u => u !== '').map(unit => (
                    <option key={unit} value={unit}>{unit}</option>
                  ))}
                  <option value="__custom__">{register.unit_of_measurement && !UNITS_OF_MEASUREMENT.includes(register.unit_of_measurement) ? register.unit_of_measurement : t('modbus_creator.custom_unit')}</option>
                </select>
              </div>
              
              <div className="form-control">
                <label className="label py-0">
                  <span className="label-text text-xs">{t('modbus_creator.value_type')}</span>
                </label>
                <select
                  className="select select-bordered select-sm w-full"
                  value={register.value_type}
                  onChange={(e) => onUpdate({ value_type: e.target.value })}
                >
                  {VALUE_TYPES.map(type => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>
              
              <div className="form-control">
                <label className="label py-0">
                  <span className="label-text text-xs">{t('modbus_creator.device_class')}</span>
                </label>
                <select
                  className="select select-bordered select-sm w-full"
                  value={register.device_class}
                  onChange={(e) => onUpdate({ device_class: e.target.value })}
                >
                  {DEVICE_CLASSES.map(dc => (
                    <option key={dc} value={dc}>{dc || '(none)'}</option>
                  ))}
                </select>
              </div>
              
              <div className="form-control">
                <label className="label py-0">
                  <span className="label-text text-xs">{t('modbus_creator.state_class')}</span>
                </label>
                <select
                  className="select select-bordered select-sm w-full"
                  value={register.state_class}
                  onChange={(e) => onUpdate({ state_class: e.target.value })}
                >
                  {STATE_CLASSES.map(sc => (
                    <option key={sc} value={sc}>{sc}</option>
                  ))}
                </select>
              </div>
            </div>
            
            {/* Action buttons */}
            <div className="flex gap-1">
              <button
                className={`btn btn-sm ${register.tested ? 'btn-success' : 'btn-ghost'}`}
                onClick={onTest}
                disabled={testing === register.id}
                title={t('modbus_creator.test_register')}
              >
                {testing === register.id ? (
                  <span className="loading loading-spinner loading-xs"></span>
                ) : register.tested ? (
                  <FaCheck />
                ) : (
                  <FaPlay />
                )}
              </button>
              <button
                className="btn btn-ghost btn-sm text-error"
                onClick={onRemove}
                title={t('modbus_creator.remove_register')}
              >
                <FaTrash />
              </button>
            </div>
          </div>
        </div>
        
        {/* Test Result */}
        {(register.testResult || register.testError) && (
          <div className={`text-xs mt-2 ${register.testError ? 'text-error' : 'text-success'}`}>
            {register.testResult || register.testError}
          </div>
        )}
        
        {/* Filters */}
        <div className="mt-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium">{t('modbus_creator.filters')}:</span>
            {register.filters.map((filter, filterIndex) => (
              <div key={filterIndex} className="badge badge-outline gap-1">
                {filter.multiply !== undefined && `×${filter.multiply}`}
                {filter.offset !== undefined && `+${filter.offset}`}
                <button
                  className="btn btn-ghost btn-xs p-0"
                  onClick={() => removeFilter(filterIndex)}
                >
                  <FaTimes size={8} />
                </button>
              </div>
            ))}
            <div className="dropdown dropdown-end">
              <label tabIndex={0} className="btn btn-ghost btn-xs">
                <FaPlus size={10} />
              </label>
              <ul tabIndex={0} className="dropdown-content z-10 menu p-2 shadow bg-base-100 rounded-box w-40">
                <li>
                  <button onClick={() => {
                    const val = prompt('Multiply by:');
                    if (val) {
                      onUpdate({
                        filters: [...register.filters, { multiply: parseFloat(val) }]
                      });
                    }
                  }}>
                    Multiply
                  </button>
                </li>
                <li>
                  <button onClick={() => {
                    const val = prompt('Offset:');
                    if (val) {
                      onUpdate({
                        filters: [...register.filters, { offset: parseFloat(val) }]
                      });
                    }
                  }}>
                    Offset
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
