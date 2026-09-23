import { useNavigate, useLocation } from 'react-router-dom';
import { FaStethoscope, FaLightbulb, FaInbox, FaQuestionCircle, FaThermometerHalf, FaSignOutAlt, FaNetworkWired, FaCog, FaProjectDiagram, FaPuzzlePiece, FaEllipsisH, FaChevronRight } from 'react-icons/fa';
import ThemeChanger from './ThemeChanger';
import LanguageSelector from './LanguageSelector';
import { useEffect, useState } from 'react';
import clsx from 'clsx';
import { useAuth } from '../hooks/useAuth';
import { useConfig } from '../contexts/ConfigContext';
import { useNodeRedAvailability } from '../hooks/useNodeRedAvailability';
import { useTranslation } from '../hooks/useTranslation';
import { useAppInit } from '../contexts/AppInitContext';
import Logo from "./Logo"
import { HelpDialog } from './HelpView';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';

export default function Navigation() {
  const { isAuthenticated, logout } = useAuth();
  const { data: initData } = useAppInit();
  const deviceName = initData?.name || '';

  // Derive from init data (single API call, no duplicates)
  const version = initData?.version || '';
  const serialNo = initData?.serial_no || '';
  const serialOverride = initData?.serial_override || '';
  const pwaName = initData?.pwa_name || '';
  const cloudDomain = initData?.cloud?.domain && initData?.cloud?.cloud_config_active
    ? initData.cloud.domain : '';

  useEffect(() => {
    if (deviceName) {
      document.title = `boneIO Black - ${deviceName}`;
    }
  }, [deviceName]);

  return (
    <>
    <div className="navbar bg-base-200 border-b border-base-content/10 px-4 sticky top-0 z-30 gap-3">
      <div className="flex-1 flex items-center min-w-0 gap-3">
        <a className="normal-case text-xl xl:mx-2 shrink-0">
          <Logo />
        </a>
        {/* Below xl the name is all that fits, and it is the one detail that
            cannot move to the "More" sheet: with several controllers on the
            network it is how you know which one you are about to switch. */}
        {deviceName && (
          <div className="xl:hidden min-w-0 flex flex-col leading-tight text-sm">
            <span className="line-clamp-2 break-words font-medium">{deviceName}</span>
            {pwaName && <span className="truncate text-xs opacity-60">{pwaName}</span>}
          </div>
        )}
        <div className="hidden xl:flex xl:ml-4 flex-col text-xs">
          {deviceName && (
            <span><span className="opacity-60">boneIO:</span> {deviceName}</span>
          )}
          {version && (
            <span><span className="opacity-60">v</span>{version}</span>
          )}
          {serialNo && (
            <span>
              <span className="opacity-60">S/N:</span> {serialNo}
              {serialOverride && (
                <span className="text-warning font-semibold ml-1">
                  (as: {serialOverride})
                </span>
              )}
            </span>
          )}
          {cloudDomain && (
            <a
              href={`https://${cloudDomain}:8443`}
              target="_blank"
              rel="noopener noreferrer"
              className="link link-primary no-underline hover:underline truncate max-w-48"
              title={`https://${cloudDomain}:8443`}
            >
              {cloudDomain}
            </a>
          )}
        </div>
      </div>
      <div className="flex shrink-0 xl:gap-2">
        <ThemeChanger />
        <LanguageSelector />
        {isAuthenticated && (
          <button
            onClick={logout}
            className="btn btn-ghost btn-circle"
            title="Logout"
            aria-label="Logout"
          >
            <FaSignOutAlt className="h-5 w-5" />
          </button>
        )}
      </div>
    </div>
    {/* Desktop second row: navigation menu. Solid background: at /80 the
        page's own sub-navigation showed through it while scrolling. */}
    <div className="hidden xl:block bg-base-200 border-b border-base-content/10 sticky top-16 z-20">
      <Menu />
    </div>
    </>
  );
}

interface MenuItem {
  path: string;
  default?: boolean;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  experimental?: boolean;
  right?: boolean;
  /** Gets a slot of its own in the mobile bottom bar; the rest go under "More". */
  primary?: boolean;
}

