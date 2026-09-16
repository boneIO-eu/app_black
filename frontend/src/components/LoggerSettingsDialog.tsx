import { useEffect, useState } from 'react';
import axios from '@/api/axios';
import { fetchConfig, invalidateConfigCache } from '@/api/configCache';
import { useTranslation } from '../hooks/useTranslation';
import LoggerForm from './UISettings/LoggerForm';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { NoticeCallout } from './UISettings/ui';

interface LoggerSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * The persistent `logger:` configuration, edited where it is needed.
 *
 * Diagnostics used to link out to the settings section for this, which meant
 * leaving the page you are debugging on, changing a level, and finding your
 * way back to the log. The levels are a settings concern — they survive a
 * restart, unlike the capture window next to them — but the moment you want
 * them is while you are staring at a log that is not telling you enough.
 *
 * So: the same form the settings section renders, in a dialog, writing to the
 * same endpoint. One definition of the form, two places to reach it, and the
 * section in Settings stays where someone looking for durable configuration
 * would expect to find it.
 */
export default function LoggerSettingsDialog({ open, onOpenChange }: LoggerSettingsDialogProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    // Everything below happens after an await. Resetting the error and the
    // dirty flag up here would be a synchronous setState inside an effect,
    // which is the cascade the lint rule is there to catch — and they are
    // only stale for as long as the read takes.
    (async () => {
      try {
        const payload = (await fetchConfig()) as Record<string, any>;
        if (cancelled) return;
        setError(null);
        setDirty(false);
        // /api/config answers { config: { ... } } — reading `logger` off the
        // envelope silently yields an empty form, and saving that would wipe
        // the levels it was supposed to edit.
        const logger = (payload?.config?.logger ?? {}) as Record<string, unknown>;
        setData(logger);
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  const save = async () => {
    if (!data) return;
    setSaving(true);
    setError(null);
    try {
      await axios.put('/api/config/logger', data, { timeout: 30000 });
      // Logger is a reload section: the levels take effect without a restart,
      // which is the whole reason it is worth offering from here.
      await axios.post('/api/config/reload', ['logger'], { timeout: 30000 });
      invalidateConfigCache();
      setDirty(false);
      onOpenChange(false);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl flex flex-col max-h-[85vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span aria-hidden="true">📝</span>
            {t('sections.logger')}
          </DialogTitle>
          <DialogDescription className="text-[13px]">
            {t('diagnostics.logger_dialog_intro')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto -mx-6 px-6 py-2">
          {data === null && !error ? (
            <div className="flex justify-center py-10">
              <span className="loading loading-spinner loading-md text-primary" />
            </div>
          ) : (
            <LoggerForm
              data={data ?? {}}
              onChange={(next: Record<string, unknown>) => {
                setData(next);
                setDirty(true);
              }}
            />
          )}
          {error && <NoticeCallout variant="error" className="mt-3" message={error} />}
        </div>

        <DialogFooter>
          <button className="btn btn-ghost btn-sm" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </button>
          <button
            className="btn btn-primary btn-sm gap-2"
            onClick={() => void save()}
            disabled={!dirty || saving}
          >
            {saving && <span className="loading loading-spinner loading-xs" />}
            {t('common.save')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
