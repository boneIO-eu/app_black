import React from 'react';
import axios from '@/api/axios';
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
import type { JsonSchema } from '@/types/jsonSchema';
import type { OutputGroupRecord } from './ActionFields/types';
import { applyAiConfigResponse, buildAiConfigPrompt, type AiEntityType } from './helpers/aiConfig';
import AiAssistantShell from './AiAssistantShell';

type SupportedEntity = EventEntity | BinarySensorEntity;

interface AiConfigAssistantProps<T extends SupportedEntity> {
  entityType: AiEntityType;
  /** The config section the entity is saved in; defaults to entityType. */
  section?: string;
  data: T;
  schema?: JsonSchema;
  allOutputs?: OutputEntity[];
  allOutputGroups?: OutputGroupRecord[];
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
/**
 * What the controller would refuse in a section holding just this entity.
 *
 * The controller knows what actually exists — outputs, groups, covers, remote
 * devices — and checks it the way a save will. Errors come back without the
 * section prefix, as "actions.single[0].boneio_output: …". If the controller
 * cannot be asked, nothing is refused here: the save checks the same again.
 */
async function controllerErrors(section: string, entity: unknown): Promise<string[]> {
  try {
    const resp = await axios.post(`/api/config/${section}/validate`, [entity]);
    const errors: unknown = resp.data?.errors;
    return Array.isArray(errors)
      ? errors.map((e) => String(e).replace(`${section}[0].`, '').replace(`${section}[0]: `, ''))
      : [];
  } catch (err) {
    console.warn('Could not validate the AI response on the controller:', err);
    return [];
  }
}

export default function AiConfigAssistant<T extends SupportedEntity>({
  entityType,
  section,
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
  const handleApply = async (responseText: string): Promise<string[]> => {
    const result = applyAiConfigResponse({
      entityType,
      data,
      responseText,
      schema,
      actionTypeOptions,
      actionOutputOptions,
      actionCoverOptions,
      t,
    });

    if (result.errors.length > 0 || !result.data) {
      return result.errors;
    }

    const refused = await controllerErrors(section ?? entityType, result.data);
    if (refused.length > 0) {
      return refused;
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
