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
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';

export default function Navigation() {
  const { t } = useTranslation();
  const { isAuthenticated, logout } = useAuth();
  const [logoutOpen, setLogoutOpen] = useState(false);
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
      <div className="top-0 z-30 sticky gap-3 bg-base-200 px-4 border-base-content/10 border-b navbar xl:min-h-12 xl:py-0">
        <div className="flex flex-1 items-center gap-3 min-w-0">
          <a className="xl:mx-2 text-xl normal-case shrink-0">
            <Logo />
          </a>
          {/* Below xl the name is all that fits, and it is the one detail that
            cannot move to the "More" sheet: with several controllers on the
            network it is how you know which one you are about to switch. */}
          {deviceName && (
            <div className="xl:hidden flex flex-col min-w-0 text-xs leading-tight">
              <span className="font-medium wrap-break-word line-clamp-2">{deviceName}</span>
              {pwaName && <span className="opacity-60 truncate">{pwaName}</span>}
            </div>
          )}
          {/* xl: plain text, not a control — the name, and under it the
              version, serial and cloud link in small print. Two lines fit
              the 48px row, and nothing is hidden behind a click. */}
          {deviceName && (
            <div className="hidden xl:flex flex-col justify-center min-w-0 pl-4 border-l border-base-content/15 leading-tight">
              <span className="text-sm font-semibold truncate">{deviceName}</span>
              <span className="flex items-center gap-1.5 text-xs text-base-content/60 whitespace-nowrap">
                {version && <span>{t('navigation.version')} <span className="font-mono">{version}</span></span>}
                {serialNo && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>S/N <span className="font-mono">{serialNo}</span></span>
                  </>
                )}
                {serialOverride && (
                  <span className="font-semibold text-warning">
                    ({t('navigation.serial_override', { serial: serialOverride })})
                  </span>
                )}
                {cloudDomain && (
                  <>
                    <span aria-hidden="true">·</span>
                    <a
                      href={`https://${cloudDomain}:8443`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="link link-primary no-underline hover:underline truncate max-w-56"
                      title={`https://${cloudDomain}:8443`}
                    >
                      {cloudDomain}
                    </a>
                  </>
                )}
              </span>
            </div>
          )}
        </div>
        <div className="flex xl:gap-2 shrink-0">
          <ThemeChanger />
          <LanguageSelector />
          {isAuthenticated && (
            <button
              onClick={() => setLogoutOpen(true)}
              className="btn btn-ghost btn-circle"
              title={t('navigation.logout')}
              aria-label={t('navigation.logout')}
            >
              <FaSignOutAlt className="w-5 h-5" />
            </button>
          )}
          {/* It sits right next to the language and theme buttons, where a
              stray tap is easy — and on a phone the way back is typing the
              password again. */}
          <Dialog open={logoutOpen} onOpenChange={setLogoutOpen}>
            <DialogContent className="sm:max-w-sm">
              <DialogHeader>
                <DialogTitle>{t('navigation.logout_confirm_title')}</DialogTitle>
                <DialogDescription>{t('navigation.logout_confirm')}</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <button type="button" className="btn btn-ghost max-sm:btn-lg" onClick={() => setLogoutOpen(false)}>
                  {t('common.cancel')}
                </button>
                <button
                  type="button"
                  className="btn btn-primary max-sm:btn-lg"
                  onClick={() => { setLogoutOpen(false); logout(); }}
                >
                  <FaSignOutAlt className="w-4 h-4" />
                  {t('navigation.logout')}
                </button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>
      {/* Desktop second row: navigation menu. Solid background: at /80 the
        page's own sub-navigation showed through it while scrolling. */}
      <div className="hidden xl:block top-12 z-20 sticky bg-base-200 border-base-content/10 border-b">
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
  'flex items-center gap-2 px-4 rounded-lg h-10 text-sm transition-colors cursor-pointer',
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
        <item.icon className="w-4 h-4" />
        <span>
          {item.label}
          {item.experimental && <span className="ml-1 badge badge-warning badge-xs">{t('navigation.experimental')}</span>}
        </span>
      </a>
    </li>
  );

  return (
    <div className="flex justify-between items-center px-3 py-1.5 w-full">
      <ul className="flex flex-wrap gap-1">
        {leftItems.map(renderItem)}
      </ul>
      <ul className="flex flex-wrap gap-1">
        {rightItems.map(renderItem)}
        <li>
          <HelpDialog
            trigger={
              <button className={tabClass(false)}>
                <FaQuestionCircle className="w-4 h-4" />
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
        'flex flex-col justify-center items-center gap-1 active:bg-base-content/5 min-w-0 h-16 cursor-pointer',
        active ? 'font-semibold' : 'font-medium text-base-content/75',
      )}
    >
      <span className={clsx('flex justify-center items-center rounded-full w-14 h-8 transition-colors', active && 'nav-active')}>
        <Icon className="w-5 h-5" />
      </span>
      <span className={clsx('px-1 max-w-full text-xs truncate leading-none', active && 'nav-active-text')}>{label}</span>
    </button>
  );

  return (
    <nav className="xl:hidden bottom-0 safe-area-bottom z-30 sticky bg-base-200 border-base-content/10 border-t">
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
                    'flex items-center gap-4 px-4 rounded-xl w-full h-14 text-base text-left transition-colors cursor-pointer',
                    active ? 'nav-active font-semibold' : 'font-medium hover:bg-base-content/8 active:bg-base-content/10',
                  )}
                >
                  <Icon className="w-5 h-5 shrink-0" />
                  <span className="flex-1">{label}</span>
                  <FaChevronRight className="opacity-40 w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
          <DeviceDetails className="mt-1 px-4 pt-4 border-t border-base-300" />
        </DialogContent>
      </Dialog>
    </nav>
  );
}

/**
 * Name, version, serial and cloud link as label/value pairs. The xl chip
 * opens it in a popover and the mobile "More" sheet ends with it.
 */
function DeviceDetails({ className = '' }: { className?: string }) {
  const { t } = useTranslation();
  const { data: initData } = useAppInit();
  const deviceName = initData?.name || '';
  const pwaName = initData?.pwa_name || '';
  const version = initData?.version || '';
  const serialNo = initData?.serial_no || '';
  const serialOverride = initData?.serial_override || '';
  const cloudDomain = initData?.cloud?.domain && initData?.cloud?.cloud_config_active
    ? initData.cloud.domain : '';

  const rows: [string, React.ReactNode][] = [];
  if (version) rows.push([t('navigation.version'), <span className="font-mono">{version}</span>]);
  if (serialNo) rows.push([t('navigation.serial'), (
    <span className="font-mono">
      {serialNo}
      {serialOverride && (
        <span className="block font-sans text-xs font-semibold text-warning">
          {t('navigation.serial_override', { serial: serialOverride })}
        </span>
      )}
    </span>
  )]);
  if (cloudDomain) rows.push([t('navigation.cloud'), (
    <a
      href={`https://${cloudDomain}:8443`}
      target="_blank"
      rel="noopener noreferrer"
      className="link link-primary no-underline hover:underline break-all"
    >
      {cloudDomain}
    </a>
  )]);

  return (
    <div className={clsx('flex flex-col gap-3 text-sm', className)}>
      {deviceName && (
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-base leading-snug break-words">{deviceName}</span>
          {pwaName && <span className="text-base-content/60">{pwaName}</span>}
        </div>
      )}
      {rows.length > 0 && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 pt-3 border-t border-base-content/10">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-base-content/60">{label}</dt>
              <dd className="min-w-0">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
