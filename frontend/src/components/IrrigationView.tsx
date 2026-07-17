import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
  FaCog,
} from 'react-icons/fa';
import { GiValve } from 'react-icons/gi';
import { TabsBox } from '@/components/ui/tabs-box';
import { LongPressWrapper } from '@/components/ui/LongPressWrapper';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

import type { ZoneState, IrrigationController } from '@/types/irrigation';

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
  const [everyInput, setEveryInput] = useState(String(zone.run_every_n));

  const saveDuration = () => {
    const val = parseInt(durationInput, 10);
    if (!isNaN(val) && val > 0) onUpdate(ctrlId, zone.id, 'run_duration', val);
    setEditDuration(false);
  };

  const saveEvery = () => {
    const val = parseInt(everyInput, 10);
    if (!isNaN(val) && val > 0) onUpdate(ctrlId, zone.id, 'run_every_n', val);
    setEditEvery(false);
  };

  return (
    <div
      className={`rounded-lg text-sm transition-colors ${isActive ? 'bg-success/10 border border-success/30' : 'bg-base-200/50'
        }`}
    >
      {/* Top row: checkbox + name + action button */}
      <div className="flex items-center gap-2 px-3 pt-2 pb-1">
        <input
          type="checkbox"
          className="checkbox checkbox-sm checkbox-primary shrink-0"
          checked={zone.enabled}
          onChange={(e) => onCommand(ctrlId, zone.id, e.target.checked ? 'ENABLE' : 'DISABLE')}
          title={zone.enabled ? t('irrigation.zone_disable') : t('irrigation.zone_enable')}
        />
        <span className={`flex-1 font-medium truncate min-w-0 ${!zone.enabled ? 'opacity-40' : ''}`}>
          {isActive && <GiValve className="inline mr-1 text-success animate-pulse" />}
          {!isActive && <GiValve className="inline mr-1 text-base-content/30" />}
          {zone.name || zone.id}
        </span>
        {isActive ? (
          <button
            className="btn btn-xs btn-outline btn-warning shrink-0"
            title={t('irrigation.skip_zone')}
            onClick={() => onCommand(ctrlId, zone.id, 'NEXT_VALVE')}
          >
            <FaForward className="h-3 w-3" />
          </button>
        ) : (
          <button
            className="btn btn-xs btn-outline btn-success shrink-0"
            title={t('irrigation.start_zone')}
            onClick={() => onCommand(ctrlId, zone.id, 'ON')}
            disabled={!zone.enabled}
          >
            <FaPlay className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Bottom row: duration + run every (compact stats) */}
      <div className="flex items-center gap-3 px-3 pb-2 pl-10 text-xs text-base-content/60">
        {/* Duration */}
        <div className="flex items-center gap-1">
          <FaClock className="h-2.5 w-2.5" />
          {editDuration ? (
            <input
              autoFocus
              type="number"
              min={1}
              step={1}
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
              className="btn btn-ghost btn-xs px-1 text-xs"
              title={t('irrigation.edit_duration')}
              onClick={() => { setDurationInput(String(zone.run_duration)); setEditDuration(true); }}
            >
              {zone.run_duration} min
            </button>
          )}
        </div>

        {/* Run every */}
        <div className="flex items-center gap-1">
          <FaCalendarAlt className="h-2.5 w-2.5" />
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
              className="btn btn-ghost btn-xs px-1 text-xs"
              title={t('irrigation.edit_run_every')}
              onClick={() => { setEveryInput(String(zone.run_every_n)); setEditEvery(true); }}
            >
              {t('irrigation.every_n_runs').replace('{n}', String(zone.run_every_n))}
            </button>
          )}
        </div>
      </div>
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
  onSettingUpdate: (ctrlId: string, field: string, value: number | boolean | string) => void;
  onScheduleSkip: (ctrlId: string, idx: number, skip: boolean) => void;
}) {
  const { t } = useTranslation();
  const isRunning = ctrl.state === 'RUNNING';
  const isPaused = ctrl.state === 'PAUSED';
  const isActive = isRunning || isPaused;
  const [activeTab, setActiveTab] = useState('zones');

  // ── Live countdown ──────────────────────────────────────────────────────
  const [countdown, setCountdown] = useState<number | null>(null);

  // Track when we received the data to calculate local countdown
  const dataReceivedAt = useRef<number>(Date.now());

  // Update the received timestamp when active zone data changes
  useEffect(() => {
    dataReceivedAt.current = Date.now();
  }, [ctrl.active_zone?.remaining_s, ctrl.active_zone?.id]);

  useEffect(() => {
    const serverRemaining = ctrl.active_zone?.remaining_s;
    if (serverRemaining == null || serverRemaining <= 0 || !isActive) {
      setCountdown(serverRemaining ?? null);
      return;
    }
    // Use server's remaining_s as base and count down locally from the moment we received it
    // This avoids clock skew between device and browser
    const receivedAt = dataReceivedAt.current;
    const tick = () => {
      const elapsed = (Date.now() - receivedAt) / 1000;
      const remaining = Math.max(0, Math.round(serverRemaining - elapsed));
      setCountdown(remaining);
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [ctrl.active_zone?.remaining_s, ctrl.active_zone?.id, isActive]);

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
    <div className="space-y-4">
      {/* ── Cycle Settings ── */}
      <fieldset className="border border-base-300 rounded-lg px-3 pb-3 pt-1">
        <legend className="text-xs font-semibold uppercase tracking-wider text-base-content/50 px-1">
          {t('irrigation.cycle_settings')}
        </legend>
        <div className="grid grid-cols-2 gap-3 mt-1">
          {/* Multiplier */}
          <div className="form-control">
            <label className="label py-0.5">
              <span className="label-text text-xs">{t('irrigation.multiplier')}</span>
            </label>
            <div className="flex items-center gap-1">
              <input
                type="number"
                step={0.1}
                min={0.1}
                max={10}
                className="input input-sm input-bordered w-full text-center"
                value={ctrl.multiplier}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  if (!isNaN(v) && v >= 0.1) onSettingUpdate(ctrl.id, 'multiplier', v);
                }}
              />
              <span className="text-base-content/40 text-sm">×</span>
            </div>
          </div>

          {/* Repeat */}
          <div className="form-control">
            <label className="label py-0.5">
              <span className="label-text text-xs">{t('irrigation.repeat')}</span>
            </label>
            <input
              type="number"
              step={1}
              min={0}
              max={10}
              className="input input-sm input-bordered w-full text-center"
              value={ctrl.repeat}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10);
                if (!isNaN(v) && v >= 0) onSettingUpdate(ctrl.id, 'repeat', v);
              }}
            />
          </div>
        </div>
      </fieldset>

      {/* ── Behavior ── */}
      <fieldset className="border border-base-300 rounded-lg px-3 pb-3 pt-1">
        <legend className="text-xs font-semibold uppercase tracking-wider text-base-content/50 px-1">
          {t('irrigation.behavior')}
        </legend>
        <div className="space-y-1.5 mt-1">
          {/* Auto-advance */}
          <label className="flex items-center gap-2 cursor-pointer select-none py-0.5">
            <input
              type="checkbox"
              className="toggle toggle-sm toggle-primary"
              checked={ctrl.auto_advance}
              onChange={(e) => onSettingUpdate(ctrl.id, 'auto_advance', e.target.checked)}
            />
            <span className="text-sm">{t('irrigation.auto_advance')}</span>
          </label>

          {/* Reverse */}
          <label className="flex items-center gap-2 cursor-pointer select-none py-0.5">
            <input
              type="checkbox"
              className="toggle toggle-sm"
              checked={ctrl.reverse}
              onChange={(e) => onSettingUpdate(ctrl.id, 'reverse', e.target.checked)}
            />
            <span className="text-sm">{t('irrigation.reverse')}</span>
          </label>

          {/* Standby */}
          <label className="flex items-center gap-2 cursor-pointer select-none py-0.5">
            <input
              type="checkbox"
              className="toggle toggle-sm toggle-warning"
              checked={ctrl.standby}
              onChange={(e) => onSettingUpdate(ctrl.id, 'standby', e.target.checked)}
            />
            <span className={`text-sm ${ctrl.standby ? 'text-warning font-semibold' : ''}`}>
              {t('irrigation.standby')}
            </span>
          </label>
        </div>
      </fieldset>

      {/* ── Next Run & Water Source ── */}
      <fieldset className="border border-base-300 rounded-lg px-3 pb-3 pt-1">
        <legend className="text-xs font-semibold uppercase tracking-wider text-base-content/50 px-1">
          {t('irrigation.next_run')}
        </legend>
        <div className="space-y-2 mt-1">
          {/* Skip next run */}
          <label className="flex items-center gap-2 cursor-pointer select-none py-0.5">
            <input
              type="checkbox"
              className="toggle toggle-sm toggle-warning"
              checked={ctrl.skip_next_run}
              onChange={(e) => onSettingUpdate(ctrl.id, 'skip_next_run', e.target.checked)}
            />
            <span className={`text-sm ${ctrl.skip_next_run ? 'text-warning font-semibold' : ''}`}>
              {t('irrigation.skip_next')}
            </span>
          </label>

          {/* Water Source */}
          {ctrl.water_sources.length > 1 && (
            <div className="form-control">
              <label className="label py-0.5">
                <span className="label-text text-xs">💧 {t('irrigation.water_source')}</span>
              </label>
              <div className="flex flex-wrap gap-2">
                {ctrl.water_sources.map((ws) => {
                  const isSelected = ctrl.active_water_source === ws.id;
                  return (
                    <button
                      key={ws.id}
                      className={`btn btn-sm gap-1.5 min-h-10 px-4 transition-all ${isSelected
                        ? 'btn-primary shadow-md'
                        : 'btn-outline btn-ghost border-base-300'
                        }`}
                      onClick={() => onSettingUpdate(ctrl.id, 'water_source', ws.id)}
                    >
                      <span className="text-base">💧</span>
                      <span>{ws.name || ws.id}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {ctrl.water_sources.length === 1 && (
            <div className="flex items-center gap-1.5 text-sm text-base-content/60 py-0.5">
              <span>💧 {t('irrigation.water_source')}: <strong>{ctrl.water_sources[0].name || ctrl.water_sources[0].id}</strong></span>
            </div>
          )}
        </div>
      </fieldset>
    </div>
  );

  // ── Total remaining time ─────────────────────────────────────────────────
  const totalRemaining = (() => {
    if (!isActive || countdown == null) return null;

    // Find the index of the active zone
    const activeIdx = ctrl.zones.findIndex(z => z.id === ctrl.active_zone?.id);
    if (activeIdx === -1) return countdown;

    // Sum durations of remaining zones (after active) that are enabled
    const remainingZones = ctrl.zones.slice(activeIdx + 1).filter(z => z.enabled);
    const remainingZonesTime = remainingZones.reduce(
      (sum, z) => sum + z.run_duration * 60 * ctrl.multiplier,
      0
    );

    return Math.round(countdown + remainingZonesTime);
  })();

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
                </span>
              )}
              {isPaused && ctrl.active_zone && (
                <span className="ml-1 text-base-content/60">
                  — {ctrl.active_zone.name}
                </span>
              )}
              {isPaused && ctrl.pause_timeout_s > 0 && (
                <span className="ml-1 text-warning/70 text-[10px]">
                  ⏱ {t('irrigation.pause_timeout_active').replace('{time}', fmtSeconds(ctrl.pause_timeout_s))}
                </span>
              )}
            </p>
          </div>

          {/* Timers (zone + total) */}
          {isActive && countdown != null && countdown > 0 && (
            <div className="flex flex-col items-end gap-0.5 shrink-0 text-right">
              {/* Zone timer */}
              <div className="flex items-center gap-1 text-sm">
                <FaClock className="h-3 w-3 text-success" />
                <span className="tabular-nums font-mono font-semibold text-success">
                  {fmtSeconds(countdown)}
                </span>
              </div>
              {/* Total timer */}
              {totalRemaining != null && totalRemaining > countdown && (
                <div className="flex items-center gap-1 text-xs text-base-content/50">
                  <span className="tabular-nums font-mono">
                    {t('irrigation.total_short')}: {fmtSeconds(totalRemaining)}
                  </span>
                </div>
              )}
            </div>
          )}

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
  const navigate = useNavigate();
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

  const updateSetting = useCallback(async (ctrlId: string, field: string, value: number | boolean | string) => {
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

  // Long press dialog state
  const [longPressDialog, setLongPressDialog] = useState<{
    open: boolean;
    ctrl: IrrigationController | null;
  }>({
    open: false,
    ctrl: null,
  });

  const handleLongPress = useCallback((ctrl: IrrigationController) => {
    setLongPressDialog({ open: true, ctrl });
  }, []);

  const handleGoToSettings = useCallback(() => {
    if (!longPressDialog.ctrl) return;
    const ctrlId = longPressDialog.ctrl.id;
    navigate(`/settings/template?edit=${encodeURIComponent(ctrlId)}`);
    setLongPressDialog({ open: false, ctrl: null });
  }, [longPressDialog.ctrl, navigate]);

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

      <div className="flex flex-col gap-4 max-w-2xl">
        {data.map((ctrl) => (
          <LongPressWrapper
            key={ctrl.id}
            onLongPress={() => handleLongPress(ctrl)}
            title={t('irrigation.long_press_to_edit')}
          >
            <ControllerCard
              ctrl={ctrl}
              onCommand={sendCommand}
              onZoneCommand={sendZoneCommand}
              onZoneUpdate={updateZone}
              onSettingUpdate={updateSetting}
              onScheduleSkip={toggleScheduleSkip}
            />
          </LongPressWrapper>
        ))}
      </div>

      {/* Long press dialog - go to settings */}
      <Dialog
        open={longPressDialog.open}
        onOpenChange={(open) =>
          setLongPressDialog({ open, ctrl: open ? longPressDialog.ctrl : null })
        }
      >
        <DialogContent className="sm:max-w-md bg-base-200">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FaCog className="w-5 h-5" />
              {t('irrigation.go_to_settings')}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p>{t('irrigation.go_to_settings_confirm')}</p>
            <p className="font-semibold mt-2">{longPressDialog.ctrl?.name}</p>
          </div>
          <DialogFooter className="gap-2">
            <button
              className="btn btn-ghost"
              onClick={() => setLongPressDialog({ open: false, ctrl: null })}
            >
              {t('common.cancel')}
            </button>
            <button
              className="btn btn-primary"
              onClick={handleGoToSettings}
            >
              {t('irrigation.go_to_settings')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}