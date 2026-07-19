import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useTranslation } from '@/hooks/useTranslation';
import { copyToClipboard } from '@/utils/clipboard';
import axios from '@/api/axios';
import { FaCopy, FaCheck, FaArrowUp, FaArrowDown } from 'react-icons/fa';

/** Single MQTT publish action from the backend API. */
interface MqttPublishAction {
  action: string;
  topic: string;
  payload: string;
  description?: string;
}

/** Single MQTT subscribe topic from the backend API. */
interface MqttSubscribeTopic {
  topic: string;
  payload_format: string;
  description?: string;
}

/** Full MQTT reference response from the backend API. */
interface MqttReferenceData {
  entity_id: string;
  entity_type: string;
  entity_name: string;
  output_type: string;
  mqtt_enabled: boolean;
  publish: MqttPublishAction[];
  subscribe: MqttSubscribeTopic[];
}

interface MqttReferenceSheetProps {
  /** Whether the dialog is open. */
  open: boolean;
  /** Called when the dialog should close. */
  onOpenChange: (open: boolean) => void;
  /** Entity type (output, output_group, cover, input, remote_outputs). */
  entityType: string;
  /** Entity ID. */
  entityId: string;
  /** Entity display name (shown in header). */
  entityName?: string;
}

/** Track which field was recently copied for visual feedback. */
type CopiedKey = string | null;

/**
 * Bottom sheet / dialog displaying MQTT topics and payloads for an entity.
 *
 * Fetches structured reference data from the backend API and renders
 * publish (command) and subscribe (state) sections with copy buttons.
 *
 * Designed to be opened from the long-press dialog on entity cards.
 */
const MqttReferenceSheet: React.FC<MqttReferenceSheetProps> = ({
  open,
  onOpenChange,
  entityType,
  entityId,
  entityName,
}) => {
  const { t } = useTranslation();
  const [data, setData] = useState<MqttReferenceData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<CopiedKey>(null);

  /**
   * Translate backend description strings using i18n keys.
   * Falls back to the raw English description if no translation exists.
   */
  const translateDescription = useCallback((description?: string): string | undefined => {
    if (!description) return undefined;
    // Map known backend descriptions to i18n keys
    const key = `mqtt_reference.desc.${description
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '')}`;
    const translated = t(key);
    // If i18n returns the key itself, fallback to original
    return translated === key ? description : translated;
  }, [t]);

  // Fetch MQTT reference when dialog opens
  useEffect(() => {
    if (!open || !entityType || !entityId) return;

    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    axios
      .get<MqttReferenceData>(`/api/mqtt_reference/${entityType}/${entityId}`)
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch((err) => {
        if (!cancelled) {
          const status = err?.response?.status;
          const detail: string = err?.response?.data?.detail ?? '';
          if (status === 400 && detail.includes('cover')) {
            setError(t('mqtt_reference.belongs_to_cover'));
          } else if (status === 400) {
            setError(t('mqtt_reference.mqtt_not_configured'));
          } else if (status === 404) {
            setError(t('mqtt_reference.entity_not_found'));
          } else {
            setError(t('mqtt_reference.fetch_error'));
          }
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, entityType, entityId, t]);

  const handleCopy = useCallback(async (text: string, key: string) => {
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 1500);
    }
  }, []);

  /**
   * Render a single MQTT topic + payload row with copy buttons.
   */
  const renderTopicRow = (
    topic: string,
    payload: string,
    keyPrefix: string,
    description?: string,
  ) => (
    <div key={keyPrefix} className="bg-base-200 rounded-lg p-3 space-y-2">
      {description && (
        <p className="text-xs text-base-content/60">{description}</p>
      )}
      {/* Topic */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-base-content/50 uppercase w-14 shrink-0">
          Topic
        </span>
        <code className="text-sm font-mono bg-base-300 rounded px-2 py-1 flex-1 break-all select-all">
          {topic}
        </code>
        <button
          className="btn btn-ghost btn-xs"
          onClick={() => handleCopy(topic, `${keyPrefix}_topic`)}
          title={t('mqtt_reference.copy_topic')}
        >
          {copiedKey === `${keyPrefix}_topic` ? (
            <FaCheck className="text-success w-3 h-3" />
          ) : (
            <FaCopy className="w-3 h-3" />
          )}
        </button>
      </div>
      {/* Payload */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-base-content/50 uppercase w-14 shrink-0">
          Payload
        </span>
        <code className="text-sm font-mono bg-base-300 rounded px-2 py-1 flex-1 break-all select-all">
          {payload}
        </code>
        <button
          className="btn btn-ghost btn-xs"
          onClick={() => handleCopy(payload, `${keyPrefix}_payload`)}
          title={t('mqtt_reference.copy_payload')}
        >
          {copiedKey === `${keyPrefix}_payload` ? (
            <FaCheck className="text-success w-3 h-3" />
          ) : (
            <FaCopy className="w-3 h-3" />
          )}
        </button>
      </div>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-base-100 p-0 gap-0 sm:max-w-md">
        <DialogHeader className="px-5 pt-4 pb-2 sm:pt-5">
          <DialogTitle className="text-center flex items-center justify-center gap-2">
            📡 {t('mqtt_reference.title')}
          </DialogTitle>
          {entityName && (
            <p className="text-sm text-base-content/70 text-center font-semibold">
              {entityName}
            </p>
          )}
          <p className="text-xs text-base-content/50 text-center font-mono">
            {entityId}
          </p>
        </DialogHeader>

        <div className="px-5 pb-5 overflow-y-auto max-h-[60vh]">
          {/* Loading */}
          {loading && (
            <div className="flex justify-center py-8">
              <span className="loading loading-spinner loading-md" />
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="alert alert-error text-sm">
              {error}
            </div>
          )}

          {/* Data */}
          {data && (
            <div className="space-y-4">
              {/* Publish section */}
              {data.publish.length > 0 && (
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-semibold mb-2 text-primary">
                    <FaArrowUp className="w-3 h-3" />
                    {t('mqtt_reference.publish_section')}
                  </h3>
                  <div className="space-y-2">
                    {data.publish.map((action, i) =>
                      renderTopicRow(
                        action.topic,
                        action.payload,
                        `pub_${action.action}_${i}`,
                        translateDescription(action.description),
                      ),
                    )}
                  </div>
                </div>
              )}

              {/* Subscribe section */}
              {data.subscribe.length > 0 && (
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-semibold mb-2 text-info">
                    <FaArrowDown className="w-3 h-3" />
                    {t('mqtt_reference.subscribe_section')}
                  </h3>
                  <div className="space-y-2">
                    {data.subscribe.map((sub, i) =>
                      renderTopicRow(
                        sub.topic,
                        sub.payload_format,
                        `sub_${i}`,
                        translateDescription(sub.description),
                      ),
                    )}
                  </div>
                </div>
              )}

              {/* No publish for read-only entities */}
              {data.publish.length === 0 && (
                <div className="text-center text-sm text-base-content/50 py-2">
                  {t('mqtt_reference.read_only')}
                </div>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default MqttReferenceSheet;
