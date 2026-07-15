/**
 * BindingMatrix — Read-only matrix view showing all input→output bindings.
 *
 * Desktop: full cross-reference table (inputs as rows, outputs/covers as columns).
 * Mobile: accordion list of inputs with their bindings + unconfigured sections.
 */
import React, { useMemo, useState, useCallback, useRef } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  FaFilter, FaChevronDown, FaChevronUp, FaExclamationTriangle,
  FaCheckCircle, FaTimesCircle, FaEye, FaEyeSlash, FaPen,
} from 'react-icons/fa';
import clsx from 'clsx';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import EventForm from './EventForm';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A single parsed binding from an input to an output/cover. */
interface Binding {
  clickType: string;
  actionType: string; // 'output' | 'cover' | 'remote_output' | 'remote_cover' | 'mqtt' | etc.
  targetId: string;   // boneio_output / boneio_cover / output_id etc.
  actionValue: string; // TOGGLE / ON / OFF / OPEN / CLOSE / STOP
  remoteDevice?: string;
}

/** Resolved input row. */
interface InputRow {
  id: string;
  name: string;
  area?: string;
  type: 'local' | 'remote';
  remoteDevice?: string;
  bindings: Binding[];
}

/** Resolved output/cover column. */
interface OutputColumn {
  id: string;       // unique key used in matrix
  name: string;
  area?: string;
  type: 'output' | 'cover' | 'remote_output' | 'remote_cover';
  remoteDevice?: string;
}

interface ConfigSection {
  name: string;
  schema: any;
  normalizedSchema: any;
  uiSchema: any;
  data: Record<string, any>;
}

