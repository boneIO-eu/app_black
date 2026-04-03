import { useState, useCallback, useEffect, useRef } from 'react';
import {
  FaCheck,
  FaClock,
  FaExclamationTriangle,
  FaSpinner,
  FaSync,
} from 'react-icons/fa';
import SettingsCard from '../components/SettingsCard';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import FixTimezoneSudoers from '../FixTimezoneSudoers';

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
  const [isExpanded, setIsExpanded] = useState(false);
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

  // Load timezone list only when section is expanded
  useEffect(() => {
    if (isExpanded && timezones.length === 0) {
      fetchTimezones();
    }
  }, [isExpanded, timezones.length, fetchTimezones]);

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
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err.message;
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
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err.message;
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

  return (
    <SettingsCard
      icon={<FaClock />}
      title={t('timezone.title')}
      description={
        info
          ? `${info.timezone} — ${tickingTime}`
          : t('timezone.description')
      }
      toggleButtonText={t('timezone.show_section')}
      toggleButtonTextExpanded={t('common.close')}
      isExpanded={isExpanded}
      onToggle={() => setIsExpanded(!isExpanded)}
      expandableContent={
        <div className="space-y-4">
          {/* Sudoers Check */}
          <FixTimezoneSudoers />

          {/* Current Status */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="flex flex-col gap-1">
              <span className="text-xs opacity-70">{t('timezone.current_timezone')}</span>
              <span className="font-mono font-bold">{info?.timezone || '...'}</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs opacity-70">{t('timezone.local_time')}</span>
              <span className="font-mono">{tickingTime || '...'}</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs opacity-70">{t('timezone.ntp_status')}</span>
              <div>
                {info?.ntp_synchronized ? (
                  <span className="badge badge-success badge-sm gap-1">
                    <FaSync className="w-2.5 h-2.5" />
                    {t('timezone.synchronized')}
                  </span>
                ) : (
                  <span className="badge badge-warning badge-sm gap-1">
                    <FaExclamationTriangle className="w-2.5 h-2.5" />
                    {t('timezone.not_synchronized')}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="divider my-1"></div>

          {/* Timezone Selection */}
          <div>
            <label className="label">
              <span className="label-text font-medium">{t('timezone.select_timezone')}</span>
            </label>
            {/* Search filter */}
            <input
              type="text"
              className="input input-bordered input-sm w-full mb-2"
              placeholder={t('timezone.search_placeholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <select
              className="select select-bordered w-full"
              value={selectedTimezone}
              onChange={(e) => setSelectedTimezone(e.target.value)}
              size={8}
            >
              {/* Popular timezones group */}
              {!searchQuery && (
                <optgroup label={t('timezone.popular')}>
                  {popularTimezones
                    .filter((tz) => timezones.includes(tz))
                    .map((tz) => (
                      <option key={`popular-${tz}`} value={tz}>
                        {tz} {tz === info?.timezone ? '✓' : ''}
                      </option>
                    ))}
                </optgroup>
              )}
              {/* All / filtered timezones */}
              <optgroup label={searchQuery ? t('timezone.search_results') : t('timezone.all_timezones')}>
                {filteredTimezones.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz} {tz === info?.timezone ? '✓' : ''}
                  </option>
                ))}
              </optgroup>
            </select>
            <label className="label">
              <span className="label-text-alt">
                {filteredTimezones.length} {t('timezone.timezones_available')}
              </span>
            </label>
          </div>

          {/* NTP Toggle */}
          <div>
            <label className="label cursor-pointer justify-start gap-4">
              <input
                type="checkbox"
                className="toggle toggle-primary"
                checked={ntpEnabled}
                onChange={toggleNtp}
                disabled={isTogglingNtp}
              />
              <div>
                <span className="label-text font-medium">{t('timezone.ntp_sync')}</span>
                <p className="text-xs opacity-60">{t('timezone.ntp_hint')}</p>
              </div>
              {isTogglingNtp && <FaSpinner className="animate-spin ml-2" />}
            </label>
          </div>

          {/* Result */}
          {result && (
            <div className={`alert ${result.status === 'success' ? 'alert-success' : result.status === 'info' ? 'alert-info' : 'alert-error'}`}>
              {result.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
              <span>{result.message}</span>
            </div>
          )}

          {/* Save Button */}
          <button
            className="btn btn-primary"
            onClick={changeTimezone}
            disabled={isSaving || !selectedTimezone.trim() || selectedTimezone === info?.timezone}
          >
            {isSaving ? (
              <>
                <FaSpinner className="animate-spin" />
                {t('timezone.saving')}
              </>
            ) : (
              <>
                <FaCheck />
                {t('timezone.save_timezone')}
              </>
            )}
          </button>
        </div>
      }
    />
  );
}
