import React from 'react';
import { FaCopy, FaMagic } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import type {
  AreaEntity,
  BinarySensorEntity,
  CoverEntity,
  EventEntity,
  OutputEntity,
  RemoteDeviceEntity,
} from '@/types/config';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { applyAiConfigResponse, buildAiConfigPrompt, type AiEntityType } from './helpers/aiConfig';

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
  const [isDialogOpen, setIsDialogOpen] = React.useState(false);
  const [responseText, setResponseText] = React.useState('');
  const [errors, setErrors] = React.useState<string[]>([]);
  const [copied, setCopied] = React.useState(false);
  const [status, setStatus] = React.useState<{ type: 'success' | 'error'; message: string } | null>(null);

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
  const handleCopyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setStatus({ type: 'success', message: t('event_form.ai_prompt_copied') });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setStatus({ type: 'error', message: t('event_form.ai_copy_failed') });
    }
  };

  /**
   * Validates the pasted AI response and applies it to the current form.
   */
  const handleApplyResponse = () => {
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
      setErrors(result.errors);
      setStatus({ type: 'error', message: t('event_form.ai_apply_failed') });
      return;
    }

    onApply(result.data);
    setErrors([]);
    setResponseText('');
    setIsDialogOpen(false);
    setStatus({ type: 'success', message: t('event_form.ai_apply_success') });
  };

  return (
    <>
      <div className="rounded-lg border border-base-300 bg-base-200/60 p-3 space-y-2">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <div className="font-medium flex items-center gap-2">
              <FaMagic className="text-primary" />
              {t('event_form.ai_assistant_title')}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-outline btn-sm" onClick={handleCopyPrompt}>
              <FaCopy className="mr-2" />
              {copied ? t('event_form.ai_prompt_copied_short') : t('event_form.ai_copy_prompt')}
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => setIsDialogOpen(true)}>
              <FaMagic className="mr-2" />
              {t('event_form.ai_paste_response')}
            </button>
          </div>
        </div>

        <div className="collapse collapse-arrow bg-base-100/60 rounded-lg border border-base-300/50">
          <input type="checkbox" />
          <div className="collapse-title min-h-0 py-2 px-3 text-sm font-medium">
            {t('common.details')}
          </div>
          <div className="collapse-content px-3 pb-3 text-xs opacity-70 space-y-2">
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
          </div>
        </div>

        {status && (
          <div className={`alert ${status.type === 'success' ? 'alert-success' : 'alert-error'} py-2`}>
            <span className="text-sm">{status.message}</span>
          </div>
        )}
      </div>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-2xl bg-base-100">
          <DialogHeader>
            <DialogTitle>{t('event_form.ai_dialog_title')}</DialogTitle>
            <DialogDescription>{t('event_form.ai_dialog_description')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <textarea
              className="textarea textarea-bordered min-h-64 w-full font-mono text-sm"
              value={responseText}
              onChange={(event) => setResponseText(event.target.value)}
              placeholder={t('event_form.ai_response_placeholder')}
            />

            {errors.length > 0 && (
              <div className="alert alert-error">
                <div>
                  <div className="font-medium">{t('event_form.ai_validation_failed')}</div>
                  <ul className="mt-2 list-disc list-inside text-sm space-y-1">
                    {errors.map((error, index) => (
                      <li key={`${error}-${index}`}>{error}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setErrors([]);
                setIsDialogOpen(false);
              }}
            >
              {t('common.cancel')}
            </button>
            <button type="button" className="btn btn-primary" onClick={handleApplyResponse}>
              {t('event_form.ai_apply_response')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