interface BindingMatrixProps {
  formData: Record<string, any>;
  sections: ConfigSection[];
  onSaveSection: (sectionName: string, dataOverride?: any) => Promise<void>;
  onUpdateFormData: (section: string, data: any) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CLICK_TYPE_LABELS: Record<string, string> = {
  single: '1×',
  double: '2×',
  triple: '3×',
  long: '⏎',
  pressed: '▼',
  released: '▲',
  double_then_long: '2×⏎',
  single_then_long: '1×⏎',
  double_then_single: '2×1×',
};

const ACTION_SHORT: Record<string, string> = {
  TOGGLE: '⇆',
  ON: '●',
  OFF: '○',
  OPEN: '▲',
  CLOSE: '▼',
  STOP: '■',
};

/** Map binding clickType → EventForm tab name. */
const CLICK_TYPE_TO_TAB: Record<string, 'basic' | 'single' | 'double' | 'triple' | 'long' | 'sequences' | 'advanced'> = {
  single: 'single',
  double: 'double',
  triple: 'triple',
  long: 'long',
  pressed: 'basic',
  released: 'basic',
  double_then_long: 'sequences',
  single_then_long: 'sequences',
  double_then_single: 'sequences',
};

/**
 * Get a short label for a binding cell.
 * e.g. "1× ⇆" for single-click toggle.
 */
function bindingLabel(b: Binding): string {
  const click = CLICK_TYPE_LABELS[b.clickType] || b.clickType;
  const act = ACTION_SHORT[b.actionValue] || b.actionValue;
  return `${click} ${act}`;
}

/**
 * Get a verbose label for tooltip.
 * e.g. "single → TOGGLE"
 */
function bindingTooltip(b: Binding): string {
  return `${b.clickType} → ${b.actionValue}`;
}

/**
 * Extract target ID from an action definition.
 */
function extractTargetId(action: any): { targetId: string; actionType: string; actionValue: string; remoteDevice?: string } {
  const actionType = action.action || 'output';
  let targetId = '';
  let actionValue = '';
  let remoteDevice: string | undefined;

  switch (actionType) {
    case 'output':
      targetId = action.boneio_output || '';
      actionValue = action.action_output || 'TOGGLE';
      break;
    case 'cover':
      targetId = action.boneio_cover || '';
      actionValue = action.action_cover || 'TOGGLE';
      break;
    case 'remote_output':
      remoteDevice = action.boneio_id || '';
      targetId = remoteDevice ? `${remoteDevice}/${action.output_id || ''}` : (action.output_id || '');
      actionValue = action.action_output || 'TOGGLE';
      break;
    case 'remote_cover':
      remoteDevice = action.boneio_id || '';
      targetId = remoteDevice ? `${remoteDevice}/${action.cover_id || ''}` : (action.cover_id || '');
      actionValue = action.action_cover || 'TOGGLE';
      break;
    default:
      // mqtt, etc. — skip for now
      targetId = '';
      actionValue = action.action_output || action.action_cover || '';
      break;
  }

  return { targetId, actionType, actionValue, remoteDevice };
}

// ---------------------------------------------------------------------------
// Data extraction
// ---------------------------------------------------------------------------

/**
 * Parse all inputs (local + remote) into InputRow[].
 */
function extractInputs(formData: Record<string, any>): InputRow[] {
  const rows: InputRow[] = [];
  const clickTypes = ['single', 'double', 'triple', 'long', 'pressed', 'released',
    'double_then_long', 'single_then_long', 'double_then_single'];

  // Local inputs (event + binary_sensor via composite section 'local_inputs')
  const localInputs = formData.local_inputs || [];
  for (const input of localInputs) {
    const id = input.id || input.pin || '';
    const bindings: Binding[] = [];
    for (const ct of clickTypes) {
      const actions = input.actions?.[ct] || [];
      for (const action of actions) {
        const { targetId, actionType, actionValue, remoteDevice } = extractTargetId(action);
        if (targetId) {
          bindings.push({ clickType: ct, actionType, targetId, actionValue, remoteDevice });
        }
      }
    }
    rows.push({
      id,
      name: input.name || input.id || input.pin || id,
      area: input.area || undefined,
      type: 'local',
      bindings,
    });
  }

  // Remote inputs
  const remoteInputs = formData.remote_inputs || [];
  for (const input of remoteInputs) {
    const device = input.boneio_id || input.remote_device || '';
    const inputId = input.id || input.entity_id || '';
    const id = device ? `${device}/${inputId}` : inputId;
    const bindings: Binding[] = [];
    for (const ct of clickTypes) {
      const actions = input.actions?.[ct] || [];
      for (const action of actions) {
        const { targetId, actionType, actionValue, remoteDevice } = extractTargetId(action);
        if (targetId) {
          bindings.push({ clickType: ct, actionType, targetId, actionValue, remoteDevice });
        }
      }
    }
    rows.push({
      id,
      name: input.name || input.id || inputId,
      area: input.area || undefined,
      type: 'remote',
      remoteDevice: device,
      bindings,
    });
  }

  return rows;
}

/**
 * Extract all outputs and covers into OutputColumn[].
 */
function extractOutputs(formData: Record<string, any>): OutputColumn[] {
  const cols: OutputColumn[] = [];

  // Local outputs
  const outputs = formData.output || [];
  for (const o of outputs) {
    const id = o.id || '';
    cols.push({
      id,
      name: o.name || o.id || id,
      area: o.area || undefined,
      type: 'output',
    });
  }

  // Local covers
  const covers = formData.cover || [];
  for (const c of covers) {
    const id = c.id || '';
    cols.push({
      id,
      name: c.name || c.id || id,
      area: c.area || undefined,
      type: 'cover',
    });
  }

  // Remote outputs
  const remoteOutputs = formData.remote_outputs || [];
  for (const ro of remoteOutputs) {
    const device = ro.boneio_id || ro.remote_device || '';
    const outputId = ro.id || ro.output_id || '';
    const id = device ? `${device}/${outputId}` : outputId;
    cols.push({
      id,
      name: ro.name || ro.id || outputId,
      area: ro.area || undefined,
      type: 'remote_output',
      remoteDevice: device,
    });
  }

  return cols;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Statistics banner at the top. */
function StatsBanner({ inputs, outputs, t }: {
  inputs: InputRow[];
  outputs: OutputColumn[];
  t: (key: string, opts?: any) => string;
}) {
  const localInputs = inputs.filter(i => i.type === 'local');
  const remoteInputs = inputs.filter(i => i.type === 'remote');
  const localOutputs = outputs.filter(o => o.type === 'output');
  const localCovers = outputs.filter(o => o.type === 'cover');
  const remoteOutputs = outputs.filter(o => o.type === 'remote_output' || o.type === 'remote_cover');

  const boundLocalInputs = localInputs.filter(i => i.bindings.length > 0);
  const boundRemoteInputs = remoteInputs.filter(i => i.bindings.length > 0);

  // Outputs that appear as target in any binding
  const allTargetIds = new Set(inputs.flatMap(i => i.bindings.map(b => b.targetId)));
  const boundLocalOutputs = localOutputs.filter(o => allTargetIds.has(o.id));
  const boundLocalCovers = localCovers.filter(o => allTargetIds.has(o.id));
  const boundRemoteOutputs = remoteOutputs.filter(o => allTargetIds.has(o.id));

  const totalBindings = inputs.reduce((sum, i) => sum + i.bindings.length, 0);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
      {/* Local */}
      <div className="bg-base-200/50 rounded-xl p-3 border border-base-300 space-y-1">
        <h4 className="text-xs font-bold uppercase tracking-wider text-base-content/50">{t('binding_matrix.local')}</h4>
        <p className="text-xs text-base-content/70">
          📥 {t('binding_matrix.inputs')}: {localInputs.length}
          <span className="text-success ml-1">({boundLocalInputs.length} ✓)</span>
          <span className="text-warning ml-1">({localInputs.length - boundLocalInputs.length} ○)</span>
        </p>
        <p className="text-xs text-base-content/70">
          💡 {t('binding_matrix.outputs')}: {localOutputs.length}
          <span className="text-success ml-1">({boundLocalOutputs.length} ✓)</span>
          <span className="text-warning ml-1">({localOutputs.length - boundLocalOutputs.length} ○)</span>
        </p>
        <p className="text-xs text-base-content/70">
          🚪 {t('binding_matrix.covers')}: {localCovers.length}
          <span className="text-success ml-1">({boundLocalCovers.length} ✓)</span>
          <span className="text-warning ml-1">({localCovers.length - boundLocalCovers.length} ○)</span>
        </p>
      </div>

      {/* Remote */}
      {(remoteInputs.length > 0 || remoteOutputs.length > 0) && (
        <div className="bg-info/5 rounded-xl p-3 border border-info/20 space-y-1">
          <h4 className="text-xs font-bold uppercase tracking-wider text-info/70">{t('binding_matrix.remote')}</h4>
          <p className="text-xs text-base-content/70">
            📥 {t('binding_matrix.inputs')}: {remoteInputs.length}
            <span className="text-success ml-1">({boundRemoteInputs.length} ✓)</span>
            <span className="text-warning ml-1">({remoteInputs.length - boundRemoteInputs.length} ○)</span>
          </p>
          <p className="text-xs text-base-content/70">
            📡 {t('binding_matrix.outputs')}: {remoteOutputs.length}
            <span className="text-success ml-1">({boundRemoteOutputs.length} ✓)</span>
            <span className="text-warning ml-1">({remoteOutputs.length - boundRemoteOutputs.length} ○)</span>
          </p>
        </div>
      )}

      {/* Total */}
      <div className="bg-primary/5 rounded-xl p-3 border border-primary/20 flex flex-col justify-center">
        <p className="text-2xl font-extrabold text-primary">{totalBindings}</p>
        <p className="text-xs font-medium text-primary/70">{t('binding_matrix.total_bindings')}</p>
      </div>
    </div>
  );
}

/** Unconfigured items section (mobile + desktop). */
function UnconfiguredSection({ inputs, outputs, t }: {
  inputs: InputRow[];
  outputs: OutputColumn[];
  t: (key: string, opts?: any) => string;
}) {
  const [showLocal, setShowLocal] = useState(true);
  const [showRemote, setShowRemote] = useState(true);

  const allTargetIds = new Set(inputs.flatMap(i => i.bindings.map(b => b.targetId)));

  const freeLocalInputs = inputs.filter(i => i.type === 'local' && i.bindings.length === 0);
  const freeLocalOutputs = outputs.filter(o => o.type === 'output' && !allTargetIds.has(o.id));
  const freeLocalCovers = outputs.filter(o => o.type === 'cover' && !allTargetIds.has(o.id));

  const freeRemoteInputs = inputs.filter(i => i.type === 'remote' && i.bindings.length === 0);
  const freeRemoteOutputs = outputs.filter(o => (o.type === 'remote_output' || o.type === 'remote_cover') && !allTargetIds.has(o.id));

  const hasLocalFree = freeLocalInputs.length > 0 || freeLocalOutputs.length > 0 || freeLocalCovers.length > 0;
  const hasRemoteFree = freeRemoteInputs.length > 0 || freeRemoteOutputs.length > 0;

  if (!hasLocalFree && !hasRemoteFree) return null;

  return (
    <div className="mt-4 space-y-3">
      {/* Local unconfigured */}
      {hasLocalFree && (
        <div className="border border-warning/20 rounded-xl bg-warning/5 overflow-hidden">
          <button
            className="w-full p-3 flex items-center justify-between text-sm font-semibold text-warning hover:bg-warning/10 transition-colors"
            onClick={() => setShowLocal(!showLocal)}
          >
            <span className="flex items-center gap-2">
              <FaExclamationTriangle className="w-3.5 h-3.5" />
              {t('binding_matrix.unconfigured_local')}
            </span>
            {showLocal ? <FaChevronUp className="w-3 h-3" /> : <FaChevronDown className="w-3 h-3" />}
          </button>
          {showLocal && (
            <div className="p-3 pt-0 space-y-2">
              {freeLocalInputs.length > 0 && (
                <FreeItemList
                  title={`📥 ${t('binding_matrix.free_inputs')} (${freeLocalInputs.length})`}
                  items={freeLocalInputs.map(i => ({ id: i.id, name: i.name, area: i.area }))}
                />
              )}
              {freeLocalOutputs.length > 0 && (
                <FreeItemList
                  title={`💡 ${t('binding_matrix.free_outputs')} (${freeLocalOutputs.length})`}
                  items={freeLocalOutputs.map(o => ({ id: o.id, name: o.name, area: o.area }))}
                />
              )}
              {freeLocalCovers.length > 0 && (
                <FreeItemList
                  title={`🚪 ${t('binding_matrix.free_covers')} (${freeLocalCovers.length})`}
                  items={freeLocalCovers.map(o => ({ id: o.id, name: o.name, area: o.area }))}
                />
              )}
            </div>
          )}
        </div>
      )}

      {/* Remote unconfigured */}
      {hasRemoteFree && (
        <div className="border border-info/20 rounded-xl bg-info/5 overflow-hidden">
          <button
            className="w-full p-3 flex items-center justify-between text-sm font-semibold text-info hover:bg-info/10 transition-colors"
            onClick={() => setShowRemote(!showRemote)}
          >
            <span className="flex items-center gap-2">
              <FaExclamationTriangle className="w-3.5 h-3.5" />
              {t('binding_matrix.unconfigured_remote')}
            </span>
            {showRemote ? <FaChevronUp className="w-3 h-3" /> : <FaChevronDown className="w-3 h-3" />}
          </button>
          {showRemote && (
            <div className="p-3 pt-0 space-y-2">
              {freeRemoteInputs.length > 0 && (
                <FreeItemList
                  title={`📥 ${t('binding_matrix.free_remote_inputs')} (${freeRemoteInputs.length})`}
                  items={freeRemoteInputs.map(i => ({ id: i.id, name: i.name, area: i.area, badge: i.remoteDevice }))}
                />
              )}
              {freeRemoteOutputs.length > 0 && (
                <FreeItemList
                  title={`📡 ${t('binding_matrix.free_remote_outputs')} (${freeRemoteOutputs.length})`}
                  items={freeRemoteOutputs.map(o => ({ id: o.id, name: o.name, area: o.area, badge: o.remoteDevice }))}
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Simple list of free (unbound) items. */
function FreeItemList({ title, items }: {
  title: string;
  items: { id: string; name: string; area?: string; badge?: string }[];
}) {
  return (
    <div>
      <p className="text-xs font-semibold text-base-content/60 mb-1">{title}</p>
      <div className="flex flex-wrap gap-1.5">
        {items.map(item => (
          <span
            key={item.id}
            className="badge badge-sm badge-ghost text-xxs font-mono gap-1"
            title={item.id}
          >
            {item.name}
            {item.area && <span className="text-base-content/40">({item.area})</span>}
            {item.badge && <span className="text-info/60">[{item.badge}]</span>}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Desktop Matrix Table
// ---------------------------------------------------------------------------

function DesktopMatrix({ inputs, outputs, areaFilter, hideEmpty, t, onEditInput }: {
  inputs: InputRow[];
  outputs: OutputColumn[];
  areaFilter: string;
  hideEmpty: boolean;
  t: (key: string, opts?: any) => string;
  onEditInput: (input: InputRow, clickType?: string) => void;
}) {
  const [hoverRow, setHoverRow] = useState<string | null>(null);
  const [hoverCol, setHoverCol] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isMouseDown = useRef(false);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const scrollStartX = useRef(0);

  // Filter by area
  const filteredInputs = useMemo(() => {
    let result = inputs;
    if (areaFilter) result = result.filter(i => i.area === areaFilter);
    if (hideEmpty) result = result.filter(i => i.bindings.length > 0);
    return result;
  }, [inputs, areaFilter, hideEmpty]);

  const allTargetIds = useMemo(() => {
    return new Set(inputs.flatMap(i => i.bindings.map(b => b.targetId)));
  }, [inputs]);

  const filteredOutputs = useMemo(() => {
    let result = outputs;
    if (areaFilter) result = result.filter(o => o.area === areaFilter || !o.area);
    if (hideEmpty) result = result.filter(o => allTargetIds.has(o.id));
    return result;
  }, [outputs, areaFilter, hideEmpty, allTargetIds]);

  // Build lookup: inputId → targetId → Binding[]
  const matrixLookup = useMemo(() => {
    const map = new Map<string, Map<string, Binding[]>>();
    for (const input of filteredInputs) {
      const targets = new Map<string, Binding[]>();
      for (const b of input.bindings) {
        const existing = targets.get(b.targetId) || [];
        existing.push(b);
        targets.set(b.targetId, existing);
      }
      map.set(input.id, targets);
    }
    return map;
  }, [filteredInputs]);

  if (filteredInputs.length === 0 || filteredOutputs.length === 0) {
    return (
      <div className="text-center py-12 text-base-content/40">
        <p className="text-sm">{t('binding_matrix.no_data')}</p>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="overflow-x-auto rounded-xl border border-base-300 cursor-grab active:cursor-grabbing"
      onMouseDown={(e) => {
        isMouseDown.current = true;
        isDragging.current = false;
        dragStartX.current = e.clientX;
        scrollStartX.current = scrollRef.current?.scrollLeft || 0;
      }}
      onMouseMove={(e) => {
        if (!isMouseDown.current || !scrollRef.current) return;
        const dx = e.clientX - dragStartX.current;
        // Only start dragging after 5px threshold to allow normal clicks
        if (!isDragging.current && Math.abs(dx) > 5) {
          isDragging.current = true;
        }
        if (isDragging.current) {
          scrollRef.current.scrollLeft = scrollStartX.current - dx;
        }
      }}
      onMouseUp={() => { isMouseDown.current = false; isDragging.current = false; }}
      onMouseLeave={() => { isMouseDown.current = false; isDragging.current = false; }}
      onClickCapture={(e) => {
        // If we were dragging, prevent the click from firing on cells
        if (isDragging.current) {
          e.stopPropagation();
          e.preventDefault();
        }
      }}
    >
      <table className="table table-xs w-auto">
        <thead>
          <tr>
            <th className="sticky left-0 z-20 bg-base-200 border-r border-base-300 min-w-[120px]" />
            {filteredOutputs.map(col => (
              <th
                key={col.id}
                className={clsx(
                  'text-center text-xxs font-bold px-1.5 py-2 min-w-[80px] max-w-[100px] border-r border-base-300 bg-base-200',
                  hoverCol === col.id && 'bg-primary/10',
                )}
                onMouseEnter={() => setHoverCol(col.id)}
                onMouseLeave={() => setHoverCol(null)}
              >
                <div className="truncate" title={`${col.name}${col.area ? ` (${col.area})` : ''}`}>
                  {col.name}
                </div>
                {col.area && (
                  <div className="text-xxs font-normal text-base-content/40 truncate">{col.area}</div>
                )}
                {col.remoteDevice && (
                  <div className="text-xxs font-normal text-info/50 truncate">{col.remoteDevice}</div>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filteredInputs.map(row => {
            const targetMap = matrixLookup.get(row.id);
            return (
              <tr
                key={row.id}
                className={clsx(
                  'hover:bg-base-200/50',
                  hoverRow === row.id && 'bg-base-200/40',
                )}
                onMouseEnter={() => setHoverRow(row.id)}
                onMouseLeave={() => setHoverRow(null)}
              >
                <td
                  className={clsx(
                    'sticky left-0 z-10 bg-base-100 border-r border-base-300 font-medium text-xs cursor-pointer group/row',
                    hoverRow === row.id && 'bg-base-200/60',
                    row.bindings.length === 0 && 'text-base-content/30',
                  )}
                  onClick={() => onEditInput(row)}
                  title={t('binding_matrix.click_to_edit')}
                >
                  <div className="font-bold truncate max-w-[120px] flex items-center gap-1" title={row.id}>
                    {row.name}
                    <FaPen className="w-2.5 h-2.5 opacity-0 group-hover/row:opacity-40 transition-opacity shrink-0" />
                  </div>
                  {row.area && <div className="text-xxs text-base-content/40">{row.area}</div>}
                  {row.remoteDevice && <div className="text-xxs text-info/50">{row.remoteDevice}</div>}
                </td>
                {filteredOutputs.map(col => {
                  const cellBindings = targetMap?.get(col.id) || [];
                  const isHighlighted = hoverRow === row.id || hoverCol === col.id;
                  return (
                    <td
                      key={col.id}
                      className={clsx(
                        'text-center text-xxs border-r border-base-300 px-1 py-1',
                        cellBindings.length > 0
                          ? 'bg-success/15 text-success-content font-medium cursor-pointer hover:bg-success/30'
                          : 'text-base-content/10',
                        isHighlighted && cellBindings.length > 0 && 'bg-success/25',
                        isHighlighted && cellBindings.length === 0 && 'bg-base-200/40',
                      )}
                      title={cellBindings.length > 0 ? `${cellBindings.map(bindingTooltip).join('\n')}\n\n${t('binding_matrix.click_to_edit')}` : undefined}
                      onMouseEnter={() => setHoverCol(col.id)}
                      onMouseLeave={() => setHoverCol(null)}
                      onClick={cellBindings.length > 0 ? () => onEditInput(row, cellBindings[0].clickType) : undefined}
                    >
                      {cellBindings.length > 0 && (
                        <div className="flex flex-col gap-0.5">
                          {cellBindings.map((b, i) => (
                            <span key={i} className="whitespace-nowrap">{bindingLabel(b)}</span>
                          ))}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mobile Accordion
// ---------------------------------------------------------------------------

function MobileAccordion({ inputs, areaFilter, hideEmpty, t, onEditInput }: {
  inputs: InputRow[];
  areaFilter: string;
  hideEmpty: boolean;
  t: (key: string, opts?: any) => string;
  onEditInput: (input: InputRow, clickType?: string) => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filteredInputs = useMemo(() => {
    let result = inputs;
    if (areaFilter) result = result.filter(i => i.area === areaFilter);
    if (hideEmpty) result = result.filter(i => i.bindings.length > 0);
    return result;
  }, [inputs, areaFilter, hideEmpty]);

  const toggleExpand = useCallback((id: string) => {
    setExpandedId(prev => prev === id ? null : id);
  }, []);

  if (filteredInputs.length === 0) {
    return (
      <div className="text-center py-12 text-base-content/40">
        <p className="text-sm">{t('binding_matrix.no_data')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {filteredInputs.map(input => {
        const isExpanded = expandedId === input.id;
        const hasBind = input.bindings.length > 0;

        // Group bindings by target
        const groupedByTarget = new Map<string, Binding[]>();
        for (const b of input.bindings) {
          const existing = groupedByTarget.get(b.targetId) || [];
          existing.push(b);
          groupedByTarget.set(b.targetId, existing);
        }

        return (
          <div
            key={input.id}
            className={clsx(
              'rounded-xl border overflow-hidden transition-colors',
              hasBind ? 'border-success/20 bg-success/5' : 'border-base-300 bg-base-200/30',
            )}
          >
            <button
              className="w-full p-3 flex items-center justify-between text-sm hover:bg-base-200/30 transition-colors"
              onClick={() => hasBind && toggleExpand(input.id)}
              disabled={!hasBind}
            >
              <div className="flex items-center gap-2 min-w-0">
                {hasBind ? (
                  <FaCheckCircle className="w-3.5 h-3.5 text-success shrink-0" />
                ) : (
                  <FaTimesCircle className="w-3.5 h-3.5 text-base-content/20 shrink-0" />
                )}
                <div className="min-w-0 text-left">
                  <span className={clsx(
                    'font-semibold truncate block',
                    !hasBind && 'text-base-content/30',
                  )}>
                    {input.name}
                  </span>
                  {input.area && (
                    <span className="text-xxs text-base-content/40">{input.area}</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {hasBind && (
                  <span className="badge badge-sm badge-success font-bold">{input.bindings.length}</span>
                )}
                {input.type === 'remote' && (
                  <span className="badge badge-xs badge-info font-mono">{input.remoteDevice}</span>
                )}
                {hasBind && (isExpanded ? <FaChevronUp className="w-3 h-3 text-base-content/30" /> : <FaChevronDown className="w-3 h-3 text-base-content/30" />)}
              </div>
            </button>

            {isExpanded && hasBind && (
              <div className="border-t border-base-300 p-3 space-y-2 bg-base-100/50">
                {[...groupedByTarget.entries()].map(([targetId, bindings]) => (
                  <div key={targetId} className="flex items-start gap-2 text-xs">
                    <span className="font-mono font-bold text-base-content/70 shrink-0 mt-0.5">→</span>
                    <div>
                      <span className="font-semibold">{targetId}</span>
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {bindings.map((b, i) => (
                          <span key={i} className="badge badge-xs badge-success font-mono gap-0.5">
                            {bindingLabel(b)}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
                {/* Edit button */}
                <button
                  className="btn btn-xs btn-primary btn-outline gap-1 mt-1"
                  onClick={(e) => { e.stopPropagation(); onEditInput(input); }}
                >
                  <FaPen className="w-2.5 h-2.5" />
                  {t('binding_matrix.edit_input')}
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

/**
 * BindingMatrix — read-only view of all input→output/cover bindings.
 * Desktop: full matrix table. Mobile: accordion list.
 */
const BindingMatrix: React.FC<BindingMatrixProps> = ({ formData, sections, onSaveSection, onUpdateFormData }) => {
  const { t } = useTranslation();
  const [areaFilter, setAreaFilter] = useState('');
  const [hideEmpty, setHideEmpty] = useState(false);

  // Inline edit dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [editingSection, setEditingSection] = useState<string>('');
  const [editingIndex, setEditingIndex] = useState<number>(-1);
  const [editingInitialTab, setEditingInitialTab] = useState<'basic' | 'single' | 'double' | 'triple' | 'long' | 'sequences' | 'advanced'>('basic');
  const [hasValidationErrors, setHasValidationErrors] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const originalItemRef = useRef<string | null>(null);

  /** Open inline edit dialog for an input, optionally on a specific tab. */
  const handleEditInput = useCallback((input: InputRow, clickType?: string) => {
    // Find the raw item in formData
    const section = input.type === 'remote' ? 'remote_inputs' : 'local_inputs';
    const items: any[] = formData[section] || [];
    const idx = items.findIndex((item: any) => {
      const itemId = item.id || item.pin || '';
      return itemId === input.id || item.name === input.id;
    });
    if (idx < 0) return;

    setEditingSection(section);
    setEditingIndex(idx);
    setEditingItem(JSON.parse(JSON.stringify(items[idx])));
    originalItemRef.current = JSON.stringify(items[idx]);
    setEditingInitialTab(clickType ? (CLICK_TYPE_TO_TAB[clickType] || 'basic') : 'basic');
    setHasValidationErrors(false);
    setEditDialogOpen(true);
  }, [formData]);

  /** Save the edited input and persist via API. */
  const handleSaveEdit = useCallback(async () => {
    if (hasValidationErrors || editingIndex < 0 || !editingItem) return;

    const items = [...(formData[editingSection] || [])];
    items[editingIndex] = editingItem;

    setIsSaving(true);
    try {
      // Update formData first, then save
      onUpdateFormData(editingSection, items);
      await onSaveSection(editingSection, items);
      setEditDialogOpen(false);
      setEditingItem(null);
    } catch (err) {
      console.error('Failed to save input:', err);
    } finally {
      setIsSaving(false);
    }
  }, [editingItem, editingIndex, editingSection, formData, hasValidationErrors, onSaveSection, onUpdateFormData]);

  const handleCancelEdit = useCallback(() => {
    setEditDialogOpen(false);
    setEditingItem(null);
  }, []);

  const inputs = useMemo(() => extractInputs(formData), [formData]);
  const outputs = useMemo(() => extractOutputs(formData), [formData]);

  // Unique areas from all entities
  const allAreas = useMemo(() => {
    const areas = new Set<string>();
    inputs.forEach(i => { if (i.area) areas.add(i.area); });
    outputs.forEach(o => { if (o.area) areas.add(o.area); });
    return [...areas].sort();
  }, [inputs, outputs]);

  // Collect data needed by EventForm
  const allOutputs = useMemo(() => formData.output || [], [formData.output]);
  const allCovers = useMemo(() => formData.cover || [], [formData.cover]);
  const allOutputGroups = useMemo(() => formData.output_group || [], [formData.output_group]);
  const allRemoteDevices = useMemo(() => formData.remote_devices || [], [formData.remote_devices]);
  const allBinarySensors = useMemo(() => {
    return (formData.local_inputs || []).filter((i: any) => i._inputType === 'binary_sensor');
  }, [formData.local_inputs]);
  const allEvents = useMemo(() => {
    return (formData.local_inputs || []).filter((i: any) => i._inputType !== 'binary_sensor');
  }, [formData.local_inputs]);
  const allAreasData = useMemo(() => formData.areas || [], [formData.areas]);

  // Get the event/binary_sensor schema for EventForm
  const eventSchema = useMemo(() => {
    const localInputsSection = sections.find(s => s.name === 'local_inputs');
    return localInputsSection?.schema || localInputsSection?.normalizedSchema || {};
  }, [sections]);

  const isDirty = editingItem && originalItemRef.current && JSON.stringify(editingItem) !== originalItemRef.current;

  return (
    <div className="p-4 md:p-6 max-w-full">
      {/* Header */}
      <div className="mb-4">
        <h2 className="text-xl font-extrabold tracking-tight">{t('binding_matrix.title')}</h2>
        <p className="text-sm text-base-content/50">{t('binding_matrix.subtitle')}</p>
      </div>

      {/* Statistics */}
      <StatsBanner inputs={inputs} outputs={outputs} t={t} />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4 items-center">
        <div className="flex items-center gap-2">
          <FaFilter className="w-3 h-3 text-base-content/40" />
          <select
            className="select select-sm select-bordered"
            value={areaFilter}
            onChange={e => setAreaFilter(e.target.value)}
          >
            <option value="">{t('binding_matrix.all_areas')}</option>
            {allAreas.map(area => (
              <option key={area} value={area}>{area}</option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            className="checkbox checkbox-sm checkbox-primary"
            checked={hideEmpty}
            onChange={e => setHideEmpty(e.target.checked)}
          />
          <span className="text-xs font-medium text-base-content/60 flex items-center gap-1">
            {hideEmpty ? <FaEyeSlash className="w-3 h-3" /> : <FaEye className="w-3 h-3" />}
            {t('binding_matrix.hide_empty')}
          </span>
        </label>
      </div>

      {/* Desktop: Matrix table */}
      <div className="hidden md:block">
        <DesktopMatrix
          inputs={inputs}
          outputs={outputs}
          areaFilter={areaFilter}
          hideEmpty={hideEmpty}
          t={t}
          onEditInput={handleEditInput}
        />
      </div>

      {/* Mobile: Accordion list */}
      <div className="md:hidden">
        <MobileAccordion
          inputs={inputs}
          areaFilter={areaFilter}
          hideEmpty={hideEmpty}
          t={t}
          onEditInput={handleEditInput}
        />
      </div>

      {/* Unconfigured items (both views) */}
      <UnconfiguredSection inputs={inputs} outputs={outputs} t={t} />

      {/* Inline Edit Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="max-w-4xl sm:max-w-3xl lg:w-[120vw] max-h-[85vh] flex flex-col gap-0 bg-base-100">
          <DialogHeader>
            <DialogTitle>
              {t('binding_matrix.edit_input')}
              {editingItem && (
                <span className="font-normal text-base-content/70">
                  {' — '}{editingItem.name || editingItem.id || ''}
                </span>
              )}
            </DialogTitle>
            <DialogDescription className="sr-only">
              {t('binding_matrix.edit_input')}
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto overflow-x-hidden -mx-6 px-6">
            {editingItem && (
              <EventForm
                data={editingItem}
                onChange={setEditingItem}
                onSave={handleSaveEdit}
                onCancel={handleCancelEdit}
                isNew={false}
                schema={eventSchema}
                allBinarySensors={allBinarySensors}
                allEvents={allEvents}
                allOutputs={allOutputs}
                allOutputGroups={allOutputGroups}
                allCovers={allCovers}
                allAreas={allAreasData}
                allRemoteDevices={allRemoteDevices}
                editingIndex={editingIndex}
                onValidationChange={setHasValidationErrors}
                attemptedSubmit={false}
                savedOutputs={allOutputs}
                savedOutputGroups={allOutputGroups}
                savedCovers={allCovers}
                initialTab={editingInitialTab}
              />
            )}
          </div>

          <DialogFooter className="shrink-0 mt-2">
            <button type="button" onClick={handleCancelEdit} className="btn btn-ghost">
              {t('common.cancel')}
            </button>
            <button
              type="button"
              onClick={handleSaveEdit}
              className="btn btn-primary"
              disabled={hasValidationErrors || !isDirty || isSaving}
            >
              {isSaving ? (
                <><span className="loading loading-spinner loading-xs" /> {t('settings.saving')}</>
              ) : (
                t('settings.save_changes')
              )}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default BindingMatrix;
