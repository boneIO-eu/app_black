import { useEffect, useState } from 'react';
import axios from '@/api/axios';
import { NumericInput } from '@/components/ui/NumericInput';
import { useTranslation } from '@/hooks/useTranslation';
import SettingsToggleGroup from './widgets/SettingsToggleGroup';
import { FormField, NoticeCallout } from './ui';
import type { ConfigRecord } from '@/types/jsonSchema';

interface Props {
  data: ConfigRecord | undefined;
  onChange: (data: ConfigRecord) => void;
}

/**
 * The opt-in for usage history: hourly counts an AI suggests automations from.
 *
 * It says plainly what it costs - a record of when somebody is at home, read
 * by an AI vendor - because that is the decision being made here. The day
 * count comes from the controller, so it shows what is actually held.
 */
export default function UsageHistoryForm({ data, onChange }: Props) {
  const { t } = useTranslation();
  const enabled = data?.enabled === true;
  const days = typeof data?.days === 'number' ? data.days : 30;
  const [collected, setCollected] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    axios
      .get('/api/usage-summary', { params: { days: 90 } })
      .then(({ data: summary }) => alive && setCollected(summary.enabled ? summary.days : null))
      .catch(() => alive && setCollected(null));
    return () => {
      alive = false;
    };
  }, [enabled]);

  return (
    <div className="space-y-4">
      <p className="text-sm text-base-content/70">{t('usage_history.intro')}</p>
      <NoticeCallout variant="warning" message={t('usage_history.privacy')} />
      <SettingsToggleGroup
        items={[
          {
            key: 'enabled',
            label: t('usage_history.enabled'),
            description: t('usage_history.enabled_hint'),
            checked: enabled,
            onChange: (checked) => onChange({ ...data, enabled: checked, days }),
          },
        ]}
      />
      {enabled && (
        <FormField label={t('usage_history.days')} help={t('usage_history.days_hint')}>
          <NumericInput
            value={days}
            min={7}
            max={90}
            onChange={(v) => onChange({ ...data, enabled, days: v === '' ? 30 : v })}
            className="w-28"
          />
        </FormField>
      )}
      {enabled && collected !== null && (
        <p className="text-sm text-base-content/70">{t('usage_history.collected', { days: collected })}</p>
      )}
    </div>
  );
}
