import { ReactNode } from 'react';
import Navigation, { DrawerSide } from './Navigation';
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
    <div className="w-full max-w-screen h-screen drawer">
      <input id="my-drawer" type="checkbox" className="drawer-toggle" />
      
      <div className={clsx("flex flex-col drawer-content", { "max-h-screen": fullHeight })}>
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
      </div>
      <DrawerSide />
    </div>
  );
}
