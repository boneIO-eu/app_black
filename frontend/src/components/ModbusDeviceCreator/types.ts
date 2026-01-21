export interface RegisterFilter {
  multiply?: number;
  offset?: number;
}

export interface Register {
  id: string;
  name: string;
  address: number;
  register_type: string;
  unit_of_measurement: string;
  state_class: string;
  device_class: string;
  value_type: string;
  filters: RegisterFilter[];
  tested?: boolean;
  testResult?: string;
  testError?: string;
}

export interface BaudrateConfig {
  address: number;
  possible_baudrates: Record<string, number>;
}

export interface SetBase {
  set_address_address?: number;
  set_baudrate?: BaudrateConfig;
}

export interface OutputRegister {
  name: string;
  address: number;
  unit_of_measurement: string;
  state_class: string;
  device_class?: string;
  value_type: string;
  filters?: RegisterFilter[];
}

export interface OutputRegisterBlock {
  base: number;
  length: number;
  register_type: string;
  registers: OutputRegister[];
}

export interface DeviceConfig {
  model: string;
  set_base?: SetBase;
  registers_base: OutputRegisterBlock[];
}

export const CATEGORIES = [
  { value: 'sensors', label: 'Sensors' },
  { value: 'energy_meters', label: 'Energy Meters' },
  { value: 'hvac', label: 'HVAC' },
  { value: 'inverters', label: 'Inverters' },
  { value: 'other', label: 'Other' },
];

export const VALUE_TYPES = [
  'U_WORD', 'S_WORD', 
  'U_DWORD', 'S_DWORD', 'U_DWORD_R', 'S_DWORD_R',
  'U_QWORD', 'S_QWORD', 'U_QWORD_R',
  'FP32', 'FP32_R'
];

export const DEVICE_CLASSES = [
  '', 'temperature', 'humidity', 'voltage', 'current', 'power', 
  'energy', 'frequency', 'distance', 'pressure', 'speed'
];

export const STATE_CLASSES = ['measurement', 'total', 'total_increasing'];

export const REGISTER_TYPES = ['holding', 'input'];

export const UNITS_OF_MEASUREMENT = [
  '', '°C', '%', 'V', 'A', 'W', 'kW', 'VA', 'kVA', 'var', 'kvar',
  'kWh', 'kvarh', 'Hz', 'mm', 'cm', 'm³/h', 'L', 'min', 'Ohm', '°'
];

export const generateId = () => Math.random().toString(36).substring(2, 9);

export const STORAGE_KEY = 'modbus_device_creator_draft';

/**
 * State that can be saved/loaded from localStorage or JSON file
 */
export interface CreatorState {
  modelName: string;
  fileName: string;
  category: string;
  enableSetAddress: boolean;
  setAddressAddress: number;
  enableSetBaudrate: boolean;
  baudrateAddress: number;
  baudrateMappings: Record<string, number>;
  registers: Register[];
}

/**
 * Parse a device config JSON and convert it to creator state
 */
export const parseDeviceConfig = (config: DeviceConfig): Partial<CreatorState> => {
  const state: Partial<CreatorState> = {
    modelName: config.model,
    registers: [],
  };

  // Parse set_base
  if (config.set_base) {
    if (config.set_base.set_address_address !== undefined) {
      state.enableSetAddress = true;
      state.setAddressAddress = config.set_base.set_address_address;
    }
    if (config.set_base.set_baudrate) {
      state.enableSetBaudrate = true;
      state.baudrateAddress = config.set_base.set_baudrate.address;
      state.baudrateMappings = config.set_base.set_baudrate.possible_baudrates;
    }
  }

  // Parse registers from blocks
  for (const block of config.registers_base) {
    for (const reg of block.registers) {
      state.registers!.push({
        id: generateId(),
        name: reg.name,
        address: reg.address,
        register_type: block.register_type,
        unit_of_measurement: reg.unit_of_measurement,
        state_class: reg.state_class,
        device_class: reg.device_class || '',
        value_type: reg.value_type,
        filters: reg.filters || [],
      });
    }
  }

  return state;
};

export const getRegisterSize = (valueType: string): number => {
  if (['U_DWORD', 'S_DWORD', 'U_DWORD_R', 'S_DWORD_R', 'FP32', 'FP32_R'].includes(valueType)) return 2;
  if (['U_QWORD', 'S_QWORD', 'U_QWORD_R'].includes(valueType)) return 4;
  return 1;
};

/**
 * Maximum gap between registers to be grouped in the same block.
 * If gap is larger, a new block is created.
 */
const MAX_GAP_BETWEEN_REGISTERS = 10;

/**
 * Groups registers into blocks by register_type and proximity.
 * Registers are grouped together only if they are close to each other (within MAX_GAP_BETWEEN_REGISTERS).
 */
export const groupRegistersIntoBlocks = (registers: Register[]): OutputRegisterBlock[] => {
  // Group by register_type first
  const byType: Record<string, Register[]> = {};
  for (const reg of registers) {
    if (!byType[reg.register_type]) {
      byType[reg.register_type] = [];
    }
    byType[reg.register_type].push(reg);
  }
  
  const blocks: OutputRegisterBlock[] = [];
  
  for (const [registerType, regs] of Object.entries(byType)) {
    if (regs.length === 0) continue;
    
    // Sort by address
    const sorted = [...regs].sort((a, b) => a.address - b.address);
    
    // Split into groups based on proximity
    const groups: Register[][] = [];
    let currentGroup: Register[] = [sorted[0]];
    
    for (let i = 1; i < sorted.length; i++) {
      const prevReg = sorted[i - 1];
      const currReg = sorted[i];
      const prevEnd = prevReg.address + getRegisterSize(prevReg.value_type);
      const gap = currReg.address - prevEnd;
      
      if (gap > MAX_GAP_BETWEEN_REGISTERS) {
        // Start a new group
        groups.push(currentGroup);
        currentGroup = [currReg];
      } else {
        // Add to current group
        currentGroup.push(currReg);
      }
    }
    groups.push(currentGroup);
    
    // Create blocks from groups
    for (const group of groups) {
      const base = group[0].address;
      const lastReg = group[group.length - 1];
      const length = lastReg.address - base + getRegisterSize(lastReg.value_type);
      
      blocks.push({
        base,
        length,
        register_type: registerType,
        registers: group.map(reg => {
          const output: OutputRegister = {
            name: reg.name,
            address: reg.address,
            unit_of_measurement: reg.unit_of_measurement,
            state_class: reg.state_class,
            value_type: reg.value_type,
          };
          if (reg.device_class) {
            output.device_class = reg.device_class;
          }
          if (reg.filters.length > 0) {
            output.filters = reg.filters;
          }
          return output;
        }),
      });
    }
  }
  
  return blocks;
};
