/**
 * 1-Wire addresses in the kernel form (`28-000000053f33`) and the ESPHome
 * form (`0xc0000000053f3328`: CRC, serial, family). Mirrors
 * boneio/core/config/onewire_address.py; the backend stores the kernel form.
 * Plain string work: the 64-bit ESPHome number does not fit a JS number.
 */

const KERNEL = /^([0-9a-f]{2})-([0-9a-f]{12})$/;
const ESPHOME = /^0x([0-9a-f]{2})([0-9a-f]{12})([0-9a-f]{2})$/;

/** Maxim CRC-8 over the ROM in wire order: family, serial LSB first. */
function romCrc(family: string, serial: string): number {
  const bytes = [parseInt(family, 16)];
  for (let i = 10; i >= 0; i -= 2) bytes.push(parseInt(serial.slice(i, i + 2), 16));
  let crc = 0;
  for (let byte of bytes) {
    for (let bit = 0; bit < 8; bit++) {
      const mix = (crc ^ byte) & 1;
      crc >>= 1;
      if (mix) crc ^= 0x8c;
      byte >>= 1;
    }
  }
  return crc;
}

/** Kernel form of an address in either form, or null if it is neither. */
export function kernelAddress(value: string): string | null {
  const text = value.trim().toLowerCase();
  if (/^[0-9a-f]{12}$/.test(text)) return `28-${text}`;
  if (KERNEL.test(text)) return text;
  const m = ESPHOME.exec(text);
  if (m && romCrc(m[3], m[2]) === parseInt(m[1], 16)) return `${m[3]}-${m[2]}`;
  return null;
}

/** ESPHome form of an address in either form, or null if it is neither. */
export function esphomeAddress(value: string): string | null {
  const kernel = kernelAddress(value);
  if (!kernel) return null;
  const [family, serial] = kernel.split('-');
  return `0x${romCrc(family, serial).toString(16).padStart(2, '0')}${serial}${family}`;
}
