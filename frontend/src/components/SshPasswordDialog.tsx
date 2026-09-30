import { useState, type FormEvent } from 'react';
import { FaTerminal } from 'react-icons/fa';
import type { AxiosError } from 'axios';
import axios from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';
import {
  MIN_PASSWORD_LENGTH,
  PASSWORD_PROBLEM_KEYS,
  checkNewPassword,
} from '@/utils/passwordPolicy';
import { SSH_ACCOUNT } from '@/utils/sshPassword';
import { PasswordField } from './AccountPasswordDialog';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';

type ChangeError = AxiosError<{
  code?: string;
  attempts_left?: number;
  retry_after?: number;
  detail?: string;
}>;

/** From how many tries left the form starts counting them down, as ReauthDialog does. */
const WARN_FROM = 3;

interface SshPasswordDialogProps {
  open: boolean;
  /** The login still has the password every unit shipped with. */
  shipped: boolean;
  onClose: () => void;
  onChanged: () => void;
  /** The device no longer has a password the panel may change; re-read its state. */
  onStale: () => void;
}

/**
 * Change the boneio SSH password, the way passwd does: current one first.
 *
 * The same form as the panel password dialog, on purpose, but a different
 * password: the Linux login behind SSH and sudo. The privileged helper checks
 * the current one and counts wrong ones for everybody, and each wrong one also
 * counts against this session like a wrong panel password.
 *
 * Render it with `key` changing per opening, so nothing typed survives.
 */
export default function SshPasswordDialog({
  open,
  shipped,
  onClose,
  onChanged,
  onStale,
}: SshPasswordDialogProps) {
  const { t } = useTranslation();
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [currentError, setCurrentError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const problem = checkNewPassword(password, repeat, SSH_ACCOUNT);
  // As in the panel password dialog: nothing is scolded before it is typed.
  const passwordError =
    password && problem && problem !== 'mismatch'
      ? t(PASSWORD_PROBLEM_KEYS[problem], { min: MIN_PASSWORD_LENGTH })
      : null;
  const repeatError = repeat && problem === 'mismatch' ? t('accounts.password_mismatch') : null;

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (problem || !current) return;
    setCurrentError(null);
    setFormError(null);
    setSubmitting(true);
    try {
      // sudo, a Python start-up and a password hash on a BeagleBone, plus two
      // seconds for a wrong password: well past the default 5 s.
      await axios.put(
        '/api/accounts/ssh-password',
        { current_password: current, new_password: password },
        { timeout: 60_000 },
      );
      onChanged();
    } catch (err: unknown) {
      const response = (err as ChangeError).response;
      const code = response?.data?.code;
      if (response?.status === 403 && code === 'current_password_wrong') {
        const left = response.data?.attempts_left;
        setCurrentError(
          typeof left === 'number' && left <= WARN_FROM
            ? `${t('accounts.ssh_current_wrong')} ${t('accounts.ssh_attempts_left', { count: left })}`
            : t('accounts.ssh_current_wrong'),
        );
      } else if (response?.status === 429) {
        const seconds = response.data?.retry_after;
        setFormError(
          t('accounts.ssh_throttled', {
            minutes: Math.max(1, Math.ceil((typeof seconds === 'number' ? seconds : 900) / 60)),
          }),
        );
      } else if (code === 'helper_outdated' || code === 'ssh_password_not_set') {
        // The device changed under the form; the card says what it is now.
        onStale();
      } else if (response?.status !== 401) {
        // 401 is a sign-out (the session's last wrong try), handled globally.
        setFormError(response?.data?.detail || t('accounts.ssh_failed'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !submitting && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <div className="flex items-center gap-3">
              <span className="stg-chip w-10 h-10 rounded-xl flex items-center justify-center shrink-0">
                <FaTerminal />
              </span>
              <DialogTitle>{t('accounts.ssh_dialog_title')}</DialogTitle>
            </div>
            <DialogDescription>
              {shipped ? t('accounts.ssh_dialog_intro_shipped') : t('accounts.ssh_dialog_intro')}
            </DialogDescription>
          </DialogHeader>

          <PasswordField
            id="ssh-current-password"
            label={t('accounts.ssh_current')}
            value={current}
            onChange={(v) => {
              setCurrent(v);
              setCurrentError(null);
            }}
            autoComplete="current-password"
            error={currentError}
            autoFocus
          />
          <PasswordField
            id="ssh-new-password"
            label={t('accounts.ssh_new')}
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
            error={passwordError}
          />
          <PasswordField
            id="ssh-repeat-password"
            label={t('accounts.ssh_repeat')}
            value={repeat}
            onChange={setRepeat}
            autoComplete="new-password"
            error={repeatError}
          />

          {formError && (
            <p role="alert" className="text-error text-sm">
              {formError}
            </p>
          )}

          <DialogFooter>
            <button
              type="button"
              className="btn btn-ghost max-sm:btn-lg"
              onClick={onClose}
              disabled={submitting}
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              className="btn btn-primary max-sm:btn-lg"
              disabled={submitting || !!problem || !current}
            >
              {submitting && <span className="loading loading-spinner loading-sm" />}
              {t('accounts.ssh_button')}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
