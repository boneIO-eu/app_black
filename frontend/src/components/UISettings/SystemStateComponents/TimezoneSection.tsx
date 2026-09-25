import { useState, useCallback, useEffect, useRef } from 'react';
import {
  FaExclamationTriangle,
  FaSearch,
  FaSync,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import type { AxiosError } from 'axios';
import FixTimezoneSudoers from '../FixTimezoneSudoers';
import NtpServersField from './NtpServersField';
import {
  SettingsPage,
  SettingsCard,
  StatGrid,
  FormField,
  ToggleRow,
  NoticeCallout,
  useSectionSave,
} from '../ui';

type ApiError = AxiosError<{ detail?: string }>;

interface TimezoneInfo {
  timezone: string;
  ntp_synchronized: boolean;
  ntp_enabled: boolean;
  local_time: string;
}

/**
 * Parse a "YYYY-MM-DD HH:MM:SS" string into a Date object,
 * treating it as time in the *device's* timezone (which we don't know offset of).
 * We only need the relative tick — the server sends the snapshot and we tick
 * forward from there using elapsed wall-clock ms.
 */
function parseLocalTime(s: string): Date | null {
  if (!s) return null;
  // Accepts both "2026-04-03 19:40:00" and ISO variants
  const d = new Date(s.replace(' ', 'T'));
  return isNaN(d.getTime()) ? null : d;
}

/**
 * Format a Date back to "YYYY-MM-DD HH:MM:SS".
 */
function formatTime(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

/**
 * Hook that takes a snapshot time string from the API and ticks it
 * forward every second so the display stays live.
 */
function useTickingTime(serverTime: string | undefined) {
  const [display, setDisplay] = useState(serverTime || '');
  const snapshotRef = useRef<{ base: Date; fetchedAt: number } | null>(null);

  // When new server time arrives, reset the snapshot
  useEffect(() => {
    if (!serverTime) return;
    const parsed = parseLocalTime(serverTime);
    if (parsed) {
      snapshotRef.current = { base: parsed, fetchedAt: Date.now() };
      setDisplay(serverTime);
    }
  }, [serverTime]);

  // Tick every second
  useEffect(() => {
    const id = setInterval(() => {
      const snap = snapshotRef.current;
      if (!snap) return;
      const elapsed = Date.now() - snap.fetchedAt;
      const ticked = new Date(snap.base.getTime() + elapsed);
      setDisplay(formatTime(ticked));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  return display;
}

/**
 * Section for configuring system timezone and NTP synchronization.
 * Uses timedatectl on the backend to manage timezone and NTP settings.
 */
export default function TimezoneSection() {
  const { t } = useTranslation();
  const [info, setInfo] = useState<TimezoneInfo | null>(null);
  const [timezones, setTimezones] = useState<string[]>([]);
  const [selectedTimezone, setSelectedTimezone] = useState('');
  const [ntpEnabled, setNtpEnabled] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTogglingNtp, setIsTogglingNtp] = useState(false);
  const [result, setResult] = useState<{ status: string; message: string } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const tickingTime = useTickingTime(info?.local_time);

  const fetchTimezoneInfo = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/timezone');
      setInfo(data);
      setSelectedTimezone(data.timezone || '');
      setNtpEnabled(data.ntp_enabled);
    } catch (err) {
      console.error('Failed to fetch timezone info:', err);
    }
  }, []);

  const fetchTimezones = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/timezones');
      setTimezones(data.timezones || []);
    } catch (err) {
      console.error('Failed to fetch timezones:', err);
    }
  }, []);

  useEffect(() => {
    fetchTimezoneInfo();
  }, [fetchTimezoneInfo]);

  // The list is ~600 entries, which is why it used to wait for the panel to be
  // expanded. The panel does not fold any more — it has its own entry in the
  // settings tree — so it loads on mount, but still only once.
  useEffect(() => {
    if (timezones.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void fetchTimezones();
    }
  }, [timezones.length, fetchTimezones]);

  const changeTimezone = async () => {
    if (!selectedTimezone.trim()) return;
    if (selectedTimezone === info?.timezone) {
      setResult({ status: 'info', message: t('timezone.unchanged') });
      return;
    }

    setIsSaving(true);
    setResult(null);

    try {
      await axios.post('/api/timezone', { timezone: selectedTimezone });
      setResult({ status: 'success', message: t('timezone.changed_success') });
      fetchTimezoneInfo();
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      const detail = apiErr?.response?.data?.detail || apiErr.message;
      setResult({ status: 'error', message: detail || t('timezone.change_failed') });
    } finally {
      setIsSaving(false);
    }
  };

  const toggleNtp = async () => {
    setIsTogglingNtp(true);
    setResult(null);

    try {
      const newState = !ntpEnabled;
      await axios.post('/api/ntp', { enabled: newState });
      setNtpEnabled(newState);
      setResult({
        status: 'success',
        message: newState ? t('timezone.ntp_enabled') : t('timezone.ntp_disabled'),
      });
      // Refresh to see NTP sync status change
      setTimeout(fetchTimezoneInfo, 2000);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      const detail = apiErr?.response?.data?.detail || apiErr.message;
      setResult({ status: 'error', message: detail || t('timezone.ntp_toggle_failed') });
    } finally {
      setIsTogglingNtp(false);
    }
  };

  // Filter timezones by search query
  const filteredTimezones = searchQuery
    ? timezones.filter((tz) => tz.toLowerCase().includes(searchQuery.toLowerCase()))
    : timezones;

  // Group timezones by region for better UX
  const popularTimezones = [
    'Europe/Warsaw',
    'Europe/Berlin',
    'Europe/London',
    'Europe/Paris',
    'Europe/Moscow',
    'America/New_York',
    'America/Chicago',
    'America/Los_Angeles',
    'Asia/Tokyo',
    'Asia/Shanghai',
    'Australia/Sydney',
    'UTC',
  ];

  // What the second group actually lists, and therefore what the count below
  // it should say.
  const listedTimezones = searchQuery
    ? filteredTimezones
    : filteredTimezones.filter((tz) => !popularTimezones.includes(tz));

  useSectionSave(
    {
      dirty: selectedTimezone.trim() !== '' && selectedTimezone !== info?.timezone,
      saving: isSaving,
      label: t('timezone.save_timezone'),
    },
    () => void changeTimezone(),
  );

  return (
    <SettingsPage>
      {/* Sudoers check — its own card, because it is a precondition for the
          controls below rather than one of them. */}
      <FixTimezoneSudoers />

      {/* No footer: the save is registered with the shell and drawn in the
          action bar at the bottom of the pane, like every other section. */}
      <SettingsCard>
        <div className="space-y-4">
          {/* Current status */}
          <StatGrid
            columns={3}
            items={[
              {
                label: t('timezone.current_timezone'),
                value: info?.timezone || '…',
                mono: true,
              },
              {
                label: t('timezone.local_time'),
                value: tickingTime || '…',
                mono: true,
              },
              {
                label: t('timezone.ntp_status'),
                value: info?.ntp_synchronized ? (
                  <span className="badge badge-success badge-sm gap-1.5">
                    <FaSync className="w-2.5 h-2.5" />
                    {t('timezone.synchronized')}
                  </span>
                ) : (
                  <span className="badge badge-warning badge-sm gap-1.5">
                    <FaExclamationTriangle className="w-2.5 h-2.5" />
                    {t('timezone.not_synchronized')}
                  </span>
                ),
              },
            ]}
          />

          {/* Timezone selection */}
          <FormField label={t('timezone.select_timezone')} className="max-w-xl">
            <div className="space-y-2">
              <label className="input input-bordered flex items-center gap-2 w-full">
                <FaSearch className="w-3.5 h-3.5 text-base-content/40 shrink-0" />
                <input
                  type="text"
                  className="grow min-w-0 bg-transparent outline-hidden"
                  placeholder={t('timezone.search_placeholder')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </label>
              <select
                className="select select-bordered w-full font-mono"
                value={selectedTimezone}
                onChange={(e) => setSelectedTimezone(e.target.value)}
              >
                {/* Popular timezones group */}
                {!searchQuery && (
                  <optgroup label={t('timezone.popular')}>
                    {popularTimezones
                      .filter((tz) => timezones.includes(tz))
                      .map((tz) => (
                        <option key={`popular-${tz}`} value={tz}>
                          {tz} {tz === info?.timezone ? '\u2713' : ''}
                        </option>
                      ))}
                  </optgroup>
                )}
                <optgroup label={searchQuery ? t('timezone.search_results') : t('timezone.all_timezones')}>
                  {listedTimezones.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz} {tz === info?.timezone ? '\u2713' : ''}
                    </option>
                  ))}
                </optgroup>
              </select>
              <p className="text-xs opacity-60">
                {timezones.length} {t('timezone.timezones_available')}
              </p>
            </div>
          </FormField>

          {/* NTP */}
          <ToggleRow
            checked={ntpEnabled}
            onChange={toggleNtp}
            busy={isTogglingNtp}
            icon={<FaSync className="w-3.5 h-3.5" />}
            label={t('timezone.ntp_sync')}
            description={t('timezone.ntp_hint')}
          />

          {/* Which servers that synchronisation uses. Separate from the toggle
              because it stays meaningful while synchronisation is off: the
              choice is remembered and applied when it is switched back on. */}
          <NtpServersField onChanged={fetchTimezoneInfo} />

          {/* Result */}
          {result && (
            <NoticeCallout
              variant={
                result.status === 'success'
                  ? 'success'
                  : result.status === 'info'
                    ? 'info'
                    : 'error'
              }
              message={result.message}
            />
          )}
        </div>
      </SettingsCard>
    </SettingsPage>
  );
}
