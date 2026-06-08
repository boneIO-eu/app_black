import { useState, useMemo, useCallback, useEffect } from 'react';
import axios from '@/api/axios';
import { copyToClipboard } from '@/utils/clipboard';
import { useTranslation } from '@/hooks/useTranslation';
import {
  FaFileExport, FaArrowLeft, FaArrowRight, FaCopy, FaCheck,
  FaRedo, FaChevronDown, FaChevronRight,
} from 'react-icons/fa';

// ─── Types ─────────────────────────────────────────────────────────────

interface EntityInfo {
  id: string;
  name: string;
  area?: string;
  sub_type?: string;
  zones?: number;
}

interface TypeInfo {
  count: number;
  enabled: boolean;
  entities: EntityInfo[];
}

interface DashboardMeta {
  types: Record<string, TypeInfo>;
  areas: Array<{ id: string; counts: Record<string, number> }>;
}

interface ExportSection {
  area: string;
  yaml: string;
  entity_count: number;
  breakdown?: Record<string, number>;
}

type WizardStep = 'types' | 'area' | 'export';

const STEPS: WizardStep[] = ['types', 'area', 'export'];

const TYPE_CONFIG: Record<string, { icon: string; labelKey: string }> = {
  outputs: { icon: '💡', labelKey: 'dashboard_wizard.outputs' },
  covers: { icon: '🪟', labelKey: 'dashboard_wizard.covers' },
  groups: { icon: '👥', labelKey: 'dashboard_wizard.groups' },
  alarms: { icon: '🚨', labelKey: 'dashboard_wizard.alarms' },
  gates: { icon: '🚪', labelKey: 'dashboard_wizard.gates' },
  irrigation: { icon: '🌿', labelKey: 'dashboard_wizard.irrigation' },
  modbus: { icon: '📡', labelKey: 'dashboard_wizard.modbus' },
};

// ─── localStorage persistence ──────────────────────────────────────────

const STORAGE_KEY = 'boneio_dashboard_wizard';

interface WizardState {
  step: WizardStep;
  selectedTypes: string[];
  selectedAreas: string[];
  excludedEntities: string[];
  sections: ExportSection[];
  summary: Record<string, number>;
}

function saveState(state: WizardState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch { /* quota exceeded etc. */ }
}

function loadState(): WizardState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as WizardState;
  } catch {
    return null;
  }
}

function clearState() {
  localStorage.removeItem(STORAGE_KEY);
}

// ─── Component ─────────────────────────────────────────────────────────

/**
 * HA Dashboard Wizard — step-by-step YAML export tool.
 *
 * Features:
 * - 3-step process: types → areas → export
 * - Per-entity exclusion in step 1
 * - State persisted in localStorage (survives F5)
 * - "New export" resets state
 */
