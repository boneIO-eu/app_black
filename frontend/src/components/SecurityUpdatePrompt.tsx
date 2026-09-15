import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppInit } from '../contexts/AppInitContext';
import { useAuth } from '../hooks/useAuth';
import { useTranslation } from '../hooks/useTranslation';
import { useSecurityPosture } from '../hooks/useSecurityPosture';
import { checkText, promptDecision } from '../utils/securityPosture';

/**
 * Points an administrator at the Security section after an update.
 *
 * boneIO's hardening work lands in releases that existing devices install
 * without anyone reading the notes. A device that has been running since 1.5
 * comes out of the update with the same factory MQTT password it went in with,
 * and nothing about the panel changes enough to say so. This is the one moment
 * the user is looking at the screen anyway.
 *
 * It is a prompt, not a gate: one button opens the section, the other closes
 * it, and it does not come back for that version. An update that forces a
 * security interview is an update people learn to postpone.
 *
 * Shown only when something is actually outstanding. Interrupting someone to
 * tell them everything is fine is how a notice becomes noise, and the next one
 * gets dismissed unread.
 */

const SEEN_VERSION_KEY = 'boneio.security.promptedVersion';

function readSeenVersion(): string | null {
  try {
    return localStorage.getItem(SEEN_VERSION_KEY);
  } catch {
    // Private mode, or storage disabled. Treat it as never prompted: showing
    // the notice twice is a smaller failure than never showing it.
    return null;
  }
}

function writeSeenVersion(version: string): void {
  try {
    localStorage.setItem(SEEN_VERSION_KEY, version);
  } catch {
    // Nothing to do — the prompt will simply appear again next time.
  }
}

export default function SecurityUpdatePrompt() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const appInit = useAppInit();
  const { posture } = useSecurityPosture();

  const version = appInit.data?.version ?? null;
  const [seenVersion, setSeenVersion] = useState<string | null>(() => readSeenVersion());
  const [dismissed, setDismissed] = useState(false);

  // A device with nothing outstanding never prompts, and recording the version
  // now means it will not prompt later for this one either. That is the point:
  // the notice is about the gap, not about the release.
  useEffect(() => {
    if (!isAdmin || !version || !posture) return;
    if (posture.summary.actionable === 0) {
      // Only the stored value changes. React state is left alone on purpose:
      // this branch already renders nothing, and writing state from an effect
      // would re-render for no visible reason.
      writeSeenVersion(version);
    }
  }, [isAdmin, version, posture]);

  const decision = promptDecision({ isAdmin, version, seenVersion, posture, dismissed });
  if (!decision.show || !version || !posture) return null;

  const close = () => {
    writeSeenVersion(version);
    setSeenVersion(version);
    setDismissed(true);
  };

  const review = () => {
    close();
    navigate('/settings/security');
  };

  // Without a previously recorded version there is no evidence an update
  // happened — this browser may simply never have been here. Saying "updated
  // to 1.6.0" would be a guess, so the neutral title is used instead.
  const title = decision.knownUpgrade
    ? t('security.after_update.title', { version })
    : t('security.after_update.title_first');

  return (
    <dialog className="modal modal-open" aria-labelledby="security-update-title">
      <div className="modal-box max-w-lg">
        <h3 id="security-update-title" className="font-bold text-lg flex items-center gap-2">
          🛡️ {title}
        </h3>
        <p className="py-3 text-sm">{t('security.after_update.body')}</p>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="badge badge-error">
            {t('security.after_update.outstanding', { count: posture.summary.actionable })}
          </span>
          {posture.checks
            .filter(c => c.state === 'failed' && c.severity !== 'info')
            .slice(0, 3)
            .map(c => (
              <span key={c.id} className="badge badge-ghost badge-sm">
                {/* Translated the same way the section does. Taking the
                    backend's own English here made the prompt read half in
                    one language and half in the other. */}
                {checkText(t, c.id, 'title', c.title)}
              </span>
            ))}
        </div>
        <div className="modal-action">
          <button className="btn btn-outline" onClick={close}>
            {t('security.after_update.later')}
          </button>
          <button className="btn btn-primary" onClick={review}>
            {t('security.after_update.review')}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={close}>close</button>
      </form>
    </dialog>
  );
}
