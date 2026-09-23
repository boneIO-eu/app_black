import { ReactNode } from 'react';
import Navigation, { BottomNav } from './Navigation';
import StartupBanner from './StartupBanner';
import MigrationBanner from './MigrationBanner';
import AnonymousAccessBanner from './AnonymousAccessBanner';
import clsx from 'clsx';

interface LayoutProps {
  children: ReactNode;
  /**
   * The page manages its own height and scrolling.
   *
   * Used by the screens that are a viewport-filling workspace rather than a
   * document: the settings editor, the YAML editor, and diagnostics. Without
   * it the shell scrolls as well as the pane inside, which puts two
   * scrollbars side by side against the same right edge.
   */
  fullHeight?: boolean;
}


export default function Layout({ children, fullHeight = false }: LayoutProps) {

  return (
    // A one-cell grid, as the daisyUI drawer that used to wrap this was: the
    // column stretches to at least the viewport, and on ordinary pages grows
    // with the content so the document scrolls under the sticky bars.
    <div className="w-full max-w-screen h-screen grid">
      <div className={clsx("flex flex-col min-w-0", { "max-h-screen": fullHeight })}>
        <Navigation />
        <AnonymousAccessBanner />
        <StartupBanner />
        <MigrationBanner />
        {/* The tinted field the cards sit on. Settings and Diagnostics paint
            their own inside `.settings-scope`, so this is for everything
            else — and `bg-base-100` here would have covered theirs. */}
        <main
          className={clsx(
            "flex-1",
            fullHeight ? "overflow-hidden" : "overflow-y-auto stg-backdrop",
          )}
        >
          {children}
        </main>
        <BottomNav />
      </div>
    </div>
  );
}
