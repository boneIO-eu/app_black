import React, { useMemo } from 'react';
import { NumericInput } from '@/components/ui/NumericInput';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { normalizeCovers } from '../helpers/coverUtils';
import SearchableEntityPicker from '../SearchableEntityPicker';
import type { EntityItem } from '../EntitySelectDropdown';
import type { CoverActionProps } from './types';
import { formatActionLabel } from './helpers';

/** Tilt-related cover actions that only apply to venetian covers. */
const TILT_ACTIONS = ['TILT', 'TILT_OPEN', 'TILT_CLOSE'];

/**
 * Cover Action component - handles local boneIO covers.
 * Uses SearchableEntityPicker for cover selection with search and area grouping.
 * Filters tilt-related actions based on the selected cover's platform.
 */
const CoverAction: React.FC<CoverActionProps> = ({
  action,
  onUpdate,
  t,
  allCovers,
  allAreas,
  actionCoverOptions,
  isCoverSaved,
  preferredArea,
}) => {
  // Wrapper for onUpdate that removes deprecated 'pin' field
  const handleUpdate = (field: string, value: any) => {
    if (action.pin) {
      onUpdate('pin', undefined);
    }
    onUpdate(field, value);
  };

  /** Get short label for cover platform. */
  const getCoverPlatformBadge = (platform?: string): string | undefined => {
    if (platform === 'venetian') return t('covers.type_venetian');
    if (platform === 'time_based') return t('covers.type_time_based');
    return t('covers.type_time_based'); // default
  };

  /** Convert covers into EntityItem[] for the dropdown. */
  const coverItems: EntityItem[] = useMemo(() => {
    return normalizeCovers(allCovers).map((cover): EntityItem => {
      const saved = isCoverSaved(cover.id);
      return {
        id: cover.id,
        name: cover.name || cover.id,
        area: cover.area,
        badge: getCoverPlatformBadge(cover.platform),
        badgeClass: cover.platform === 'venetian' ? 'badge-accent' : 'badge-info',
        disabled: !saved,
        disabledLabel: !saved ? t('common.unsaved') : undefined,
      };
    });
  }, [allCovers, isCoverSaved]);

  /** Find the selected cover to determine its platform. */
  const selectedCoverId = action.boneio_cover || action.pin || '';
  const selectedCover = useMemo(() => {
    return normalizeCovers(allCovers).find(c => c.id === selectedCoverId);
  }, [allCovers, selectedCoverId]);

  const isVenetian = selectedCover?.platform === 'venetian';

  /** Filter action options: show tilt actions only for venetian covers. */
  const filteredCoverOptions = useMemo(() => {
    if (isVenetian) return actionCoverOptions;
    return actionCoverOptions.filter(opt => !TILT_ACTIONS.includes(opt));
  }, [actionCoverOptions, isVenetian]);

  return (
    <>
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.cover')}</span>
        </label>
        <SearchableEntityPicker
          value={selectedCoverId}
          onChange={(value: string) => {
            handleUpdate('boneio_cover', value);
            // If switching from venetian to non-venetian, clear tilt action
            const newCover = normalizeCovers(allCovers).find(c => c.id === value);
            if (newCover?.platform !== 'venetian' && TILT_ACTIONS.includes(action.action_cover)) {
              onUpdate('action_cover', 'TOGGLE');
              onUpdate('data', undefined);
            }
          }}
          items={coverItems}
          allAreas={allAreas}
          placeholder={t('event_form.select_cover')}
          recentKey="covers"
          preferredArea={preferredArea}
        />
      </div>

      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.cover_action')}</span>
        </label>
        <Select
          value={action.action_cover || 'TOGGLE'}
          onValueChange={(value) => {
            onUpdate('action_cover', value);
            // Clear tilt_position data when switching away from TILT
            if (value !== 'TILT') {
              const currentData = action.data || {};
              if (currentData.tilt_position !== undefined) {
                const { tilt_position, ...rest } = currentData;
                onUpdate('data', Object.keys(rest).length > 0 ? rest : undefined);
              }
            }
          }}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select action..." />
          </SelectTrigger>
          <SelectContent>
            {filteredCoverOptions.map((option: string) => (
              <SelectItem key={option} value={option}>
                {formatActionLabel(option, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Tilt position input — required for TILT action */}
      {action.action_cover === 'TILT' && (
        <div className="form-control mb-3">
          <label className="label">
            <span className="label-text font-medium">{t('event_form.tilt_position')} <span className="text-error">*</span></span>
          </label>
          <NumericInput
            className={(action.data?.tilt_position === undefined || action.data?.tilt_position === null || action.data?.tilt_position === '') ? 'input-error' : ''}
            min={0}
            max={100}
            placeholder="50"
            value={action.data?.tilt_position ?? ''}
            onChange={(v) => {
              const data = { ...(action.data || {}), tilt_position: v === '' ? undefined : v };
              onUpdate('data', data);
            }}
          />
          <label className="label">
            <span className="label-text-alt">{t('event_form.tilt_position_hint')}</span>
          </label>
        </div>
      )}

      {action.action_cover === 'SMART_TOGGLE' && (
        <div className="form-control mb-3">
          <label className="label">
            <span className="label-text font-medium">{t('event_form.always_open_till')}</span>
          </label>
          <NumericInput
            min={0}
            max={100}
            placeholder="50"
            value={action.data?.always_open_till ?? 50}
            onChange={(v) => {
              const data = { ...(action.data || {}), always_open_till: v === '' ? 50 : v };
              onUpdate('data', data);
            }}
          />
          <label className="label">
            <span className="label-text-alt">{t('event_form.always_open_till_hint')}</span>
          </label>
        </div>
      )}

      {/* Restore Tilt — only for venetian covers */}
      {isVenetian && (
        <div className="form-control mb-3">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="checkbox checkbox-sm"
              checked={action.restore_tilt || false}
              onChange={(e) => onUpdate('restore_tilt', e.target.checked || undefined)}
            />
            <div>
              <span className="label-text font-medium">{t('event_form.restore_tilt')}</span>
              <p className="text-sm text-base-content/70 mt-1">
                {t('event_form.restore_tilt_hint')}
              </p>
            </div>
          </label>
        </div>
      )}
    </>
  );
};

export default CoverAction;
