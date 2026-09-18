/**
 * A rough latitude/longitude for common IANA timezones.
 *
 * This exists because the honest ways to get coordinates into an embedded
 * controller are all awkward: `navigator.geolocation` needs a secure context,
 * which a panel served over plain HTTP on a LAN does not have; a map means
 * external tiles, a CSP hole and megabytes of bundle; and typing coordinates
 * from memory is something almost nobody can do.
 *
 * So the timezone the device already knows becomes a starting point. Within one
 * zone the error is minutes of sunrise, not hours — good enough to make the
 * panel show plausible times immediately, and the operator can correct it.
 *
 * Deliberately not exhaustive: a curated list of the zones boneIO is actually
 * installed in, plus one anchor per major region. An unknown zone simply
 * returns nothing and the fields stay empty, which is the correct outcome —
 * a wrong guess would be worse than no guess.
 */
export interface Coordinates {
  latitude: number;
  longitude: number;
}

const TIMEZONE_COORDINATES: Record<string, Coordinates> = {
  // Europe — where most boneIO controllers live, so the densest part.
  'Europe/Warsaw': { latitude: 52.2297, longitude: 21.0122 },
  'Europe/Berlin': { latitude: 52.52, longitude: 13.405 },
  'Europe/Vienna': { latitude: 48.2082, longitude: 16.3738 },
  'Europe/Prague': { latitude: 50.0755, longitude: 14.4378 },
  'Europe/Bratislava': { latitude: 48.1486, longitude: 17.1077 },
  'Europe/Budapest': { latitude: 47.4979, longitude: 19.0402 },
  'Europe/Ljubljana': { latitude: 46.0569, longitude: 14.5058 },
  'Europe/Zagreb': { latitude: 45.815, longitude: 15.9819 },
  'Europe/Belgrade': { latitude: 44.7866, longitude: 20.4489 },
  'Europe/Bucharest': { latitude: 44.4268, longitude: 26.1025 },
  'Europe/Sofia': { latitude: 42.6977, longitude: 23.3219 },
  'Europe/Athens': { latitude: 37.9838, longitude: 23.7275 },
  'Europe/Rome': { latitude: 41.9028, longitude: 12.4964 },
  'Europe/Madrid': { latitude: 40.4168, longitude: -3.7038 },
  'Europe/Lisbon': { latitude: 38.7223, longitude: -9.1393 },
  'Europe/Paris': { latitude: 48.8566, longitude: 2.3522 },
  'Europe/Brussels': { latitude: 50.8503, longitude: 4.3517 },
  'Europe/Amsterdam': { latitude: 52.3676, longitude: 4.9041 },
  'Europe/Luxembourg': { latitude: 49.6116, longitude: 6.1319 },
  'Europe/Zurich': { latitude: 47.3769, longitude: 8.5417 },
  'Europe/London': { latitude: 51.5072, longitude: -0.1276 },
  'Europe/Dublin': { latitude: 53.3498, longitude: -6.2603 },
  'Europe/Copenhagen': { latitude: 55.6761, longitude: 12.5683 },
  'Europe/Oslo': { latitude: 59.9139, longitude: 10.7522 },
  'Europe/Stockholm': { latitude: 59.3293, longitude: 18.0686 },
  'Europe/Helsinki': { latitude: 60.1699, longitude: 24.9384 },
  'Europe/Tallinn': { latitude: 59.437, longitude: 24.7536 },
  'Europe/Riga': { latitude: 56.9496, longitude: 24.1052 },
  'Europe/Vilnius': { latitude: 54.6872, longitude: 25.2797 },
  'Europe/Minsk': { latitude: 53.9006, longitude: 27.559 },
  'Europe/Kyiv': { latitude: 50.4501, longitude: 30.5234 },
  'Europe/Moscow': { latitude: 55.7558, longitude: 37.6173 },
  'Europe/Istanbul': { latitude: 41.0082, longitude: 28.9784 },
  'Europe/Reykjavik': { latitude: 64.1466, longitude: -21.9426 },
  'Europe/Malta': { latitude: 35.8997, longitude: 14.5147 },
  'Atlantic/Reykjavik': { latitude: 64.1466, longitude: -21.9426 },

  // Americas
  'America/New_York': { latitude: 40.7128, longitude: -74.006 },
  'America/Toronto': { latitude: 43.6532, longitude: -79.3832 },
  'America/Chicago': { latitude: 41.8781, longitude: -87.6298 },
  'America/Denver': { latitude: 39.7392, longitude: -104.9903 },
  'America/Phoenix': { latitude: 33.4484, longitude: -112.074 },
  'America/Los_Angeles': { latitude: 34.0522, longitude: -118.2437 },
  'America/Vancouver': { latitude: 49.2827, longitude: -123.1207 },
  'America/Anchorage': { latitude: 61.2181, longitude: -149.9003 },
  'America/Mexico_City': { latitude: 19.4326, longitude: -99.1332 },
  'America/Bogota': { latitude: 4.711, longitude: -74.0721 },
  'America/Lima': { latitude: -12.0464, longitude: -77.0428 },
  'America/Santiago': { latitude: -33.4489, longitude: -70.6693 },
  'America/Sao_Paulo': { latitude: -23.5505, longitude: -46.6333 },
  'America/Argentina/Buenos_Aires': { latitude: -34.6037, longitude: -58.3816 },

  // Asia
  'Asia/Jerusalem': { latitude: 31.7683, longitude: 35.2137 },
  'Asia/Dubai': { latitude: 25.2048, longitude: 55.2708 },
  'Asia/Karachi': { latitude: 24.8607, longitude: 67.0011 },
  'Asia/Kolkata': { latitude: 22.5726, longitude: 88.3639 },
  'Asia/Bangkok': { latitude: 13.7563, longitude: 100.5018 },
  'Asia/Singapore': { latitude: 1.3521, longitude: 103.8198 },
  'Asia/Jakarta': { latitude: -6.2088, longitude: 106.8456 },
  'Asia/Manila': { latitude: 14.5995, longitude: 120.9842 },
  'Asia/Hong_Kong': { latitude: 22.3193, longitude: 114.1694 },
  'Asia/Shanghai': { latitude: 31.2304, longitude: 121.4737 },
  'Asia/Seoul': { latitude: 37.5665, longitude: 126.978 },
  'Asia/Tokyo': { latitude: 35.6762, longitude: 139.6503 },

  // Africa
  'Africa/Cairo': { latitude: 30.0444, longitude: 31.2357 },
  'Africa/Lagos': { latitude: 6.5244, longitude: 3.3792 },
  'Africa/Nairobi': { latitude: -1.2921, longitude: 36.8219 },
  'Africa/Johannesburg': { latitude: -26.2041, longitude: 28.0473 },
  'Africa/Casablanca': { latitude: 33.5731, longitude: -7.5898 },

  // Oceania
  'Australia/Perth': { latitude: -31.9523, longitude: 115.8613 },
  'Australia/Adelaide': { latitude: -34.9285, longitude: 138.6007 },
  'Australia/Brisbane': { latitude: -27.4698, longitude: 153.0251 },
  'Australia/Melbourne': { latitude: -37.8136, longitude: 144.9631 },
  'Australia/Sydney': { latitude: -33.8688, longitude: 151.2093 },
  'Pacific/Auckland': { latitude: -36.8485, longitude: 174.7633 },

  UTC: { latitude: 51.4779, longitude: 0 },
};

/**
 * A plausible starting point for a timezone, or null when it is not listed.
 *
 * @param timezone IANA zone name, e.g. `Europe/Warsaw`.
 */
export function coordinatesForTimezone(timezone: string | undefined): Coordinates | null {
  if (!timezone) return null;
  return TIMEZONE_COORDINATES[timezone] ?? null;
}

export default TIMEZONE_COORDINATES;
