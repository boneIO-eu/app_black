import { useTranslation } from '../hooks/useTranslation';
import DiagnosticsMenu from './DiagnosticsMenu';
import LogViewer from './LogViewer';
import Tools from './Tools';

/**
 * Why is this device behaving like this — in one place.
 *
 * The log is the page. The support actions that used to sit above it as a card
 * are in a menu beside the title: reading the log is what people come here to
 * do, and collecting a bundle is what they do once, on the day it does not
 * help. A screen of explanation between the reader and the log served neither.
 *
 * The persistent `logger:` configuration stays in Settings, linked from the
 * menu. That is a choice about how this device behaves from now on; the
 * capture window is about the next ten minutes, and putting the durable and
 * the temporary behind one control is how a device ends up permanently at
 * debug.
 */
export default function DiagnosticsView() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-3 px-4 pt-4 sm:px-6">
        <h1 className="text-lg font-bold flex items-center gap-2">
          🩺 {t('diagnostics.page_title')}
        </h1>
        <DiagnosticsMenu />
      </div>
      <LogViewer />

      {/* Bus scans — what is wired to the controller. They were their own
          top-level page; nothing in them is saved, so they belong with the
          other ways of finding out what is going on. */}
      <div className="px-4 pb-6 sm:px-6">
        <Tools />
      </div>
    </div>
  );
}
