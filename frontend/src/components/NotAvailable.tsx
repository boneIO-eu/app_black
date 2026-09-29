import { useEffect, useState } from 'react';
import { useAppInit } from '@/contexts/AppInitContext';
import { useTranslation } from '@/hooks/useTranslation';
import { alreadyReloadedFor, noteReloadFor, readUpdateMark } from '@/utils/updateGuard';

/**
 * Drop this page's service worker and its precache, then reload.
 *
 * Only this scope's: behind a proxy several controllers can share the origin.
 * index.html is served no-store, so the reload gets the new shell straight
 * from the network instead of waiting for a new service worker to download
 * the whole build from a controller that is still starting up.
 */
async function reloadWithoutServiceWorker(): Promise<void> {
  try {
    const registration = await navigator.serviceWorker?.getRegistration();
    if (registration) {
      const scope = registration.scope;
      await registration.unregister();
      const names = await window.caches?.keys() ?? [];
      await Promise.all(names.filter(n => n.includes(scope)).map(n => window.caches.delete(n)));
    }
  } catch {
    // Reload anyway: on plain http there is no service worker to begin with.
  }
  window.location.reload();
}

/** Full screen for a controller that does not answer, or a panel that is stale. */
const NotAvailable = () => {
  const { isLoading, refetch, panelState, data, dismissPanelState } = useAppInit();
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());
  const serverVersion = data?.version ?? '';
  const stale = panelState === 'stale_panel';
  const reloadedOnce = stale && alreadyReloadedFor(sessionStorageOrUndefined(), serverVersion);

  // One automatic reload per server version; after that the user decides.
  useEffect(() => {
    if (!stale || !serverVersion || reloadedOnce) return;
    noteReloadFor(sessionStorageOrUndefined(), serverVersion);
    void reloadWithoutServiceWorker();
  }, [stale, serverVersion, reloadedOnce]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  if (stale) {
    const versions = { server: serverVersion, panel: __APP_VERSION__ };
    if (!reloadedOnce) {
      return (
        <Screen title={t('panel_guard.stale_title')} body={t('panel_guard.stale_body', versions)} />
      );
    }
    return (
      <Screen title={t('panel_guard.stale_manual_title')} body={t('panel_guard.stale_manual_body', versions)}>
        <button onClick={() => void reloadWithoutServiceWorker()} className="btn btn-primary">
          {t('panel_guard.reload')}
        </button>
        <button onClick={dismissPanelState} className="btn btn-ghost">
          {t('panel_guard.continue_anyway')}
        </button>
      </Screen>
    );
  }

  const mark = panelState === 'updating'
    ? readUpdateMark(window.localStorage, window.__BONEIO_BASE_PATH__, now)
    : null;
  const checkButton = (
    <button onClick={refetch} disabled={isLoading} className="btn btn-primary">
      {isLoading ? t('panel_guard.checking') : t('panel_guard.check_now')}
    </button>
  );

  if (mark) {
    return (
      <Screen title={t('panel_guard.updating_title')} body={t('panel_guard.updating_body')}>
        {mark.toVersion && (
          <p className="text-base-content/70">{t('panel_guard.updating_to', { version: mark.toVersion })}</p>
        )}
        <p className="text-sm text-base-content/50">
          {t('panel_guard.updating_elapsed', {
            minutes: String(Math.max(0, Math.floor((now - mark.startedAt) / 60_000))),
          })}
        </p>
        {checkButton}
      </Screen>
    );
  }

  return (
    <Screen title={t('panel_guard.probably_title')} body={t('panel_guard.probably_body')}>
      {checkButton}
    </Screen>
  );
};

function sessionStorageOrUndefined(): Storage | undefined {
  try {
    return window.sessionStorage;
  } catch {
    return undefined;
  }
}

function Screen({ title, body, children }: { title: string; body: string; children?: React.ReactNode }) {
  return (
    <div className="fixed inset-0 flex items-center justify-center z-50 bg-base-100">
      <div className="p-8 text-center max-w-md flex flex-col items-center gap-4">
        <div className="loading loading-dots loading-lg"></div>
        <h2 className="text-xl font-bold">{title}</h2>
        <p className="text-base-content/70">{body}</p>
        {children}
      </div>
    </div>
  );
}

export default NotAvailable;