function useMenuItems() {
  const { t } = useTranslation();
  const location = useLocation();
  const { hasBoneioSection } = useConfig();
  const { isNodeRedAvailable } = useNodeRedAvailability();
  const { isAdmin } = useAuth();

  const menuItems: MenuItem[] = [
    { path: '/', default: true, icon: FaLightbulb, label: t('navigation.outputs'), primary: true },
    { path: '/inputs', icon: FaInbox, label: t('navigation.inputs'), primary: true },
    { path: '/sensors', icon: FaThermometerHalf, label: t('navigation.sensors'), primary: true },
    { path: '/modbus', icon: FaNetworkWired, label: t('navigation.modbus'), primary: true },
    { path: '/templates', icon: FaPuzzlePiece, label: t('navigation.templates') },
    // Everything below configures the device, so a viewer is not offered it.
    // The backend refuses these routes for a viewer regardless; hiding them
    // just avoids dead ends. See boneio/webui/middleware/policy.py.
    // Diagnostics is admin-only for a reason the name hides: its bus scans
    // are not passive. The Modbus helper pauses the polling loop to take the
    // bus, so someone who opened the page to look can leave Modbus stopped.
    ...(isAdmin ? [{ path: '/diagnostics', icon: FaStethoscope, label: t('navigation.diagnostics'), right: true }] : []),
    // Settings (experimental) - only show if boneio section exists in config
    ...(isAdmin && hasBoneioSection ? [{ path: '/settings', icon: FaCog, label: t('navigation.settings'), right: true }] : []),
    // Node-RED - only show if available via nginx proxy
    ...(isAdmin && isNodeRedAvailable ? [{ path: '/nodered', icon: FaProjectDiagram, label: 'Node-RED', right: true }] : []),
  ];

  const isActive = (item: MenuItem) =>
    (location.pathname === item.path) ||
    (item.path !== '/' && item.path !== '/modbus' && location.pathname.startsWith(item.path)) ||
    (location.pathname === "/" && item?.default);

  return { menuItems, isActive };
}

/** Shared look of a top-bar tab: 40px tall, active one a tinted pill. */
const tabClass = (active: boolean) => clsx(
  'flex items-center gap-2 h-10 px-4 rounded-lg text-sm transition-colors cursor-pointer',
  active ? 'nav-active font-semibold' : 'font-medium text-base-content/80 hover:bg-base-content/8 hover:text-base-content',
);

function Menu() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { menuItems, isActive } = useMenuItems();

  const leftItems = menuItems.filter((item) => !item.right);
  const rightItems = menuItems.filter((item) => item.right);

  const renderItem = (item: MenuItem) => (
    <li key={item.path}>
      <a
        onClick={() => navigate(item.path)}
        aria-current={isActive(item) ? 'page' : undefined}
        className={tabClass(!!isActive(item))}
      >
        <item.icon className="h-4 w-4" />
        <span>
          {item.label}
          {item.experimental && <span className="ml-1 badge badge-warning badge-xs">{t('navigation.experimental')}</span>}
        </span>
      </a>
    </li>
  );

  return (
    <div className="flex justify-between items-center w-full px-3 py-1.5">
      <ul className="flex flex-wrap gap-1">
        {leftItems.map(renderItem)}
      </ul>
      <ul className="flex flex-wrap gap-1">
        {rightItems.map(renderItem)}
        <li>
          <HelpDialog
            trigger={
              <button className={tabClass(false)}>
                <FaQuestionCircle className="h-4 w-4" />
                <span>{t('navigation.help')}</span>
              </button>
            }
          />
        </li>
      </ul>
    </div>
  );
}

/**
 * Bottom navigation below xl: the four everyday views under the thumb, the
 * rest in a "More" sheet. It is the column's last flex child and sticky, so
 * the content above ends where it starts instead of scrolling underneath —
 * which is also what lets the settings/diagnostics peek bar sit on top of it
 * (see --bottom-nav-h in index.css).
 */
