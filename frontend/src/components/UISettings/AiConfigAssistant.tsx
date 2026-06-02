import React from 'react';
import { copyToClipboard } from '@/utils/clipboard';
import { useTranslation } from '@/hooks/useTranslation';
import type {
  AreaEntity,
  BinarySensorEntity,
  CoverEntity,
  EventEntity,
  OutputEntity,
  RemoteDeviceEntity,
} from '@/types/config';
import { applyAiConfigResponse, buildAiConfigPrompt, type AiEntityType } from './helpers/aiConfig';
import AiAssistantShell from './AiAssistantShell';

type SupportedEntity = EventEntity | BinarySensorEntity;

interface AiConfigAssistantProps<T extends SupportedEntity> {
  entityType: AiEntityType;
  data: T;
  schema?: any;
  allOutputs?: OutputEntity[];
  allOutputGroups?: any[];
  allCovers?: CoverEntity[];
  allAreas?: AreaEntity[];
  allRemoteDevices?: RemoteDeviceEntity[];
  actionTypeOptions: string[];
  actionOutputOptions: string[];
  actionCoverOptions: string[];
  onApply: (data: T) => void;
}

/**
 * AI configuration assistant for Event and Binary Sensor forms.
 *
 * Wraps AiAssistantShell with domain-specific prompt building
 * and response validation/apply logic for event/binary_sensor entities.
 */
export default function AiConfigAssistant<T extends SupportedEntity>({
  entityType,
  data,
  schema,
  allOutputs = [],
  allOutputGroups = [],
  allCovers = [],
  allAreas = [],
  allRemoteDevices = [],
  actionTypeOptions,
  actionOutputOptions,
  actionCoverOptions,
  onApply,
}: AiConfigAssistantProps<T>) {
  const { t } = useTranslation();

  const prompt = React.useMemo(
    () =>
      buildAiConfigPrompt({
        entityType,
        data,
        schema,
        allOutputs,
        allOutputGroups,
        allCovers,
        allAreas,
        allRemoteDevices,
        actionTypeOptions,
        actionOutputOptions,
        actionCoverOptions,
      }),
    [
      entityType,
      data,
      schema,
      allOutputs,
      allOutputGroups,
      allCovers,
      allAreas,
      allRemoteDevices,
      actionTypeOptions,
      actionOutputOptions,
      actionCoverOptions,
    ],
  );

  /**
   * Copies the generated AI prompt with the current entity context.
   */
  const handleCopyPrompt = async (): Promise<boolean> => {
    try {
      await copyToClipboard(prompt);
      return true;
    } catch {
      return false;
    }
  };

  /**
   * Validates the pasted AI response and applies it to the current form.
   * Returns an array of error messages (empty = success).
   */
  const handleApply = (responseText: string): string[] => {
    const result = applyAiConfigResponse({
      entityType,
      data,
      responseText,
      schema,
      allOutputs,
      allOutputGroups,
      allCovers,
      allAreas,
      allRemoteDevices,
      actionTypeOptions,
      actionOutputOptions,
      actionCoverOptions,
      t,
    });

    if (result.errors.length > 0 || !result.data) {
      return result.errors;
    }

    onApply(result.data);
    return [];
  };

  return (
    <AiAssistantShell
      onCopyPrompt={handleCopyPrompt}
      onApply={handleApply}
      detailsContent={
        <>
          <p>{t('event_form.ai_assistant_description')}</p>
          <p>{t('event_form.ai_assistant_hint')}</p>
          <p>
            <a className="link link-primary" href="https://boneio.eu/docs/black" target="_blank" rel="noreferrer">
              {t('event_form.ai_docs_link')}
            </a>
            <span> · </span>
            <a className="link link-primary" href="/help" target="_blank" rel="noreferrer">
              {t('event_form.ai_webui_help_link')}
            </a>
          </p>
        </>
      }
      dialogDescription={t('event_form.ai_dialog_description')}
    />
  );
}
