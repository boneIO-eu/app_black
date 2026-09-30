import { useCallback, useEffect, useState } from 'react';
import { FaTerminal } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';
import { sshCardMode, type SshPasswordState } from '@/utils/sshPassword';
import SshPasswordDialog from './SshPasswordDialog';
import { SettingsCard, NoticeCallout } from './UISettings/ui';
import { LoadingState } from '@/components/ui/LoadingState';

/**
 * The boneio SSH login's password, changed the way passwd changes it.
 *
 * Not a panel account: the Linux user behind SSH and sudo, whose password is
 * therefore the root password. The first-run wizard copies the first panel
 * password onto it once; after that the two are separate and this card is
 * the panel's only say in it. The change wants the current SSH password — the
 * privileged helper checks it and counts wrong ones — so it grants nothing
 * knowing that password does not already. A lost one is not recovered here:
 * that is the flasher card.
 *
 * The card says how the login stands; the form is a dialog, like the panel
 * passwords' above it.
 */
export default function SshPasswordCard() {
  const { t } = useTranslation();
  const [state, setState] = useState<SshPasswordState>(null);
  const [supported, setSupported] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  // Bumped per opening, as the dialog's key: a fresh form every time.
  const [dialogKey, setDialogKey] = useState(0);
  const [dialogOpen, setDialogOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/accounts/ssh-password', { timeout: 30_000 });
      setState(data?.state ?? null);
      setSupported(Boolean(data?.supported));
    } catch {
      setState(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const mode = sshCardMode(state, supported);

  const status = () => {
    if (isLoading) {
      return (
        <LoadingState className="py-2" />
      );
    }
    if (mode === 'form') {
      return state === 'shipped' ? (
        <NoticeCallout variant="warning" message={t('accounts.ssh_shipped')} />
      ) : null;
    }
    return (
      <NoticeCallout
        variant={mode === 'empty' ? 'warning' : 'info'}
        message={t(`accounts.ssh_${mode}`)}
      />
    );
  };

  return (
    <>
      <SettingsCard
        icon={<FaTerminal />}
        title={t('accounts.ssh_title')}
        description={t('accounts.ssh_intro')}
        action={
          mode === 'form' && !isLoading ? (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => {
                setNotice(null);
                setDialogKey((k) => k + 1);
                setDialogOpen(true);
              }}
            >
              {t('accounts.ssh_button')}
            </button>
          ) : undefined
        }
      >
        {(notice || status()) && (
          <div className="flex flex-col gap-3">
            {notice && <NoticeCallout variant="success" message={notice} />}
            {status()}
          </div>
        )}
      </SettingsCard>

      <SshPasswordDialog
        key={dialogKey}
        open={dialogOpen}
        shipped={state === 'shipped'}
        onClose={() => setDialogOpen(false)}
        onChanged={() => {
          setDialogOpen(false);
          setNotice(t('accounts.ssh_changed'));
          void load();
        }}
        onStale={() => {
          setDialogOpen(false);
          void load();
        }}
      />
    </>
  );
}