export default function HaDashboardWizard() {
  const { t } = useTranslation();
  const [meta, setMeta] = useState<DashboardMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Wizard state
  const [step, setStep] = useState<WizardStep>('types');
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());
  const [selectedAreas, setSelectedAreas] = useState<Set<string>>(new Set());
  const [excludedEntities, setExcludedEntities] = useState<Set<string>>(new Set());
  const [sections, setSections] = useState<ExportSection[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});

  // UI state (not persisted)
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());
  const [generating, setGenerating] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  // Persist state on every change
  useEffect(() => {
    if (!meta) return; // Don't persist before meta loads
    saveState({
      step,
      selectedTypes: Array.from(selectedTypes),
      selectedAreas: Array.from(selectedAreas),
      excludedEntities: Array.from(excludedEntities),
      sections,
      summary,
    });
  }, [step, selectedTypes, selectedAreas, excludedEntities, sections, summary, meta]);

  // Fetch meta on mount + restore state
  useEffect(() => {
    const fetchMeta = async () => {
      try {
        setLoading(true);
        const { data } = await axios.get('/api/dashboard/meta');
        setMeta(data);

        // Try to restore saved state
        const saved = loadState();
        if (saved) {
          setStep(saved.step);
          setSelectedTypes(new Set(saved.selectedTypes));
          setSelectedAreas(new Set(saved.selectedAreas));
          setExcludedEntities(new Set(saved.excludedEntities));
          setSections(saved.sections || []);
          setSummary(saved.summary || {});
        } else {
          // Pre-select enabled types
          const enabled = new Set<string>();
          for (const [typeKey, typeInfo] of Object.entries(data.types)) {
            if ((typeInfo as TypeInfo).enabled) {
              enabled.add(typeKey);
            }
          }
          setSelectedTypes(enabled);
        }
      } catch (err) {
        setError(String(err));
      } finally {
        setLoading(false);
      }
    };
    fetchMeta();
  }, []);

  // ─── Derived state ─────────────────────────────────────────────────

  /**
   * Effective entity count per type (minus excluded).
   */
  const effectiveCounts = useMemo(() => {
    if (!meta) return {};
    const counts: Record<string, number> = {};
    for (const [typeKey, typeInfo] of Object.entries(meta.types)) {
      counts[typeKey] = typeInfo.entities.filter(e => !excludedEntities.has(e.id)).length;
    }
    return counts;
  }, [meta, excludedEntities]);

  /**
   * Filter areas based on selected types (accounting for excluded entities).
   */
  const filteredAreas = useMemo(() => {
    if (!meta) return [];
    // Count per area from non-excluded entities
    const areaCounts: Record<string, number> = {};
    for (const typeKey of selectedTypes) {
      const typeInfo = meta.types[typeKey];
      if (!typeInfo) continue;
      for (const entity of typeInfo.entities) {
        if (excludedEntities.has(entity.id)) continue;
        const area = entity.area || 'other';
        areaCounts[area] = (areaCounts[area] || 0) + 1;
      }
    }
    return meta.areas
      .filter(area => (areaCounts[area.id] || 0) > 0)
      .map(area => ({ ...area, effectiveCount: areaCounts[area.id] || 0 }));
  }, [meta, selectedTypes, excludedEntities]);

  const totalEntityCount = useMemo(() => {
    return filteredAreas.reduce((sum, a) => sum + a.effectiveCount, 0);
  }, [filteredAreas]);

  const allAreasSelected = useMemo(() => {
    if (filteredAreas.length === 0) return false;
    return filteredAreas.every(a => selectedAreas.has(a.id));
  }, [filteredAreas, selectedAreas]);

  // ─── Handlers ──────────────────────────────────────────────────────

  const toggleType = useCallback((typeKey: string) => {
    setSelectedTypes(prev => {
      const next = new Set(prev);
      if (next.has(typeKey)) {
        next.delete(typeKey);
      } else {
        next.add(typeKey);
      }
      return next;
    });
  }, []);

  const toggleExpanded = useCallback((typeKey: string) => {
    setExpandedTypes(prev => {
      const next = new Set(prev);
      if (next.has(typeKey)) {
        next.delete(typeKey);
      } else {
        next.add(typeKey);
      }
      return next;
    });
  }, []);

  const toggleEntity = useCallback((entityId: string) => {
    setExcludedEntities(prev => {
      const next = new Set(prev);
      if (next.has(entityId)) {
        next.delete(entityId);
      } else {
        next.add(entityId);
      }
      return next;
    });
  }, []);

  const toggleAllAreas = useCallback(() => {
    if (allAreasSelected) {
      setSelectedAreas(new Set());
    } else {
      setSelectedAreas(new Set(filteredAreas.map(a => a.id)));
    }
  }, [allAreasSelected, filteredAreas]);

  const toggleArea = useCallback((areaId: string) => {
    setSelectedAreas(prev => {
      const next = new Set(prev);
      if (next.has(areaId)) {
        next.delete(areaId);
      } else {
        next.add(areaId);
      }
      return next;
    });
  }, []);

  const handleGenerate = useCallback(async () => {
    if (selectedAreas.size === 0) return;
    try {
      setGenerating(true);
      const params: Record<string, string> = {
        types: Array.from(selectedTypes).join(','),
      };
      if (!allAreasSelected) {
        params.area = Array.from(selectedAreas).join(',');
      }
      if (excludedEntities.size > 0) {
        params.exclude_ids = Array.from(excludedEntities).join(',');
      }
      const { data } = await axios.get('/api/dashboard/generate', { params });
      setSections(data.sections || []);
      setSummary(data.summary || {});
      setStep('export');
    } catch (err) {
      setError(String(err));
    } finally {
      setGenerating(false);
    }
  }, [selectedAreas, selectedTypes, allAreasSelected, excludedEntities]);

  const handleCopy = useCallback(async (idx: number) => {
    const section = sections[idx];
    if (!section) return;
    await copyToClipboard(section.yaml);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 3000);
  }, [sections]);

  const handleReset = useCallback(() => {
    clearState();
    setStep('types');
    setSelectedAreas(new Set());
    setExcludedEntities(new Set());
    setSections([]);
    setSummary({});
    setCopiedIdx(null);
    // Re-select enabled types
    if (meta) {
      const enabled = new Set<string>();
      for (const [typeKey, typeInfo] of Object.entries(meta.types)) {
        if (typeInfo.enabled) enabled.add(typeKey);
      }
      setSelectedTypes(enabled);
    }
  }, [meta]);

  const currentStepIndex = STEPS.indexOf(step);

  // ─── Render ────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <span className="loading loading-spinner loading-lg text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-error">
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <h2 className="card-title text-lg gap-2 mb-4">
          <FaFileExport className="text-primary" />
          {t('dashboard_wizard.heading')}
        </h2>

        {/* Steps indicator */}
        <ul className="steps steps-horizontal w-full mb-6">
          <li className={`step ${currentStepIndex >= 0 ? 'step-primary' : ''}`}>
            {t('dashboard_wizard.step_types')}
          </li>
          <li className={`step ${currentStepIndex >= 1 ? 'step-primary' : ''}`}>
            {t('dashboard_wizard.step_area')}
          </li>
          <li className={`step ${currentStepIndex >= 2 ? 'step-primary' : ''}`}>
            {t('dashboard_wizard.step_export')}
          </li>
        </ul>

        {/* ──── Step 1: Select types + entity exclusion ──── */}
        {step === 'types' && meta && (
          <div>
            <p className="text-sm text-base-content/70 mb-4">
              {t('dashboard_wizard.select_types')}
            </p>
            <div className="space-y-2">
              {Object.entries(TYPE_CONFIG).map(([typeKey, config]) => {
                const typeInfo = meta.types[typeKey];
                if (!typeInfo) return null;
                const isDisabled = !typeInfo.enabled;
                const isSelected = selectedTypes.has(typeKey);
                const isExpanded = expandedTypes.has(typeKey);
                const effectiveCount = effectiveCounts[typeKey] ?? typeInfo.count;
                const excludedCount = typeInfo.entities.filter(e => excludedEntities.has(e.id)).length;

                return (
                  <div key={typeKey}>
                    {/* Type header row */}
                    <div
                      className={`
                        flex items-center gap-3 p-4 rounded-lg border-2 transition-all
                        ${isSelected ? 'border-primary bg-primary/10' : 'border-base-300'}
                        ${isDisabled ? 'opacity-40' : 'cursor-pointer hover:border-base-content/30'}
                      `}
                    >
                      <input
                        type="checkbox"
                        className="checkbox checkbox-primary checkbox-sm"
                        checked={isSelected}
                        disabled={isDisabled}
                        onChange={() => !isDisabled && toggleType(typeKey)}
                      />
                      <span className="text-2xl">{config.icon}</span>
                      <div
                        className="flex-1 cursor-pointer"
                        onClick={() => !isDisabled && toggleExpanded(typeKey)}
                      >
                        <div className="font-medium">
                          {t(config.labelKey)}
                          {excludedCount > 0 && (
                            <span className="text-xs text-warning ml-2">
                              (-{excludedCount})
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-base-content/50">
                          {effectiveCount} / {typeInfo.count}
                        </div>
                      </div>
                      {!isDisabled && typeInfo.entities.length > 0 && (
                        <button
                          className="btn btn-ghost btn-xs"
                          onClick={(e) => { e.stopPropagation(); toggleExpanded(typeKey); }}
                        >
                          {isExpanded ? <FaChevronDown /> : <FaChevronRight />}
                        </button>
                      )}
                    </div>

                    {/* Expanded entity list */}
                    {isExpanded && typeInfo.entities.length > 0 && (
                      <div className="ml-10 mt-1 mb-2 space-y-0.5 max-h-60 overflow-y-auto border border-base-300 rounded-lg p-2">
                        {typeInfo.entities.map(entity => {
                          const isExcluded = excludedEntities.has(entity.id);
                          return (
                            <label
                              key={entity.id}
                              className={`flex items-center gap-2 p-1.5 rounded hover:bg-base-300/50 cursor-pointer text-sm ${isExcluded ? 'opacity-50 line-through' : ''}`}
                            >
                              <input
                                type="checkbox"
                                className="checkbox checkbox-xs"
                                checked={!isExcluded}
                                onChange={() => toggleEntity(entity.id)}
                              />
                              <span className="flex-1 truncate">
                                {entity.name}
                              </span>
                              {entity.sub_type && (
                                <span className="badge badge-xs badge-ghost">
                                  {entity.sub_type}
                                </span>
                              )}
                              {entity.area && entity.area !== 'other' && (
                                <span className="badge badge-xs badge-outline">
                                  {entity.area.replace(/_/g, ' ')}
                                </span>
                              )}
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="flex justify-end mt-6">
              <button
                className="btn btn-primary gap-2"
                disabled={selectedTypes.size === 0}
                onClick={() => setStep('area')}
              >
                {t('dashboard_wizard.next')}
                <FaArrowRight />
              </button>
            </div>
          </div>
        )}

        {/* ──── Step 2: Select areas ──── */}
        {step === 'area' && meta && (
          <div>
            <p className="text-sm text-base-content/70 mb-4">
              {t('dashboard_wizard.select_area')}
            </p>
            {filteredAreas.length === 0 ? (
              <div className="alert alert-warning">
                <span>{t('dashboard_wizard.no_entities')}</span>
              </div>
            ) : (
              <div className="space-y-2">
                {/* All areas toggle */}
                <label
                  className={`
                    flex items-center gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all
                    ${allAreasSelected ? 'border-primary bg-primary/10' : 'border-base-300 hover:border-base-content/30'}
                  `}
                >
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary checkbox-sm"
                    checked={allAreasSelected}
                    onChange={toggleAllAreas}
                  />
                  <span className="text-xl">🌍</span>
                  <div className="flex-1">
                    <div className="font-medium">{t('dashboard_wizard.all_areas')}</div>
                    <div className="text-xs text-base-content/50">
                      {t('dashboard_wizard.count', { count: totalEntityCount })}
                    </div>
                  </div>
                </label>

                {filteredAreas.map(area => {
                  const isSelected = selectedAreas.has(area.id);
                  const displayName = area.id === 'other'
                    ? t('dashboard_wizard.no_area')
                    : area.id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

                  return (
                    <label
                      key={area.id}
                      className={`
                        flex items-center gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all
                        ${isSelected ? 'border-primary bg-primary/10' : 'border-base-300 hover:border-base-content/30'}
                      `}
                    >
                      <input
                        type="checkbox"
                        className="checkbox checkbox-primary checkbox-sm"
                        checked={isSelected}
                        onChange={() => toggleArea(area.id)}
                      />
                      <span className="text-xl">🏠</span>
                      <div className="flex-1">
                        <div className="font-medium">{displayName}</div>
                        <div className="text-xs text-base-content/50">
                          {t('dashboard_wizard.count', { count: area.effectiveCount })}
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
            <div className="flex justify-between mt-6">
              <button
                className="btn btn-ghost gap-2"
                onClick={() => setStep('types')}
              >
                <FaArrowLeft />
                {t('dashboard_wizard.back')}
              </button>
              <button
                className="btn btn-primary gap-2"
                disabled={selectedAreas.size === 0 || generating}
                onClick={handleGenerate}
              >
                {generating && <span className="loading loading-spinner loading-xs" />}
                {t('dashboard_wizard.next')}
                <FaArrowRight />
              </button>
            </div>
          </div>
        )}

        {/* ──── Step 3: Export — per-area cards ──── */}
        {step === 'export' && (
          <div>
            <p className="text-sm text-base-content/70 mb-4">
              {t('dashboard_wizard.ready_desc')}
            </p>

            {sections.length === 0 ? (
              <div className="alert alert-warning">
                <span>{t('dashboard_wizard.no_entities')}</span>
              </div>
            ) : (
              <div className="space-y-3">
                {sections.map((section, idx) => {
                  const isCopied = copiedIdx === idx;
                  return (
                    <div key={idx} className="bg-base-300 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="font-bold text-sm">{section.area}</h3>
                          {section.breakdown && Object.keys(section.breakdown).length > 0 ? (
                            <p className="text-xs text-base-content/50">
                              {Object.entries(section.breakdown).map(([label, count], i) => (
                                <span key={label}>
                                  {i > 0 && ' · '}
                                  {count}× {label}
                                </span>
                              ))}
                            </p>
                          ) : (
                            <p className="text-xs text-base-content/50">
                              {t('dashboard_wizard.count', { count: section.entity_count })}
                            </p>
                          )}
                        </div>
                        <button
                          className={`btn btn-sm gap-2 ${isCopied ? 'btn-success' : 'btn-primary'}`}
                          onClick={() => handleCopy(idx)}
                        >
                          {isCopied ? <FaCheck /> : <FaCopy />}
                          {isCopied ? t('dashboard_wizard.copied') : t('dashboard_wizard.copy_yaml')}
                        </button>
                      </div>
                      {isCopied && (
                        <div className="mt-2 text-xs text-success">
                          {t('dashboard_wizard.paste_hint')}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Summary */}
            {Object.keys(summary).length > 0 && (
              <div className="mt-4 text-sm text-base-content/60">
                {Object.entries(summary).map(([typeKey, count]) => {
                  const config = TYPE_CONFIG[typeKey];
                  if (!config || count === 0) return null;
                  return (
                    <span key={typeKey} className="mr-4">
                      {config.icon} {count}× {t(config.labelKey)}
                    </span>
                  );
                })}
              </div>
            )}

            <div className="flex justify-between mt-6">
              <button
                className="btn btn-ghost gap-2"
                onClick={() => setStep('area')}
              >
                <FaArrowLeft />
                {t('dashboard_wizard.back')}
              </button>
              <button
                className="btn btn-outline btn-primary gap-2"
                onClick={handleReset}
              >
                <FaRedo />
                {t('dashboard_wizard.new_export')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
