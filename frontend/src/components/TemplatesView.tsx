import { useEffect, useState, useCallback, useRef } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import { FaThermometerHalf, FaShieldAlt, FaDoorOpen } from 'react-icons/fa';
import type { TemplatesData } from './templates/types';
import ThermostatCard from './templates/ThermostatCard';
import AlarmCard from './templates/AlarmCard';
import GateCard from './templates/GateCard';

export default function TemplatesView() {
  const { t } = useTranslation();
  const [data, setData] = useState<TemplatesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const response = await axios.get('/api/templates');
      setData(response.data);
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

  return (
    <div className="container mx-auto p-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <h2 className="card-title mb-4">{t('templates.title')}</h2>

          {isEmpty && (
            <div className="alert alert-info">
              <span>{t('templates.no_templates')}</span>
            </div>
          )}

          {/* Thermostats */}
          {thermostats.length > 0 && (
            <>
              <div className="divider">
                <FaThermometerHalf className="text-orange-500" />
                {t('templates.thermostats')}
              </div>
              <div className="flex flex-wrap gap-2">
                {thermostats.map((th) => (
                  <ThermostatCard
                    key={th.id}
                    data={th}
                    onSetMode={setThermostatMode}
                    onSetTemp={setThermostatTemp}
                  />
                ))}
              </div>
            </>
          )}

          {/* Alarms */}
          {alarms.length > 0 && (
            <>
              <div className="divider">
                <FaShieldAlt className="text-red-500" />
                {t('templates.alarms')}
              </div>
              <div className="flex flex-wrap gap-2">
                {alarms.map((al) => (
                  <AlarmCard
                    key={al.id}
                    data={al}
                    onCommand={sendAlarmCommand}
                  />
                ))}
              </div>
            </>
          )}

          {/* Gates */}
          {gates.length > 0 && (
            <>
              <div className="divider">
                <FaDoorOpen className="text-blue-500" />
                {t('templates.gates')}
              </div>
              <div className="flex flex-wrap gap-2">
                {gates.map((g) => (
                  <GateCard
                    key={g.id}
                    data={g}
                    onCommand={sendGateCommand}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
      {error && (
        <div className="toast">
          <div className="alert alert-error">{error}</div>
        </div>
      )}
    </div>
  );
}
