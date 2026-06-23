const fs = require('fs');
const path = require('path');

const DEVICES_DIR = path.join(__dirname, '../../boneio/modbus/devices');
const OUTPUT_FILE = path.join(__dirname, '../src/generated/modbusDeviceCatalog.ts');

function scanDevices() {
  const catalog = {};
  const categories = fs.readdirSync(DEVICES_DIR, { withFileTypes: true })
    .filter(d => d.isDirectory() && d.name !== '__pycache__')
    .map(d => d.name);

  for (const category of categories) {
    const categoryDir = path.join(DEVICES_DIR, category);
    const files = fs.readdirSync(categoryDir).filter(f => f.endsWith('.json'));
    
    for (const file of files) {
      const modelKey = file.replace('.json', '');
      const filePath = path.join(categoryDir, file);
      let data;
      try {
        data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
      } catch (err) {
        console.error(`⚠️  Failed to parse ${category}/${file}: ${err.message}`);
        continue;
      }
      
      catalog[modelKey] = {
        modelKey,
        displayName: data.model || modelKey,
        manufacturer: data.manufacturer || '',
        description: data.description || '',
        category: data.category || category,
        defaultAddress: data.default_address ?? 1,
        defaultUpdateInterval: data.default_update_interval || '30s',
        hasSetBase: !!data.set_base,
      };
    }
  }
  return catalog;
}

const catalog = scanDevices();
const output = `// Auto-generated — do NOT edit manually.
// Run: node scripts/generate-modbus-catalog.cjs
// Source: boneio/modbus/devices/**/*.json

export interface ModbusDeviceInfo {
  modelKey: string;
  displayName: string;
  manufacturer: string;
  description: string;
  category: string;
  defaultAddress: number;
  defaultUpdateInterval: string;
  hasSetBase: boolean;
}

export const MODBUS_DEVICE_CATALOG: Record<string, ModbusDeviceInfo> = ${JSON.stringify(catalog, null, 2)} as const;

export const MODBUS_CATEGORIES = [...new Set(Object.values(MODBUS_DEVICE_CATALOG).map(d => d.category))].sort();
`;

fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
fs.writeFileSync(OUTPUT_FILE, output);
console.log(`Generated modbus catalog: ${Object.keys(catalog).length} devices`);
