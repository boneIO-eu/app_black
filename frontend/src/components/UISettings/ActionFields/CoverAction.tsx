import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { normalizeCovers } from '../helpers/coverUtils';
import type { CoverActionProps } from './types';

/**
 * Cover Action component - handles local boneIO covers.
 */
const CoverAction: React.FC<CoverActionProps> = ({
  action,
  onUpdate,
  t,
  allCovers,
  actionCoverOptions,
  isCoverSaved,
}) => {
  // Wrapper for onUpdate that removes deprecated 'pin' field
  const handleUpdate = (field: string, value: any) => {
    if (action.pin) {
      onUpdate('pin', undefined);
    }
    onUpdate(field, value);
  };

  return (
    <>
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.cover')}</span>
        </label>
        <Select
          value={action.boneio_cover || action.pin || ''}
          onValueChange={(value) => handleUpdate('boneio_cover', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('event_form.select_cover')} />
          </SelectTrigger>
          <SelectContent>
            {normalizeCovers(allCovers).map((cover) => {
              const name = cover.name || cover.id;
              const label = name !== cover.id ? `${name} (${cover.id})` : cover.id;
              const isSaved = isCoverSaved(cover.id);
              return (
                <SelectItem 
                  key={cover.id} 
                  value={cover.id}
                  disabled={!isSaved}
                  className={!isSaved ? 'opacity-50 cursor-not-allowed' : ''}
                >
                  {!isSaved && <span className="badge badge-xs badge-warning mr-1">Niezapisane</span>}
                  {label}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </div>

      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.cover_action')}</span>
        </label>
        <Select
          value={action.action_cover || 'TOGGLE'}
          onValueChange={(value) => onUpdate('action_cover', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select action..." />
          </SelectTrigger>
          <SelectContent>
            {actionCoverOptions.map((option: string) => (
              <SelectItem key={option} value={option}>
                {option.split('_').map(word => 
                  word.charAt(0) + word.slice(1).toLowerCase()
                ).join(' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </>
  );
};

export default CoverAction;
