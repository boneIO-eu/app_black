import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from '@/hooks/useTranslation';
import { useAuth } from '@/hooks/useAuth';
import axios from '@/api/axios';
import { FaThermometerHalf, FaShieldAlt, FaDoorOpen, FaCog, FaTint } from 'react-icons/fa';
import { LongPressWrapper } from '@/components/ui/LongPressWrapper';
import EntityInfoCard from './entityCard/EntityInfoCard';
import { historyFormatters } from './entityCard/format';
import { historyKey, recordTemplates } from '@/utils/entityHistory';
import type { AlarmState, GateState, TemplatesData, ThermostatState } from './templates/types';
import ThermostatCard from './templates/ThermostatCard';
import AlarmCard from './templates/AlarmCard';
import GateCard from './templates/GateCard';
import IrrigationView from './IrrigationView';
import { EntityPanel } from './EntityGrid';

type TemplateKind = 'thermostat' | 'alarm' | 'gate';

/**
 * Template tiles carry a row of three buttons, which an output tile does not,
 * so they get fewer, wider columns than ENTITY_GRID_CLASS — but a grid all the
 * same, so a group fills its panel instead of huddling in the left corner.
 */
const TEMPLATE_GRID_CLASS = 'grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4';

/**
 * A group is as wide as its tiles, not as wide as the page. With one
 * thermostat, one alarm and two gates, full-width panels each left a single
 * tile in the corner of an empty card; sized by count they share a row, and
 * a group with many tiles still gets a whole row to itself by growing.
 */
const groupStyle = (tiles: number): React.CSSProperties => ({
  flex: `${tiles} 1 calc(${tiles} * 16rem + ${tiles - 1} * 1rem + 2.5rem)`,
  minWidth: 0,
});
import { useConfig } from '../contexts/ConfigContext';

/**
 * TemplatesView - Combined view for Templates and Irrigation.
 * Shows tabs: "Szablony" (Templates) and "Nawadnianie" (Irrigation).
 * Irrigation tab is only visible when irrigation controllers exist in config.
 */
