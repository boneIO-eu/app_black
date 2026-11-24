import React, { useEffect, useState } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import HelpLabel from './components/HelpLabel';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import { sanitizeId } from './helpers/idValidation';

/** One bus of the `modbus` section as edited here (other keys pass through untouched). */
interface ModbusBusFormData {
  [key: string]: unknown;
  id?: string;
  port?: string;
  baudrate?: number;
  stopbits?: number;
  bytesize?: number;
  parity?: string;
  timeout?: string | number;
  inter_device_delay?: string | number;
}

/** A port as `GET /api/modbus/ports` lists it. */
interface SerialPort {
  port: string;
  label: string;
  kind: 'builtin' | 'usb';
}

interface ModbusFormProps {
  data: ModbusBusFormData;
  onChange: (data: ModbusBusFormData) => void;
}

/** Select value that reveals the text input for a hand-typed port. */
const OTHER_PORT = '__other__';

/**
 * Form for one Modbus bus: its id, the serial port it uses and the line settings.
 */
const ModbusForm: React.FC<ModbusFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const handleChange = (field: string, value: unknown) => {
    onChange({ ...data, [field]: value });
  };

  const [ports, setPorts] = useState<SerialPort[]>([]);
  const [typingPort, setTypingPort] = useState(false);
  useEffect(() => {
    axios.get('/api/modbus/ports')
      .then((res) => setPorts((res.data as { ports?: SerialPort[] }).ports || []))
      .catch(() => {});
  }, []);

  // The configured port stays selectable while it is not listed (an unplugged adapter).
  const port = data.port || '';
  const portOptions = ports.map((p) => ({ port: p.port, text: p.kind === 'usb' ? `USB: ${p.label}` : p.label }));
  if (port && !ports.some((p) => p.port === port)) {
    portOptions.push({ port, text: `${port} (${t('modbus_config.port_not_found')})` });
  }

  return (
    <div className="stg-cols">
      {/* Bus ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('modbus_config.bus_id')} <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data.id || ''}
          onChange={(e) => handleChange('id', sanitizeId(e.target.value).replace(/-/g, '_'))}
          placeholder="rs485"
          required
        />
        <HelpLabel>{t('modbus_config.bus_id_help')}</HelpLabel>
      </div>

      {/* Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('modbus_config.port')} <span className="text-error">*</span></span>
        </label>
        <select
          className="select select-bordered w-full"
          value={typingPort ? OTHER_PORT : port}
          onChange={(e) => {
            if (e.target.value === OTHER_PORT) {
              setTypingPort(true);
              return;
            }
            setTypingPort(false);
            handleChange('port', e.target.value);
          }}
          required
        >
          <option value="">{t('modbus_config.select_port')}</option>
          {portOptions.map((p) => (
            <option key={p.port} value={p.port}>{p.text}</option>
          ))}
          <option value={OTHER_PORT}>{t('modbus_config.port_other')}</option>
        </select>
        {typingPort && (
          <input
            type="text"
            className="input input-bordered w-full mt-2"
            value={port}
            onChange={(e) => handleChange('port', e.target.value.trim())}
            placeholder="/dev/serial/by-id/..."
          />
        )}
        <HelpLabel>{t('modbus_config.port_help')}</HelpLabel>
      </div>

      {/* Baudrate */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('modbus_config.baudrate')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.baudrate ?? 9600}
          onChange={(e) => handleChange('baudrate', parseInt(e.target.value))}
        >
          <option value={1200}>1200</option>
          <option value={2400}>2400</option>
          <option value={4800}>4800</option>
          <option value={9600}>9600</option>
          <option value={19200}>19200</option>
          <option value={38400}>38400</option>
          <option value={57600}>57600</option>
          <option value={115200}>115200</option>
        </select>
        <HelpLabel>{t('modbus_config.baudrate_help')}</HelpLabel>
      </div>

      {/* Bytesize */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('modbus_config.data_bits')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.bytesize ?? 8}
          onChange={(e) => handleChange('bytesize', parseInt(e.target.value))}
        >
          <option value={7}>7</option>
          <option value={8}>8</option>
        </select>
        <HelpLabel>{t('modbus_config.data_bits_help')}</HelpLabel>
      </div>

      {/* Parity */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('modbus_config.parity')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.parity || 'N'}
          onChange={(e) => handleChange('parity', e.target.value)}
        >
          <option value="N">None (N)</option>
          <option value="E">Even (E)</option>
          <option value="O">Odd (O)</option>
        </select>
        <HelpLabel>{t('modbus_config.parity_help')}</HelpLabel>
      </div>

      {/* Stopbits */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('modbus_config.stop_bits')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.stopbits ?? 1}
          onChange={(e) => handleChange('stopbits', parseInt(e.target.value))}
        >
          <option value={1}>1</option>
          <option value={2}>2</option>
        </select>
        <HelpLabel>{t('modbus_config.stop_bits_help')}</HelpLabel>
      </div>

      {/* Timeout */}
      <SimpleTimePeriodInput
        label={t('modbus_config.timeout')}
        value={data?.timeout ?? '1500ms'}
        onChange={(val) => handleChange('timeout', val)}
        minimum={100}
        maximum={10000}
        allowedUnits={['ms', 's']}
      />
      <HelpLabel>{t('modbus_config.timeout_help')}</HelpLabel>

      {/* Inter-device delay */}
      <SimpleTimePeriodInput
        label={t('modbus_config.inter_device_delay')}
        value={data?.inter_device_delay ?? '5ms'}
        onChange={(val) => handleChange('inter_device_delay', val)}
        minimum={0}
        maximum={200}
        allowedUnits={['ms']}
      />
      <HelpLabel>{t('modbus_config.inter_device_delay_help')}</HelpLabel>
    </div>
  );
};

export default ModbusForm;
