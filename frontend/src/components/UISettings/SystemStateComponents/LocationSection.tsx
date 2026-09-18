import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import { FaGlobeEurope } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import {
  SettingsPage,
  SettingsCard,
  StatGrid,
  FormField,
  NoticeCallout,
  useSectionSave,
} from '../ui';
import { coordinatesForTimezone } from './timezoneCoordinates';

const TilePicker = lazy(() => import('./TilePicker'));

/** Response of `GET /api/sun/today`. */
interface SunToday {
  configured: boolean;
  ready: boolean;
  reason?: 'no_location' | 'clock_not_set';
  latitude?: number;
  longitude?: number;
  elevation?: number;
  timezone?: string;
  date?: string;
  anchors: Record<string, string | null>;
  now?: {
    elevation: number | null;
    azimuth: number | null;
    phase: string | null;
    golden_hour: boolean | null;
    blue_hour: boolean | null;
  };
  horizon_state?: 'crosses' | 'always_above' | 'always_below';
  /** web.security.map_tiles — whether the CSP lets tile images load at all. */
  map_tiles?: boolean;
}

/**
 * The anchors worth showing, in the order they happen.
 *
 * All eighteen exist in the API — four of them name the same two instants as
 * their neighbours — so printing every one would be a list where half the rows
 * repeat the row above. These are the distinct moments of a day.
 */
const SHOWN_ANCHORS = [
  'astronomical_dawn',
  'nautical_dawn',
  'civil_dawn',
  'golden_hour_morning_start',
  'sunrise',
  'golden_hour_morning_end',
  'solar_noon',
  'golden_hour_evening_start',
  'sunset',
  'golden_hour_evening_end',
  'civil_dusk',
  'nautical_dusk',
  'astronomical_dusk',
] as const;

