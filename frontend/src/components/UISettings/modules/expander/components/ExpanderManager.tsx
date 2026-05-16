/**
 * Expansion board management UI — Presentational layer.
 *
 * All state, fetch, and side-effects live in `useExpanderManager`. This component
 * only renders. Swap it for an alternative skin without touching logic.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';

import {
  useExpanderManager,
  EXPANDER_BOARDS,
  type UseExpanderManagerArgs,
} from '../hooks/useExpanderManager';
import { MCP_ADDRESS_OPTIONS } from '../constants/mcpAddresses';
import type { McpAddress } from '../types/mcp';

const ExpanderManager: React.FC<UseExpanderManagerArgs> = (args) => {
  const { t } = useTranslation();
  const m = useExpanderManager(args);

  const slots = EXPANDER_BOARDS[m.boardType].outputs;
  const previewText = t('mcp.expander_outputs_preview')
    .replace('{count}', String(slots.length))
    .replace('{first}', slots[0]?.slotId ?? '')
    .replace('{last}', slots[slots.length - 1]?.slotId ?? '');

  return (
    <>
      {/* Restart overlay (during expander add/remove) */}
      {m.isBusy && m.result?.status === 'success' && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body items-center text-center">
              <span className="loading loading-spinner loading-lg text-primary" />
              <p className="font-medium">{t('settings.restarting')}</p>
              <p className="text-sm text-base-content/60">{t('boneio_config.expander_saved')}</p>
            </div>
          </div>
        </div>
      )}

      <div className="divider text-sm">{t('boneio_config.expander_section')}</div>
      <div className="space-y-3">
        {m.result && (
          <div className={`alert py-2 text-sm ${m.result.status === 'success' ? 'alert-success' : 'alert-error'}`}>
            {m.result.status === 'success'
              ? t('boneio_config.expander_saved')
              : m.result.message}
          </div>
        )}

        {m.blockingInputs.length > 0 && (
          <div className="alert alert-error py-2">
            <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-5 w-5" fill="none" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <p className="font-medium text-sm">{t('mcp.expander_remove_blocked')}</p>
              <ul className="text-xs mt-1 list-disc list-inside">
                {m.blockingInputs.map((name) => <li key={name}>{name}</li>)}
              </ul>
            </div>
            <button className="btn btn-xs btn-ghost" onClick={m.dismissBlocking}>✕</button>
          </div>
        )}

        {m.hasExpander ? (
          <div className="flex items-center gap-3 flex-wrap">
            <span className="badge badge-success">{t('boneio_config.expander_active')}</span>
            {m.detectedBoardType && (
              <span className="badge badge-outline">{EXPANDER_BOARDS[m.detectedBoardType].label}</span>
            )}
            <span className="text-sm text-base-content/60">
              {m.exOutputs.length} {t('mcp.expander_outputs_active')}
            </span>
            <div className="ml-auto">
              {!m.isRemoveConfirmOpen ? (
                <button
                  className="btn btn-error btn-outline btn-sm"
                  onClick={m.openRemoveConfirm}
                  disabled={m.isBusy}
                >
                  {t('boneio_config.expander_remove')}
                </button>
              ) : (
                <div className="flex gap-2 items-center">
                  <span className="text-sm text-warning">{t('boneio_config.expander_remove_confirm')}</span>
                  <button className="btn btn-ghost btn-xs" onClick={m.closeRemoveConfirm}>{t('common.cancel')}</button>
                  <button className="btn btn-error btn-xs" onClick={m.submitRemove} disabled={m.isBusy}>
                    {m.isBusy && <span className="loading loading-spinner loading-xs" />}
                    {t('boneio_config.expander_remove')}
                  </button>
                </div>
              )}
            </div>
          </div>
        ) : !m.isAddOpen ? (
          <button className="btn btn-primary btn-sm" onClick={m.openAdd}>
            + {t('boneio_config.expander_add')}
          </button>
        ) : (
          <div className="card bg-base-200 shadow-sm">
            <div className="card-body py-4 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="form-control">
                  <label className="label py-1">
                    <span className="label-text font-medium">{t('mcp.expander_board_type')}</span>
                  </label>
                  <select
                    className="select select-bordered select-sm"
                    value={m.boardType}
                    onChange={(e) => m.setBoardType(e.target.value as typeof m.boardType)}
                  >
                    {(Object.keys(EXPANDER_BOARDS) as Array<keyof typeof EXPANDER_BOARDS>).map((bt) => (
                      <option key={bt} value={bt}>{EXPANDER_BOARDS[bt].label}</option>
                    ))}
                  </select>
                </div>
                {(['expander_left', 'expander_right'] as const).map((id) => (
                  <div key={id} className="form-control">
                    <label className="label py-1">
                      <span className="label-text font-medium font-mono text-sm">{id}</span>
                    </label>
                    <select
                      className="select select-bordered select-sm"
                      value={m.addresses[id]}
                      onChange={(e) => m.setAddress(id, e.target.value as McpAddress)}
                    >
                      {MCP_ADDRESS_OPTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              <div className="text-xs text-base-content/50">{previewText}</div>
              <div className="flex gap-2">
                <button className="btn btn-primary btn-sm" onClick={m.submitAdd} disabled={m.isBusy}>
                  {m.isBusy && <span className="loading loading-spinner loading-xs" />}
                  {t('boneio_config.expander_add')}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={m.closeAdd}>{t('common.cancel')}</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export default ExpanderManager;
