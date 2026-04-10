import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import {
  FaPlay,
  FaStop,
  FaPause,
  FaForward,
  FaTint,
  FaCheckCircle,
  FaTimesCircle,
  FaSync,
  FaClock,
  FaCalendarAlt,
} from 'react-icons/fa';
import { GiValve } from 'react-icons/gi';
import { TabsBox } from '@/components/ui/tabs-box';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ZoneState {
  id: string;
  name: string;
  run_duration: number;
  enabled: boolean;
  run_every_days: number;
  last_run: string | null;
}

interface ScheduleEntry {
  index: number;
  time: string;
  days: string;
  skip: boolean;
}

interface ActiveZone {
  id: string;
  name: string;
  remaining_s: number | null;
}

interface IrrigationController {
  id: string;
  name: string;
  state: 'IDLE' | 'RUNNING' | 'PAUSED';
  active_zone: ActiveZone | null;
  multiplier: number;
  repeat: number;
  auto_advance: boolean;
  reverse: boolean;
  skip_next_run: boolean;
  zones: ZoneState[];
  schedules: ScheduleEntry[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtSeconds(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

function stateColor(state: string) {
  if (state === 'RUNNING') return 'text-success';
  if (state === 'PAUSED') return 'text-warning';
  return 'text-base-content/50';
}

function stateLabel(state: string, t: (k: string) => string) {
  if (state === 'RUNNING') return t('irrigation.state_running');
  if (state === 'PAUSED') return t('irrigation.state_paused');
  return t('irrigation.state_idle');
}

// ─── ZoneRow ──────────────────────────────────────────────────────────────────

function ZoneRow({
  zone,
  ctrlId,
  isActive,
  onCommand,
  onUpdate,
}: {
  zone: ZoneState;
  ctrlId: string;
  isActive: boolean;
  onCommand: (ctrlId: string, zoneId: string, cmd: string) => void;
  onUpdate: (ctrlId: string, zoneId: string, field: string, value: number | boolean) => void;
}) {
  const { t } = useTranslation();
  const [editDuration, setEditDuration] = useState(false);
  const [durationInput, setDurationInput] = useState(String(zone.run_duration));
  const [editEvery, setEditEvery] = useState(false);
  const [everyInput, setEveryInput] = useState(String(zone.run_every_days));

  const saveDuration = () => {
    const val = parseInt(durationInput, 10);
    if (!isNaN(val) && val > 0) onUpdate(ctrlId, zone.id, 'run_duration', val);
    setEditDuration(false);
  };

  const saveEvery = () => {
    const val = parseInt(everyInput, 10);
    if (!isNaN(val) && val > 0) onUpdate(ctrlId, zone.id, 'run_every_days', val);
    setEditEvery(false);
  };

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
        isActive ? 'bg-success/10 border border-success/30' : 'bg-base-200/50'
      }`}
    >
      {/* Enable toggle */}
      <input
        type="checkbox"
        className="checkbox checkbox-sm checkbox-primary"
        checked={zone.enabled}
        onChange={(e) => onCommand(ctrlId, zone.id, e.target.checked ? 'ENABLE' : 'DISABLE')}
        title={zone.enabled ? t('irrigation.zone_disable') : t('irrigation.zone_enable')}
      />

      {/* Zone name */}
      <span className={`flex-1 font-medium truncate ${!zone.enabled ? 'opacity-40' : ''}`}>
        {isActive && <GiValve className="inline mr-1 text-success animate-pulse" />}
        {!isActive && <GiValve className="inline mr-1 text-base-content/30" />}
        {zone.name || zone.id}
      </span>

      {/* Duration */}
      <div className="flex items-center gap-1">
        <FaClock className="text-base-content/40 h-3 w-3" />
        {editDuration ? (
          <input
            autoFocus
            type="number"
            min={1}
            className="input input-xs input-bordered w-16 text-center"
            value={durationInput}
            onChange={(e) => setDurationInput(e.target.value)}
            onBlur={saveDuration}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveDuration();
              if (e.key === 'Escape') setEditDuration(false);
            }}
          />
        ) : (
          <button
            className="btn btn-ghost btn-xs px-1"
            title={t('irrigation.edit_duration')}
            onClick={() => { setDurationInput(String(zone.run_duration)); setEditDuration(true); }}
          >
            {fmtSeconds(zone.run_duration)}
          </button>
        )}
      </div>

      {/* Run every */}
      <div className="flex items-center gap-1">
        <FaCalendarAlt className="text-base-content/40 h-3 w-3" />
        {editEvery ? (
          <input
            autoFocus
            type="number"
            min={1}
            className="input input-xs input-bordered w-12 text-center"
            value={everyInput}
            onChange={(e) => setEveryInput(e.target.value)}
            onBlur={saveEvery}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveEvery();
              if (e.key === 'Escape') setEditEvery(false);
            }}
          />
        ) : (
          <button
            className="btn btn-ghost btn-xs px-1"
            title={t('irrigation.edit_run_every')}
            onClick={() => { setEveryInput(String(zone.run_every_days)); setEditEvery(true); }}
          >
            {t('irrigation.every_n_days').replace('{n}', String(zone.run_every_days))}
          </button>
        )}
      </div>

      {/* Start single zone */}
      <button
        className="btn btn-xs btn-outline btn-success"
        title={t('irrigation.start_zone')}
        onClick={() => onCommand(ctrlId, zone.id, 'ON')}
        disabled={!zone.enabled}
      >
        <FaPlay className="h-3 w-3" />
      </button>
    </div>
  );
}

// ─── ControllerCard ───────────────────────────────────────────────────────────

function ControllerCard({
  ctrl,
  onCommand,
  onZoneCommand,
  onZoneUpdate,
  onSettingUpdate,
  onScheduleSkip,
}: {
  ctrl: IrrigationController;
  onCommand: (ctrlId: string, cmd: string) => void;
  onZoneCommand: (ctrlId: string, zoneId: string, cmd: string) => void;
  onZoneUpdate: (ctrlId: string, zoneId: string, field: string, value: number | boolean) => void;
  onSettingUpdate: (ctrlId: string, field: string, value: number | boolean) => void;
  onScheduleSkip: (ctrlId: string, idx: number, skip: boolean) => void;
}) {
  const { t } = useTranslation();
  const isRunning = ctrl.state === 'RUNNING';
  const isPaused = ctrl.state === 'PAUSED';
  const isActive = isRunning || isPaused;
  const [activeTab, setActiveTab] = useState('zones');

  const zonesContent = (
    <div className="flex flex-col gap-1">
      {ctrl.zones.length === 0 ? (
        <p className="text-xs text-base-content/40 text-center py-2">{t('irrigation.no_zones')}</p>
      ) : (
        ctrl.zones.map((zone) => (
          <ZoneRow
            key={zone.id}
            zone={zone}
            ctrlId={ctrl.id}
            isActive={isRunning && ctrl.active_zone?.id === zone.id}
            onCommand={onZoneCommand}
            onUpdate={onZoneUpdate}
          />
        ))
      )}
    </div>
  );

  const schedulesContent = (
    <div className="flex flex-col gap-1">
      {ctrl.schedules.length === 0 ? (
        <p className="text-xs text-base-content/40 text-center py-2">{t('irrigation.no_schedules')}</p>
      ) : (
        ctrl.schedules.map((sched) => (
          <div
            key={sched.index}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-base-200/50 text-sm"
          >
            <FaClock className="text-base-content/40 h-3 w-3 shrink-0" />
            <span className="font-mono">{sched.time}</span>
            <span className="text-base-content/50">{sched.days}</span>
            <span className="flex-1" />
            <label className="flex items-center gap-1 cursor-pointer select-none text-xs">
              {sched.skip ? (
                <FaTimesCircle className="text-warning h-3.5 w-3.5" />
              ) : (
                <FaCheckCircle className="text-success h-3.5 w-3.5" />
              )}
              <input
                type="checkbox"
                className="checkbox checkbox-xs checkbox-warning"
                checked={sched.skip}
                onChange={(e) => onScheduleSkip(ctrl.id, sched.index, e.target.checked)}
              />
              <span>{t('irrigation.skip_run')}</span>
            </label>
          </div>
        ))
      )}
    </div>
  );

  const settingsContent = (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
      {/* Multiplier */}
      <label className="flex items-center gap-1.5">
        <span className="text-base-content/60">{t('irrigation.multiplier')}:</span>
        <input
          type="number"
          step={0.1}
          min={0.1}
          max={10}
          className="input input-xs input-bordered w-14 text-center"
          value={ctrl.multiplier}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            if (!isNaN(v) && v >= 0.1) onSettingUpdate(ctrl.id, 'multiplier', v);
          }}
        />
        <span className="text-base-content/50">×</span>
      </label>

      {/* Skip next run */}
      <label className="flex items-center gap-1.5 cursor-pointer select-none">
        <input
          type="checkbox"
          className="checkbox checkbox-xs checkbox-warning"
          checked={ctrl.skip_next_run}
          onChange={(e) => onSettingUpdate(ctrl.id, 'skip_next_run', e.target.checked)}
        />
        <span>{t('irrigation.skip_next')}</span>
      </label>

      {/* Auto-advance */}
      <label className="flex items-center gap-1.5 cursor-pointer select-none">
        <input
          type="checkbox"
          className="checkbox checkbox-xs"
          checked={ctrl.auto_advance}
          onChange={(e) => onSettingUpdate(ctrl.id, 'auto_advance', e.target.checked)}
        />
        <span>{t('irrigation.auto_advance')}</span>
      </label>

      {/* Reverse */}
      <label className="flex items-center gap-1.5 cursor-pointer select-none">
        <input
          type="checkbox"
          className="checkbox checkbox-xs"
          checked={ctrl.reverse}
          onChange={(e) => onSettingUpdate(ctrl.id, 'reverse', e.target.checked)}
        />
        <span>{t('irrigation.reverse')}</span>
      </label>
    </div>
  );

  return (
    <div className="card bg-base-100 shadow-sm border border-base-200 w-full">
      <div className="card-body p-4 gap-3">
        {/* Header row */}
        <div className="flex items-center gap-2">
          <FaTint className={`h-5 w-5 shrink-0 ${stateColor(ctrl.state)}`} />
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-base truncate">{ctrl.name}</h3>
            <p className={`text-xs ${stateColor(ctrl.state)}`}>
              {stateLabel(ctrl.state, t)}
              {isRunning && ctrl.active_zone && (
                <span className="ml-1 text-base-content/60">
                  — {ctrl.active_zone.name}
                  {ctrl.active_zone.remaining_s != null && (
                    <span className="ml-1">({fmtSeconds(ctrl.active_zone.remaining_s)})</span>
                  )}
                </span>
              )}
            </p>
          </div>

          {/* Main controls */}
          <div className="flex items-center gap-1">
            {!isActive && (
              <button
                className="btn btn-sm btn-success"
                title={t('irrigation.start')}
                onClick={() => onCommand(ctrl.id, 'ON')}
              >
                <FaPlay className="h-3.5 w-3.5" />
              </button>
            )}
            {isRunning && (
              <button
                className="btn btn-sm btn-warning"
                title={t('irrigation.pause')}
                onClick={() => onCommand(ctrl.id, 'PAUSE')}
              >
                <FaPause className="h-3.5 w-3.5" />
              </button>
            )}
            {isPaused && (
              <button
                className="btn btn-sm btn-info"
                title={t('irrigation.resume')}
                onClick={() => onCommand(ctrl.id, 'RESUME')}
              >
                <FaPlay className="h-3.5 w-3.5" />
              </button>
            )}
            {isRunning && (
              <button
                className="btn btn-sm btn-ghost"
                title={t('irrigation.next_zone')}
                onClick={() => onCommand(ctrl.id, 'NEXT_VALVE')}
              >
                <FaForward className="h-3.5 w-3.5" />
              </button>
            )}
            {isActive && (
              <button
                className="btn btn-sm btn-error"
                title={t('irrigation.stop')}
                onClick={() => onCommand(ctrl.id, 'OFF')}
              >
                <FaStop className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Tabs: Zones / Schedules / Settings */}
        <TabsBox
          name={`irrigation_${ctrl.id}`}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          tabs={[
            {
              id: 'zones',
              label: t('irrigation.zones'),
              badge: ctrl.zones.length,
              content: zonesContent,
            },
            {
              id: 'schedules',
              label: t('irrigation.schedules'),
              badge: ctrl.schedules.length,
              content: schedulesContent,
            },
            {
              id: 'settings',
              label: t('irrigation.settings'),
              content: settingsContent,
            },
          ]}
        />
      </div>
    </div>
  );
}

// ─── IrrigationView ───────────────────────────────────────────────────────────

export default function IrrigationView() {
  const { t } = useTranslation();
  const [data, setData] = useState<IrrigationController[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const resp = await axios.get('/api/irrigation');
      setData(resp.data);
      setError(null);
    } catch (err) {
      console.error('Error fetching irrigation data:', err);
      setError(t('irrigation.fetch_error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const fetchRef = useRef(fetchData);
  fetchRef.current = fetchData;

  const sendCommand = useCallback(async (ctrlId: string, command: string) => {
    try {
      await axios.post(`/api/irrigation/${ctrlId}/command`, { command });
      fetchRef.current();
    } catch (err) {
      console.error('Error sending irrigation command:', err);
    }
  }, []);

  const sendZoneCommand = useCallback(async (ctrlId: string, zoneId: string, command: string) => {
    try {
      await axios.post(`/api/irrigation/${ctrlId}/zone/${zoneId}/command`, { command });
      fetchRef.current();
    } catch (err) {
      console.error('Error sending zone command:', err);
    }
  }, []);

  const updateZone = useCallback(async (ctrlId: string, zoneId: string, field: string, value: number | boolean) => {
    try {
      await axios.post(`/api/irrigation/${ctrlId}/zone/${zoneId}/settings`, { [field]: value });
      fetchRef.current();
    } catch (err) {
      console.error('Error updating zone settings:', err);
    }
  }, []);

  const updateSetting = useCallback(async (ctrlId: string, field: string, value: number | boolean) => {
    try {
      await axios.post(`/api/irrigation/${ctrlId}/settings`, { [field]: value });
      fetchRef.current();
    } catch (err) {
      console.error('Error updating controller settings:', err);
    }
  }, []);

  const toggleScheduleSkip = useCallback(async (ctrlId: string, idx: number, skip: boolean) => {
    try {
      await axios.post(`/api/irrigation/${ctrlId}/schedule/${idx}/skip`, { skip });
      fetchRef.current();
    } catch (err) {
      console.error('Error updating schedule skip:', err);
    }
  }, []);

  if (loading) {
    return (
      <div className="container mx-auto p-4">
        <div className="flex justify-center items-center h-64">
          <span className="loading loading-spinner loading-lg" />
        </div>
      </div>
    );
  }

  if (error && data.length === 0) {
    return (
      <div className="container mx-auto p-4">
        <div className="alert alert-error">
          <FaTimesCircle />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="container mx-auto p-4">
        <div className="flex flex-col items-center justify-center h-48 gap-3 text-base-content/50">
          <FaTint className="h-10 w-10" />
          <p className="text-center">{t('irrigation.no_controllers')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <FaTint className="text-primary" />
          {t('irrigation.title')}
        </h2>
        <button
          className="btn btn-ghost btn-sm"
          title={t('irrigation.refresh')}
          onClick={() => fetchRef.current()}
        >
          <FaSync className="h-4 w-4" />
        </button>
      </div>

      <div className="flex flex-col gap-4 max-w-2xl mx-auto">
        {data.map((ctrl) => (
          <ControllerCard
            key={ctrl.id}
            ctrl={ctrl}
            onCommand={sendCommand}
            onZoneCommand={sendZoneCommand}
            onZoneUpdate={updateZone}
            onSettingUpdate={updateSetting}
            onScheduleSkip={toggleScheduleSkip}
          />
        ))}
      </div>
    </div>
  );
}
