import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from '@/hooks/useTranslation';
import { useAuth } from '@/hooks/useAuth';
import axios from '@/api/axios';
import {
  FaPlay,
  FaStop,
  FaPause,
  FaForward,
  FaTint,
  FaTimesCircle,
  FaClock,
  FaCalendarAlt,
  FaCog,
  FaChevronRight,
} from 'react-icons/fa';
import { GiValve } from 'react-icons/gi';
import clsx from 'clsx';
import { LongPressWrapper } from '@/components/ui/LongPressWrapper';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import type { ZoneState, IrrigationController } from '@/types/irrigation';
import EntityInfoCard from './entityCard/EntityInfoCard';
import { historyFormatters } from './entityCard/format';
import { historyKey, recordIrrigation } from '@/utils/entityHistory';
import { TILE_BUTTON, TILE_BUTTON_STACKED, TONE_ICON, type Tone } from './templates/tileStyles';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtSeconds(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
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

  const everyLabel = zone.run_every_n === 1
    ? t('irrigation.every_run')
    : t('irrigation.every_nth_run').replace('{n}', String(zone.run_every_n));

  // The two values are edited in place; as chips they are real buttons with
  // real text, not 11px links you have to aim for.
  const chip = 'btn btn-sm h-9 min-h-9 px-3 gap-1.5 font-normal text-sm btn-ghost bg-base-content/5';

  return (
    <div
      className={clsx(
        'flex flex-col gap-2 px-2 py-3 rounded-lg transition-colors',
        isActive && 'bg-success/10',
      )}
    >
      <div className="flex items-center gap-2">
        {/* 44px label around a normal-size checkbox: the box is what you see,
            the label is what your thumb hits. */}
        <label
          className="flex items-center justify-center w-11 h-11 shrink-0 cursor-pointer"
          title={zone.enabled ? t('irrigation.zone_disable') : t('irrigation.zone_enable')}
        >
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            checked={zone.enabled}
            onChange={(e) => onCommand(ctrlId, zone.id, e.target.checked ? 'ENABLE' : 'DISABLE')}
            aria-label={zone.enabled ? t('irrigation.zone_disable') : t('irrigation.zone_enable')}
          />
        </label>
        <div className={clsx('flex-1 min-w-0', !zone.enabled && 'opacity-50')}>
          <div className="flex items-center gap-2 text-base font-medium">
            <GiValve className={clsx('w-4 h-4 shrink-0', isActive ? 'text-success animate-pulse' : 'text-base-content/40')} />
            <span className="truncate">{zone.name || zone.id}</span>
          </div>
          {!zone.enabled && <span className="text-xs text-base-content/70">{t('irrigation.zone_disabled')}</span>}
        </div>
        {isActive ? (
          <button
            type="button"
            className="btn btn-square w-11 h-11 min-h-11 shrink-0"
            title={t('irrigation.skip_zone')}
            aria-label={t('irrigation.skip_zone')}
            onClick={() => onCommand(ctrlId, zone.id, 'NEXT_VALVE')}
          >
            <FaForward className="w-4 h-4" />
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-square w-11 h-11 min-h-11 shrink-0"
            title={t('irrigation.start_zone')}
            aria-label={`${t('irrigation.start_zone')}: ${zone.name || zone.id}`}
            onClick={() => onCommand(ctrlId, zone.id, 'ON')}
            disabled={!zone.enabled}
          >
            <FaPlay className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 pl-[3.25rem]">
        {editDuration ? (
          <input
            autoFocus
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            aria-label={t('irrigation.run_duration')}
            className="input input-sm h-9 w-24 text-center"
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
            type="button"
            className={chip}
            title={t('irrigation.edit_duration')}
            onClick={() => { setDurationInput(String(zone.run_duration)); setEditDuration(true); }}
          >
            <FaClock className="w-3.5 h-3.5 opacity-60" />
            {zone.run_duration} min
          </button>
        )}

        {editEvery ? (
          <input
            autoFocus
            type="number"
            min={1}
            inputMode="numeric"
            aria-label={t('irrigation.run_every_n')}
            className="input input-sm h-9 w-20 text-center"
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
            type="button"
            className={chip}
            title={t('irrigation.edit_run_every')}
            onClick={() => { setEveryInput(String(zone.run_every_n)); setEditEvery(true); }}
          >
            <FaCalendarAlt className="w-3.5 h-3.5 opacity-60" />
            {everyLabel}
          </button>
        )}
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
  embedded = false,
}: {
  ctrl: IrrigationController;
  onCommand: (ctrlId: string, cmd: string) => void;
  onZoneCommand: (ctrlId: string, zoneId: string, cmd: string) => void;
  onZoneUpdate: (ctrlId: string, zoneId: string, field: string, value: number | boolean) => void;
  onSettingUpdate: (ctrlId: string, field: string, value: number | boolean | string) => void;
  onScheduleSkip: (ctrlId: string, idx: number, skip: boolean) => void;
  /** Inside the long-press card, whose header already has the icon and name. */
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const isRunning = ctrl.state === 'RUNNING';
  const isPaused = ctrl.state === 'PAUSED';
  const isActive = isRunning || isPaused;
  const [detailsOpen, setDetailsOpen] = useState(false);
  // Focus the title, not the first field: that is the multiplier input, and on
  // a phone focusing it throws a keyboard over half the sheet.
  const detailsTitleRef = useRef<HTMLHeadingElement>(null);

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
    <div className="flex flex-col divide-y divide-base-content/10">
      {ctrl.zones.length === 0 ? (
        <p className="text-sm text-base-content/60 text-center py-4">{t('irrigation.no_zones')}</p>
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
    <div className="flex flex-col divide-y divide-base-content/10">
      {ctrl.schedules.length === 0 ? (
        <p className="text-sm text-base-content/60 text-center py-4">{t('irrigation.no_schedules')}</p>
      ) : (
        ctrl.schedules.map((sched) => (
          <div
            key={sched.index}
            className={clsx('flex items-center gap-3 px-2 py-2', sched.skip && 'opacity-60')}
          >
            <FaClock className="w-4 h-4 text-base-content/40 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-base font-medium tabular-nums">{sched.time}</div>
              <div className="text-sm text-base-content/70 truncate">{sched.days}</div>
            </div>
            <label className="flex items-center gap-2 h-11 px-2 cursor-pointer select-none text-sm">
              <span>{t('irrigation.skip_run')}</span>
              <input
                type="checkbox"
                className="toggle toggle-warning"
                checked={sched.skip}
                onChange={(e) => onScheduleSkip(ctrl.id, sched.index, e.target.checked)}
              />
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
        <legend className="text-sm font-semibold text-base-content/80 px-1">
          {t('irrigation.cycle_settings')}
        </legend>
        <div className="grid grid-cols-2 gap-3 mt-1">
          {/* Multiplier */}
          <div className="form-control">
            <label className="label py-0.5">
              <span className="label-text text-sm">{t('irrigation.multiplier')}</span>
            </label>
            <div className="flex items-center gap-1">
              <input
                type="number"
                step={0.1}
                min={0.1}
                max={10}
                className="input w-full text-center"
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
              <span className="label-text text-sm">{t('irrigation.repeat')}</span>
            </label>
            <input
              type="number"
              step={1}
              min={0}
              max={10}
              className="input w-full text-center"
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
        <legend className="text-sm font-semibold text-base-content/80 px-1">
          {t('irrigation.behavior')}
        </legend>
        <div className="space-y-1.5 mt-1">
          {/* Auto-advance */}
          <label className="flex items-center gap-3 cursor-pointer select-none min-h-11">
            <input
              type="checkbox"
              className="toggle toggle-primary"
              checked={ctrl.auto_advance}
              onChange={(e) => onSettingUpdate(ctrl.id, 'auto_advance', e.target.checked)}
            />
            <span className="text-sm">{t('irrigation.auto_advance')}</span>
          </label>

          {/* Reverse */}
          <label className="flex items-center gap-3 cursor-pointer select-none min-h-11">
            <input
              type="checkbox"
              className="toggle"
              checked={ctrl.reverse}
              onChange={(e) => onSettingUpdate(ctrl.id, 'reverse', e.target.checked)}
            />
            <span className="text-sm">{t('irrigation.reverse')}</span>
          </label>

          {/* Standby */}
          <label className="flex items-center gap-3 cursor-pointer select-none min-h-11">
            <input
              type="checkbox"
              className="toggle toggle-warning"
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
        <legend className="text-sm font-semibold text-base-content/80 px-1">
          {t('irrigation.next_run')}
        </legend>
        <div className="space-y-2 mt-1">
          {/* Skip next run */}
          <label className="flex items-center gap-3 cursor-pointer select-none min-h-11">
            <input
              type="checkbox"
              className="toggle toggle-warning"
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
                <span className="label-text text-sm">💧 {t('irrigation.water_source')}</span>
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

  const tone: Tone = isRunning ? 'success' : isPaused ? 'warning' : 'neutral';
  const state = (
    <>
      {stateLabel(ctrl.state, t)}
      {isActive && ctrl.active_zone && <> · {ctrl.active_zone.name}</>}
    </>
  );

  // The controls for the state it is in, each with its word: a green square
  // with a play icon said "start" to nobody who had not used it before.
  const controls = !isActive ? (
    <button type="button" className={clsx(TILE_BUTTON, 'btn-primary w-full')} onClick={() => onCommand(ctrl.id, 'ON')}>
      <FaPlay className="w-3.5 h-3.5" />
      {t('irrigation.start')}
    </button>
  ) : (
    <div className={clsx('grid gap-2', isRunning ? 'grid-cols-3' : 'grid-cols-2')}>
      {isRunning ? (
        <button type="button" className={TILE_BUTTON_STACKED} onClick={() => onCommand(ctrl.id, 'PAUSE')}>
          <FaPause className="w-4 h-4" />
          <span className="text-xs leading-tight">{t('irrigation.pause')}</span>
        </button>
      ) : (
        <button type="button" className={clsx(TILE_BUTTON_STACKED, 'btn-primary')} onClick={() => onCommand(ctrl.id, 'RESUME')}>
          <FaPlay className="w-4 h-4" />
          <span className="text-xs leading-tight">{t('irrigation.resume')}</span>
        </button>
      )}
      {isRunning && (
        <button type="button" className={TILE_BUTTON_STACKED} onClick={() => onCommand(ctrl.id, 'NEXT_VALVE')}>
          <FaForward className="w-4 h-4" />
          <span className="text-xs leading-tight">{t('irrigation.next_zone_short')}</span>
        </button>
      )}
      <button type="button" className={clsx(TILE_BUTTON_STACKED, 'btn-error btn-soft')} onClick={() => onCommand(ctrl.id, 'OFF')}>
        <FaStop className="w-3.5 h-3.5" />
        <span className="text-xs leading-tight">{t('irrigation.stop')}</span>
      </button>
    </div>
  );

  return (
    <div className="stg-inset p-4 flex flex-col gap-4 h-full">
      <div className="flex items-center gap-3">
        {!embedded && (
          <span className={clsx('flex items-center justify-center w-10 h-10 rounded-full shrink-0', TONE_ICON[tone])}>
            <FaTint className="w-5 h-5" />
          </span>
        )}
        <div className="flex flex-col min-w-0 flex-1">
          {!embedded && <span className="text-base font-medium truncate">{ctrl.name}</span>}
          <span className="text-sm text-base-content/70 truncate">{state}</span>
        </div>
      </div>

      {/* While it runs, the time left is what you came to see. */}
      {isActive && countdown != null && countdown > 0 && (
        <div className="flex items-baseline gap-3 flex-wrap">
          <span className="text-3xl font-semibold tabular-nums leading-none">{fmtSeconds(countdown)}</span>
          {totalRemaining != null && totalRemaining > countdown && (
            <span className="text-sm text-base-content/70 tabular-nums">
              {t('irrigation.total_short')}: {fmtSeconds(totalRemaining)}
            </span>
          )}
        </div>
      )}
      {isPaused && ctrl.pause_timeout_s > 0 && (
        <p className="text-sm text-warning-content bg-warning/20 rounded-lg px-3 py-2">
          {t('irrigation.pause_timeout_active').replace('{time}', fmtSeconds(ctrl.pause_timeout_s))}
        </p>
      )}

      {controls}

      {/* What the hidden settings are doing to the next run, said on the tile:
          with them one click away, a skipped cycle would otherwise just look
          like a controller that forgot to water. */}
      {(ctrl.standby || ctrl.skip_next_run) && (
        <div className="flex flex-col gap-1.5">
          {ctrl.standby && (
            <p className="text-sm bg-warning/20 rounded-lg px-3 py-2">{t('irrigation.standby_active')}</p>
          )}
          {ctrl.skip_next_run && (
            <p className="text-sm bg-warning/20 rounded-lg px-3 py-2">{t('irrigation.skip_next_active')}</p>
          )}
        </div>
      )}

      <div>
        <h4 className="text-sm font-semibold text-base-content/80 px-2 mb-1">
          {t('irrigation.zones')} <span className="font-normal text-base-content/60">({ctrl.zones.length})</span>
        </h4>
        {zonesContent}
      </div>

      {/* Schedules and settings change rarely, so they live in a dialog. As
          tabs on the tile they changed its height at every switch and moved
          every tile below it. */}
      <button
        type="button"
        className={clsx(TILE_BUTTON, 'btn-ghost bg-base-content/5 w-full mt-auto justify-between')}
        onClick={() => setDetailsOpen(true)}
      >
        <span className="flex items-center gap-2">
          <FaCog className="w-4 h-4 opacity-70" />
          {t('irrigation.schedules_and_settings')}
        </span>
        <span className="flex items-center gap-2 text-base-content/60 font-normal">
          {ctrl.schedules.length > 0 && (
            <span className="badge badge-sm" aria-label={`${t('irrigation.schedules')}: ${ctrl.schedules.length}`}>
              {ctrl.schedules.length}
            </span>
          )}
          <FaChevronRight className="w-3 h-3" />
        </span>
      </button>

      <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}>
        <DialogContent maxWidthClass="sm:max-w-lg" className="overflow-y-auto" showCloseButton initialFocus={detailsTitleRef}>
          <DialogHeader>
            <DialogTitle ref={detailsTitleRef} tabIndex={-1} className="outline-none">{ctrl.name}</DialogTitle>
          </DialogHeader>
          <section className="flex flex-col gap-2">
            <h4 className="text-base font-semibold">{t('irrigation.schedules')}</h4>
            {schedulesContent}
          </section>
          <section className="flex flex-col gap-2">
            <h4 className="text-base font-semibold">{t('irrigation.settings')}</h4>
            {settingsContent}
          </section>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── IrrigationView ───────────────────────────────────────────────────────────

export default function IrrigationView() {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<IrrigationController[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const resp = await axios.get('/api/irrigation');
      setData(resp.data);
      recordIrrigation(resp.data);
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

  // Long-press card. It shows the controller live, so it opens for a viewer
  // too; only the settings entry behind ⋮ is for administrators. Only the id
  // is kept, so the card follows each poll like the tile does.
  const [card, setCard] = useState<{ open: boolean; id: string | null }>({ open: false, id: null });
  const cardCtrl = card.id ? data.find(c => c.id === card.id) : undefined;
  const closeCard = useCallback(() => setCard(prev => ({ ...prev, open: false })), []);

  const handleLongPress = useCallback((ctrl: IrrigationController) => {
    setCard({ open: true, id: ctrl.id });
  }, []);

  const handleGoToSettings = useCallback(() => {
    if (!card.id) return;
    navigate(`/settings/template?edit=${encodeURIComponent(card.id)}`);
    closeCard();
  }, [card.id, navigate, closeCard]);

  if (loading) {
    return (
      <div>
        <div className="flex justify-center items-center h-64">
          <span className="loading loading-spinner loading-lg" />
        </div>
      </div>
    );
  }

  if (error && data.length === 0) {
    return (
      <div>
        <div className="alert alert-error">
          <FaTimesCircle />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div>
        <div className="flex flex-col items-center justify-center h-48 gap-3 text-base-content/50">
          <FaTint className="h-10 w-10" />
          <p className="text-center">{t('irrigation.no_controllers')}</p>
        </div>
      </div>
    );
  }

  // Rendered inside the Templates page's "Irrigation" panel, which already
  // carries the title; a second heading and a refresh button (the data polls
  // every three seconds) only stacked another frame inside that one.
  return (
    <div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(20rem,1fr))] gap-4">
        {data.map((ctrl) => (
          <LongPressWrapper
            key={ctrl.id}
            className="h-full"
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

      {/* Long-press card: the controller live, its recent runs; settings behind ⋮ */}
      {cardCtrl && (
        <EntityInfoCard
          open={card.open}
          onOpenChange={(open) => !open && closeCard()}
          icon={<FaTint className="text-blue-400" />}
          title={cardCtrl.name}
          subtitle={cardCtrl.id}
          menu={isAdmin ? [{ key: 'settings', label: t('irrigation.go_to_settings'), icon: <FaCog />, onSelect: handleGoToSettings }] : []}
          historyKey={historyKey('irrigation', cardCtrl.id)}
          formatValue={historyFormatters.irrigation(t)}
          maxWidthClass="sm:max-w-xl"
        >
          <ControllerCard
            ctrl={cardCtrl}
            onCommand={sendCommand}
            onZoneCommand={sendZoneCommand}
            onZoneUpdate={updateZone}
            onSettingUpdate={updateSetting}
            onScheduleSkip={toggleScheduleSkip}
            embedded
          />
        </EntityInfoCard>
      )}
    </div>
  );
}