import React from 'react';

interface ModbusFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for Modbus section configuration.
 * Fields: uart, baudrate, stopbits, bytesize, parity
 */
const ModbusForm: React.FC<ModbusFormProps> = ({ data, onChange }) => {
  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  // Normalize uart value to lowercase for matching with options
  const uartValue = data?.uart ? String(data.uart).toLowerCase() : '';

  return (
    <div className="space-y-4">
      {/* UART */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">UART <span className="text-error">*</span></span>
        </label>
        <select
          className="select select-bordered w-full"
          value={uartValue}
          onChange={(e) => handleChange('uart', e.target.value)}
          required
        >
          <option value="">-- Select UART --</option>
          <option value="uart1">UART1 (old BoneIO)</option>
          <option value="uart2">UART2</option>
          <option value="uart3">UART3</option>
          <option value="uart4">UART4 (current BoneIO)</option>
          <option value="uart5">UART5</option>
        </select>
        <label className="label">
          <span className="label-text-alt text-base-content/60">UART ID to use. For new boneIO use uart4, for old boneIO use uart1.</span>
        </label>
      </div>

      {/* Baudrate */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Baudrate</span>
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
        <label className="label">
          <span className="label-text-alt text-base-content/60">Communication speed (default: 9600)</span>
        </label>
      </div>

      {/* Bytesize */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Data Bits</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.bytesize ?? 8}
          onChange={(e) => handleChange('bytesize', parseInt(e.target.value))}
        >
          <option value={7}>7</option>
          <option value={8}>8</option>
        </select>
        <label className="label">
          <span className="label-text-alt text-base-content/60">Number of data bits (default: 8)</span>
        </label>
      </div>

      {/* Parity */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Parity</span>
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
        <label className="label">
          <span className="label-text-alt text-base-content/60">Parity checking (default: None)</span>
        </label>
      </div>

      {/* Stopbits */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Stop Bits</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.stopbits ?? 1}
          onChange={(e) => handleChange('stopbits', parseInt(e.target.value))}
        >
          <option value={1}>1</option>
          <option value={2}>2</option>
        </select>
        <label className="label">
          <span className="label-text-alt text-base-content/60">Number of stop bits (default: 1)</span>
        </label>
      </div>
    </div>
  );
};

export default ModbusForm;
