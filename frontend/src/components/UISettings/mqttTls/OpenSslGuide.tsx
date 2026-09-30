import React, { useState } from 'react';
import { FaCopy, FaCheck } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { CodeBlock, MoreOptions } from '../ui';
import {
  brokerCommands,
  caCommands,
  clientCommands,
  splitNames,
  verifyCommand,
} from './openSslGuide';

interface OpenSslGuideProps {
  /**
   * `broker`: a certificate for the broker on this device, for its names.
   * `client`: a CA to trust and a client certificate for boneIO.
   */
  variant: 'broker' | 'client';
  /** Names and addresses the broker certificate has to cover. */
  addresses?: string[];
}

const Step: React.FC<{ title: string; help?: string; commands: string }> = ({ title, help, commands }) => {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(commands);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard needs a secure context; the text is still there to select.
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium">{title}</span>
        <button type="button" className="btn btn-ghost btn-xs gap-1" onClick={() => void copy()}>
          {copied ? <FaCheck /> : <FaCopy />}
          {copied ? t('mqtt_tls.guide.copied') : t('mqtt_tls.guide.copy')}
        </button>
      </div>
      {help && <p className="text-xs text-base-content/60">{help}</p>}
      <CodeBlock>{commands}</CodeBlock>
    </div>
  );
};

/**
 * How to make the certificates with openssl, on the owner's own computer.
 *
 * The commands are the ones openSslGuide.test.ts runs, with this device's
 * names filled in, so what is copied here produces a certificate that passes
 * strict verification in Home Assistant.
 */
const OpenSslGuide: React.FC<OpenSslGuideProps> = ({ variant, addresses = [] }) => {
  const { t } = useTranslation();
  const names = splitNames(addresses);

  return (
    <MoreOptions label={t('mqtt_tls.guide.title')} summary={t('mqtt_tls.guide.summary')}>
      <div className="space-y-4 pt-2">
        <p className="text-xs text-base-content/70">{t('mqtt_tls.guide.intro')}</p>
        <Step title={t('mqtt_tls.guide.step_ca')} help={t('mqtt_tls.guide.step_ca_help')} commands={caCommands()} />
        {variant === 'broker' ? (
          <Step
            title={t('mqtt_tls.guide.step_broker')}
            help={t('mqtt_tls.guide.step_broker_help')}
            commands={brokerCommands(names)}
          />
        ) : (
          <Step
            title={t('mqtt_tls.guide.step_client')}
            help={t('mqtt_tls.guide.step_client_help')}
            commands={clientCommands()}
          />
        )}
        <Step
          title={t('mqtt_tls.guide.step_verify')}
          commands={verifyCommand(variant === 'broker' ? 'broker' : 'client')}
        />
        <p className="text-xs text-base-content/70">
          {variant === 'broker' ? t('mqtt_tls.guide.outro_broker') : t('mqtt_tls.guide.outro_client')}
        </p>
      </div>
    </MoreOptions>
  );
};

export default OpenSslGuide;