export function BottomNav() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { menuItems, isActive } = useMenuItems();
  const [moreOpen, setMoreOpen] = useState(false);

  const primaryItems = menuItems.filter((item) => item.primary);
  const moreItems = menuItems.filter((item) => !item.primary);
  const helpActive = location.pathname === '/help';
  const moreActive = helpActive || moreItems.some((item) => isActive(item));

  const go = (path: string) => {
    setMoreOpen(false);
    navigate(path);
  };

  const slot = (key: string, label: string, Icon: MenuItem['icon'], active: boolean, onClick: () => void) => (
    <button
      key={key}
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={clsx(
        'flex flex-col items-center justify-center gap-1 min-w-0 h-16 cursor-pointer active:bg-base-content/5',
        active ? 'font-semibold' : 'font-medium text-base-content/75',
      )}
    >
      <span className={clsx('flex items-center justify-center w-14 h-8 rounded-full transition-colors', active && 'nav-active')}>
        <Icon className="h-5 w-5" />
      </span>
      <span className={clsx('text-xs leading-none truncate max-w-full px-1', active && 'nav-active-text')}>{label}</span>
    </button>
  );

  return (
    <nav className="xl:hidden sticky bottom-0 z-30 bg-base-200 border-t border-base-content/10 safe-area-bottom">
      <div className="grid" style={{ gridTemplateColumns: `repeat(${primaryItems.length + 1}, minmax(0, 1fr))` }}>
        {primaryItems.map((item) => slot(item.path, item.label, item.icon, !!isActive(item), () => go(item.path)))}
        {slot('more', t('navigation.more'), FaEllipsisH, moreActive, () => setMoreOpen(true))}
      </div>

      <Dialog open={moreOpen} onOpenChange={setMoreOpen}>
        <DialogContent className="gap-3 sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('navigation.more')}</DialogTitle>
          </DialogHeader>
          <ul className="flex flex-col gap-1">
            {[...moreItems.map((item) => ({ key: item.path, label: item.label, icon: item.icon, active: !!isActive(item) })),
              { key: '/help', label: t('navigation.help'), icon: FaQuestionCircle, active: helpActive },
            ].map(({ key, label, icon: Icon, active }) => (
              <li key={key}>
                <button
                  type="button"
                  onClick={() => go(key)}
                  aria-current={active ? 'page' : undefined}
                  className={clsx(
                    'flex items-center gap-4 w-full h-14 px-4 rounded-xl text-base text-left cursor-pointer transition-colors',
                    active ? 'nav-active font-semibold' : 'font-medium hover:bg-base-content/8 active:bg-base-content/10',
                  )}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  <span className="flex-1">{label}</span>
                  <FaChevronRight className="h-3.5 w-3.5 opacity-40" />
                </button>
              </li>
            ))}
          </ul>
          <DeviceDetails />
        </DialogContent>
      </Dialog>
    </nav>
  );
}

/** Version, serial and cloud link: what the xl header shows, for the sheet. */
function DeviceDetails() {
  const { data: initData } = useAppInit();
  const deviceName = initData?.name || '';
  const version = initData?.version || '';
  const serialNo = initData?.serial_no || '';
  const serialOverride = initData?.serial_override || '';
  const cloudDomain = initData?.cloud?.domain && initData?.cloud?.cloud_config_active
    ? initData.cloud.domain : '';

  return (
    <div className="pt-3 mt-1 border-t border-base-300 px-4 text-sm flex flex-col gap-1 opacity-80">
      {deviceName && (
        <span><span className="opacity-60">boneIO:</span> {deviceName}</span>
      )}
      {version && (
        <span><span className="opacity-60">v</span>{version}</span>
      )}
      {serialNo && (
        <span>
          <span className="opacity-60">S/N:</span> {serialNo}
          {serialOverride && (
            <span className="text-warning font-semibold ml-1">
              (as: {serialOverride})
            </span>
          )}
        </span>
      )}
      {cloudDomain && (
        <a
          href={`https://${cloudDomain}:8443`}
          target="_blank"
          rel="noopener noreferrer"
          className="link link-primary no-underline hover:underline truncate"
          title={`https://${cloudDomain}:8443`}
        >
          🌐 {cloudDomain}
        </a>
      )}
    </div>
  );
}
