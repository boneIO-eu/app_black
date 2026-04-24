import { ReactNode } from 'react';
import Navigation, { DrawerSide } from './Navigation';
import StartupBanner from './StartupBanner';
import MigrationBanner from './MigrationBanner';
import clsx from 'clsx';

interface LayoutProps {
  children: ReactNode;
  configEditor?: boolean;
}


export default function Layout({ children, configEditor = false }: LayoutProps) {

  return (
    <div className="w-full max-w-screen h-screen drawer">
      <input id="my-drawer" type="checkbox" className="drawer-toggle" />
      
      <div className={clsx("flex flex-col drawer-content", { "max-h-screen": configEditor})}>
        <Navigation />
        <StartupBanner />
        <MigrationBanner />
        <main className="flex-1 overflow-y-auto bg-base-100">
          {children}
        </main>
      </div>
      <DrawerSide />
    </div>
  );
}