export default function TemplatesView() {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const { hasIrrigationSection } = useConfig();
  const [data, setData] = useState<TemplatesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Long-press card. It shows the template live, so it opens for a viewer
  // too; only the settings entry behind ⋮ is for administrators.
  const [card, setCard] = useState<{ open: boolean; kind: TemplateKind; id: string | null }>({
    open: false,
    kind: 'thermostat',
    id: null,
  });
  const closeCard = useCallback(() => setCard(prev => ({ ...prev, open: false })), []);

  const handleLongPress = useCallback((kind: TemplateKind, templateId: string) => {
    setCard({ open: true, kind, id: templateId });
  }, []);

  const handleGoToSettings = useCallback(() => {
    if (!card.id) return;
    navigate(`/settings/template?edit=${encodeURIComponent(card.id)}`);
    closeCard();
  }, [card.id, navigate, closeCard]);

  const fetchData = useCallback(async () => {
    try {
      const response = await axios.get('/api/templates');
      setData(response.data);
      recordTemplates(response.data);
      setError(null);
    } catch (err) {
      console.error('Error fetching templates:', err);
      setError('Failed to load template data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const fetchRef = useRef(fetchData);
  fetchRef.current = fetchData;

  // -- Thermostat actions --
  const setThermostatMode = useCallback(async (id: string, mode: string) => {
    try {
      await axios.post(`/api/templates/thermostats/${id}/mode`, { mode });
      fetchRef.current();
    } catch (err) {
      console.error('Error setting thermostat mode:', err);
    }
  }, []);

  const setThermostatTemp = useCallback(async (id: string, temp: number) => {
    try {
      await axios.post(`/api/templates/thermostats/${id}/temperature`, { temperature: temp });
      fetchRef.current();
    } catch (err) {
      console.error('Error setting thermostat temperature:', err);
    }
  }, []);

  // -- Alarm actions --
  const sendAlarmCommand = useCallback(async (id: string, command: string, code?: string) => {
    try {
      const body: Record<string, string> = { command };
      if (code) body.code = code;
      await axios.post(`/api/templates/alarms/${id}/command`, body);
      fetchRef.current();
    } catch (err) {
      console.error('Error sending alarm command:', err);
    }
  }, []);

  // -- Gate actions --
  const sendGateCommand = useCallback(async (id: string, command: string) => {
    try {
      await axios.post(`/api/templates/gates/${id}/command`, { command });
      fetchRef.current();
    } catch (err) {
      console.error('Error sending gate command:', err);
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

  if (error && !data) {
    return (
      <div className="container mx-auto p-4">
        <div className="alert alert-error">
          <span>{error}</span>
        </div>
      </div>
    );
  }

  const thermostats = data?.thermostats ?? [];
  const alarms = data?.alarms ?? [];
  const gates = data?.gates ?? [];
  const isEmpty = thermostats.length === 0 && alarms.length === 0 && gates.length === 0;

  /** The card for `card`, drawn from the latest poll like the tile is. */
  const renderCard = () => {
    if (!card.id) return null;
    const entity = card.kind === 'thermostat'
      ? thermostats.find(x => x.id === card.id)
      : card.kind === 'alarm'
        ? alarms.find(x => x.id === card.id)
        : gates.find(x => x.id === card.id);
    if (!entity) return null;
    const Icon = card.kind === 'thermostat' ? FaThermometerHalf : card.kind === 'alarm' ? FaShieldAlt : FaDoorOpen;
    const iconClass = card.kind === 'thermostat' ? 'text-orange-500' : card.kind === 'alarm' ? 'text-red-500' : 'text-blue-500';
    return (
      <EntityInfoCard
        open={card.open}
        onOpenChange={(open) => !open && closeCard()}
        icon={<Icon className={iconClass} />}
        title={entity.name || entity.id}
        subtitle={entity.id}
        menu={isAdmin ? [{ key: 'settings', label: t('inputs.go_to_settings'), icon: <FaCog />, onSelect: handleGoToSettings }] : []}
        historyKey={historyKey(card.kind, entity.id)}
        formatValue={historyFormatters[card.kind](t)}
      >
        {card.kind === 'thermostat' && (
          <ThermostatCard data={entity as ThermostatState} onSetMode={setThermostatMode} onSetTemp={setThermostatTemp} embedded />
        )}
        {card.kind === 'alarm' && <AlarmCard data={entity as AlarmState} onCommand={sendAlarmCommand} embedded />}
        {card.kind === 'gate' && <GateCard data={entity as GateState} onCommand={sendGateCommand} embedded />}
      </EntityInfoCard>
    );
  };

  return (
    <div className="container mx-auto p-4">
      {/* No panel around the list: the page is a tinted field and the
          entities are the cards on it. */}
      <div>
        <div className="flex flex-col gap-2">
          <h2 className="text-xl font-bold tracking-tight mb-4">{t('templates.title')}</h2>

          {isEmpty && !hasIrrigationSection && (
            <div className="alert alert-info">
              <span>{t('templates.no_templates')}</span>
            </div>
          )}

          <div className="flex flex-wrap gap-5">
          {/* Thermostats */}
          {thermostats.length > 0 && (
            <div style={groupStyle(thermostats.length)}>
              <EntityPanel
                className="mb-0 h-full"
                title={
                  <>
                    <FaThermometerHalf className="text-orange-500" />
                    {t('templates.thermostats')}
                  </>
                }
              >
                <div className={TEMPLATE_GRID_CLASS}>
                {thermostats.map((th) => (
                  <LongPressWrapper key={th.id} className="h-full" onLongPress={() => handleLongPress('thermostat', th.id)}>
                    <ThermostatCard
                      data={th}
                      onSetMode={setThermostatMode}
                      onSetTemp={setThermostatTemp}
                    />
                  </LongPressWrapper>
                ))}
                </div>
              </EntityPanel>
            </div>
          )}

          {/* Alarms */}
          {alarms.length > 0 && (
            <div style={groupStyle(alarms.length)}>
              <EntityPanel
                className="mb-0 h-full"
                title={
                  <>
                    <FaShieldAlt className="text-red-500" />
                    {t('templates.alarms')}
                  </>
                }
              >
                <div className={TEMPLATE_GRID_CLASS}>
                {alarms.map((al) => (
                  <LongPressWrapper key={al.id} className="h-full" onLongPress={() => handleLongPress('alarm', al.id)}>
                    <AlarmCard
                      data={al}
                      onCommand={sendAlarmCommand}
                    />
                  </LongPressWrapper>
                ))}
                </div>
              </EntityPanel>
            </div>
          )}

          {/* Gates */}
          {gates.length > 0 && (
            <div style={groupStyle(gates.length)}>
              <EntityPanel
                className="mb-0 h-full"
                title={
                  <>
                    <FaDoorOpen className="text-blue-500" />
                    {t('templates.gates')}
                  </>
                }
              >
                <div className={TEMPLATE_GRID_CLASS}>
                {gates.map((g) => (
                  <LongPressWrapper key={g.id} className="h-full" onLongPress={() => handleLongPress('gate', g.id)}>
                    <GateCard
                      data={g}
                      onCommand={sendGateCommand}
                    />
                  </LongPressWrapper>
                ))}
                </div>
              </EntityPanel>
            </div>
          )}

          {/* Irrigation */}
          {hasIrrigationSection && (
            <div className="basis-full">
              <EntityPanel
                className="mb-0"
                title={
                  <>
                    <FaTint className="text-blue-400" />
                    {t('navigation.irrigation')}
                  </>
                }
              >
                <IrrigationView />
              </EntityPanel>
            </div>
          )}
          </div>
        </div>
      </div>

      {error && (
        <div className="toast">
          <div className="alert alert-error">{error}</div>
        </div>
      )}

      {/* Long-press card: the template live, its recent changes; settings behind ⋮ */}
      {renderCard()}
    </div>
  );
}
