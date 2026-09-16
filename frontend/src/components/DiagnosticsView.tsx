import { useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from '../hooks/useTranslation';
import { useConfig } from '@/contexts/ConfigContext';
import DiagnosticsSidebar from './DiagnosticsSidebar';
import {
  DIAGNOSTICS_SECTIONS,
  DEFAULT_DIAGNOSTICS_SECTION,
} from './diagnosticsSections';
import LogViewer from './LogViewer';
import ModbusHelper from './ModbusHelper';
import CANHelper from './CANHelper';
import CANNetwork from './CANNetwork';
import { I2CSection, CANNotSupported } from './Tools';
import SupportSection from './SupportSection';
import { useState } from 'react';

/**
 * Why is this device behaving like this — in one place.
 *
 * Built like Settings, because it answers the same kind of question: a rail
 * of places on the left, one of them open on the right, a header naming what
 * you are looking at. It used to be a log with a strip of bus scans stapled
 * underneath, and those scans had a tab strip of their own — tabs inside a
 * strip inside a page that also scrolled behind a log that scrolled.
 *
 * The shell does not scroll (Layout's `fullHeight`). Each section fills the
 * space and scrolls inside itself, so there is one scrollbar and it always
 * belongs to what you are reading.
 *
 * The support actions are a section of their own rather than a dropdown by
 * the title. They were three unrelated things in one 22rem panel that shut
 * when you clicked past it; as cards they have room to explain themselves,
 * which matters most for the bundle someone is about to email.
 *
 * The persistent `logger:` configuration is reachable from there through a
 * dialog rather than a link into Settings. The levels are a settings concern
 * — they survive a restart, unlike the capture window beside them — but the
 * moment you want to change them is while you are staring at a log that is
 * not saying enough, and that is here.

 */
export default function DiagnosticsView() {
  const { t } = useTranslation();
  const { canSupported, boardVersion } = useConfig();
  const { section } = useParams<{ section?: string }>();
  const navigate = useNavigate();
  const [isSheetOpen, setIsSheetOpen] = useState(false);

  const known = DIAGNOSTICS_SECTIONS.some(s => s.name === section);
  const activeSection = known ? section! : DEFAULT_DIAGNOSTICS_SECTION;
  const active = DIAGNOSTICS_SECTIONS.find(s => s.name === activeSection)!;

  const onNavigate = useCallback(
    (next: string) => navigate(`/diagnostics/${next}`),
    [navigate],
  );

  const canBlocked = Boolean(active.requiresCan) && !canSupported;

  return (
    <div className="settings-scope flex h-full flex-col lg:flex-row overflow-hidden">
      <DiagnosticsSidebar
        activeSection={activeSection}
        onNavigate={onNavigate}
        isSheetOpen={isSheetOpen}
        onSheetOpenChange={setIsSheetOpen}
      />

      <div className="flex-1 flex flex-col overflow-hidden min-w-0 pb-14 lg:pb-0">
        <div className="stg-header shrink-0 px-4 py-3.5 lg:px-6 lg:py-4 z-20">
          <div className="flex items-start gap-3.5 min-w-0">
            <div className="stg-chip w-11 h-11 rounded-xl hidden sm:flex items-center justify-center text-xl shrink-0">
              <span aria-hidden="true">{active.icon}</span>
            </div>
            <div className="min-w-0">
              <h1 className="text-xl lg:text-[26px] font-bold tracking-tight text-base-content leading-tight">
                {t(active.titleKey)}
              </h1>
              <p className="text-[13px] text-base-content/60 mt-1 leading-relaxed max-w-2xl">
                {t(active.descriptionKey)}
              </p>
            </div>
          </div>
        </div>

        {/* The log brings its own chrome and fills the pane; the scans are
            ordinary content on the canvas. */}
        {activeSection === 'log' ? (
          <div className="flex-1 min-h-0 overflow-hidden">
            <LogViewer />
          </div>
        ) : activeSection === 'support' ? (
          <div className="stg-canvas flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-8">
            <SupportSection />
          </div>
        ) : (
          <div className="stg-canvas flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-8">
            <div className="w-full max-w-5xl 2xl:max-w-6xl">
              {canBlocked ? (
                <CANNotSupported boardVersion={boardVersion} />
              ) : (
                <>
                  {activeSection === 'modbus' && <ModbusHelper />}
                  {activeSection === 'i2c' && <I2CSection />}
                  {activeSection === 'can_network' && <CANNetwork />}
                  {activeSection === 'can_sniffer' && <CANHelper />}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