/** Render an ISO timestamp as local HH:MM, or an em dash when it never happens. */
function clock(iso: string | null | undefined): string {
  if (!iso) return '—';
  const parsed = new Date(iso);
  if (isNaN(parsed.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

/** Pull the backend's `detail` out of an axios error, falling back to its message. */
function errorDetail(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const response = (err as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    const message = (err as { message?: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return '';
}

/** Round to four decimals (~11 m); more is noise and it lands in config backups. */
function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

/**
 * Where the controller stands.
 *
 * Only sun-based features need this, and they need it exactly: an hour's error
 * in sunset is an hour of lights. So the page does not just take three numbers
 * — it shows today's times back, which is the only practical way for someone to
 * notice they typed the longitude into the latitude field.
 */
export default function LocationSection() {
  const { t } = useTranslation();
  const [sun, setSun] = useState<SunToday | null>(null);
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [elevation, setElevation] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [result, setResult] = useState<{ status: string; message: string } | null>(null);

  const fetchSun = useCallback(async () => {
    try {
      const { data } = await axios.get<SunToday>('/api/sun/today');
      setSun(data);
      if (data.configured) {
        setLatitude(String(data.latitude ?? ''));
        setLongitude(String(data.longitude ?? ''));
        setElevation(String(data.elevation ?? 0));
      }
    } catch (err) {
      console.error('Failed to fetch sun info:', err);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchSun();
  }, [fetchSun]);

  const parsed = useMemo(() => {
    const lat = parseFloat(latitude.replace(',', '.'));
    const lon = parseFloat(longitude.replace(',', '.'));
    const alt = elevation.trim() === '' ? 0 : parseFloat(elevation.replace(',', '.'));
    return { lat, lon, alt };
  }, [latitude, longitude, elevation]);

  /**
   * What the device currently has, in the same shape the inputs hold it.
   *
   * `fetchSun` fills the fields with `String(...)` of these very numbers, so
   * comparing the strings is exact: right after a load or a save nothing is
   * dirty, and one keystroke makes it so.
   */
  const saved = useMemo(
    () =>
      sun?.configured
        ? {
            lat: String(sun.latitude ?? ''),
            lon: String(sun.longitude ?? ''),
            alt: String(sun.elevation ?? 0),
          }
        : { lat: '', lon: '', alt: '' },
    [sun],
  );
  const dirty = latitude !== saved.lat || longitude !== saved.lon || elevation !== saved.alt;

  const latError = latitude.trim() !== '' && (isNaN(parsed.lat) || Math.abs(parsed.lat) > 90);
  const lonError = longitude.trim() !== '' && (isNaN(parsed.lon) || Math.abs(parsed.lon) > 180);
  const altError = elevation.trim() !== '' && (isNaN(parsed.alt) || parsed.alt < -500 || parsed.alt > 9000);
  const complete = latitude.trim() !== '' && longitude.trim() !== '';
  const canSave = complete && !latError && !lonError && !altError && !isSaving;

  // No "use my browser's location" button on purpose. It would need two things
  // this panel does not have: a secure context, which a panel served over plain
  // HTTP on a LAN is not, and the `geolocation` feature, which
  // webui/security_headers.py denies outright in Permissions-Policy. A button
  // that silently never calls back is worse than no button, and relaxing a
  // header that was tightened during the pentest remediation is not worth a
  // convenience. Filling from the timezone covers the same need offline.

  const fillFromTimezone = () => {
    const guess = coordinatesForTimezone(sun?.timezone);
    if (!guess) {
      setResult({ status: 'error', message: t('location.timezone_unknown') });
      return;
    }
    setLatitude(String(guess.latitude));
    setLongitude(String(guess.longitude));
    setResult({ status: 'info', message: t('location.timezone_filled') });
  };

  const save = async () => {
    setIsSaving(true);
    setResult(null);
    try {
      await axios.put('/api/config/location', {
        latitude: round4(parsed.lat),
        longitude: round4(parsed.lon),
        elevation: isNaN(parsed.alt) ? 0 : Math.round(parsed.alt),
      });
      // `location` hot-reloads: the provider drops its cached day and picks the
      // new coordinates up without a restart.
      await axios.post('/api/config/reload', ['location'], { timeout: 30000 });
      setResult({ status: 'success', message: t('location.saved') });
      await fetchSun();
    } catch (err: unknown) {
      setResult({ status: 'error', message: errorDetail(err) || t('location.save_failed') });
    } finally {
      setIsSaving(false);
    }
  };

  useSectionSave(
    {
      dirty,
      saving: isSaving,
      disabled: !canSave,
      label: t('location.save'),
    },
    () => void save(),
  );

  const phase = sun?.now?.phase;
  const polar =
    sun?.horizon_state === 'always_above'
      ? t('location.polar_day')
      : sun?.horizon_state === 'always_below'
        ? t('location.polar_night')
        : null;

  return (
    <SettingsPage>
      {/* No footer: the save is registered with the shell and drawn in the
          action bar at the bottom of the pane, where every other settings
          section is committed from. */}
      <SettingsCard>
        <div className="space-y-4">
          <StatGrid
            columns={3}
            items={[
              {
                label: t('location.sun_phase'),
                value: phase ? t(`sun.phase_${phase}`) : '—',
              },
              {
                label: t('sun.anchor_sunrise'),
                value: polar ?? clock(sun?.anchors?.sunrise),
                mono: !polar,
              },
              {
                label: t('sun.anchor_sunset'),
                value: polar ?? clock(sun?.anchors?.sunset),
                mono: !polar,
              },
            ]}
          />

          {sun && !sun.configured && (
            <NoticeCallout variant="warning" message={t('location.not_configured')} />
          )}
          {sun?.configured && sun.reason === 'clock_not_set' && (
            <NoticeCallout variant="warning" message={t('location.clock_not_set')} />
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-xl">
            <FormField label={t('location.latitude')} error={latError ? t('location.latitude_range') : undefined}>
              <input
                type="text"
                inputMode="decimal"
                className={`input input-bordered input-sm w-full font-mono ${latError ? 'input-error' : ''}`}
                placeholder="52.2297"
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
                spellCheck={false}
              />
            </FormField>
            <FormField label={t('location.longitude')} error={lonError ? t('location.longitude_range') : undefined}>
              <input
                type="text"
                inputMode="decimal"
                className={`input input-bordered input-sm w-full font-mono ${lonError ? 'input-error' : ''}`}
                placeholder="21.0122"
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
                spellCheck={false}
              />
            </FormField>
            <FormField label={t('location.elevation')} error={altError ? t('location.elevation_range') : undefined}>
              <input
                type="text"
                inputMode="numeric"
                className={`input input-bordered input-sm w-full font-mono ${altError ? 'input-error' : ''}`}
                placeholder="0"
                value={elevation}
                onChange={(e) => setElevation(e.target.value)}
                spellCheck={false}
              />
            </FormField>
          </div>

          {sun?.map_tiles ? (
            <Suspense
              fallback={
                <div className="h-[300px] rounded-lg bg-base-200 animate-pulse max-w-xl" />
              }
            >
              <div className="max-w-xl">
                <TilePicker
                  latitude={latError || latitude.trim() === '' ? null : parsed.lat}
                  longitude={lonError || longitude.trim() === '' ? null : parsed.lon}
                  onPick={(lat, lon) => {
                    setLatitude(String(round4(lat)));
                    setLongitude(String(round4(lon)));
                  }}
                />
              </div>
            </Suspense>
          ) : (
            <p className="text-xs opacity-60 max-w-xl">{t('location.map_disabled')}</p>
          )}

          <div className="flex flex-wrap gap-2">
            <button className="btn btn-ghost btn-sm gap-2" onClick={fillFromTimezone}>
              <FaGlobeEurope />
              {t('location.fill_from_timezone')}
            </button>
          </div>

          <p className="text-xs opacity-60 max-w-xl">
            {t('location.hint')}
            {sun?.timezone ? ` ${t('location.timezone')}: ${sun.timezone}.` : ''}
          </p>

          {result && (
            <NoticeCallout
              variant={
                result.status === 'success' ? 'success' : result.status === 'info' ? 'info' : 'error'
              }
              message={result.message}
            />
          )}
        </div>
      </SettingsCard>

      {sun?.ready && (
        <SettingsCard>
          <div className="space-y-2">
            <p className="text-sm font-medium">
              {t('location.today_times')}
              {sun.date ? ` — ${sun.date}` : ''}
            </p>
            <p className="text-xs opacity-60">{t('location.today_times_hint')}</p>
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <tbody>
                  {SHOWN_ANCHORS.map((name) => (
                    <tr key={name}>
                      <td className="whitespace-nowrap">{t(`sun.anchor_${name}`)}</td>
                      <td className="font-mono text-right whitespace-nowrap">
                        {clock(sun.anchors?.[name])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sun.now?.elevation != null && (
              <p className="text-xs opacity-60">
                {t('location.current_position')}:{' '}
                <span className="font-mono">
                  {sun.now.elevation.toFixed(1)}° / {sun.now.azimuth?.toFixed(1)}°
                </span>
              </p>
            )}
          </div>
        </SettingsCard>
      )}
    </SettingsPage>
  );
}
