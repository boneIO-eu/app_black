import { useNavigate, useLocation } from 'react-router-dom';
import { FaCode, FaList, FaLightbulb, FaInbox, FaQuestionCircle, FaThermometerHalf, FaSignOutAlt, FaNetworkWired, FaCog, FaTerminal, FaProjectDiagram } from 'react-icons/fa';
import ThemeChanger from './ThemeChanger';
import LanguageSelector from './LanguageSelector';
import { useState, useEffect } from 'react';
import clsx from 'clsx';
import axios from 'axios';
import { useAuth } from '../hooks/useAuth';
import { useDeviceName } from '../hooks/useDeviceName';
import { useConfig } from '../contexts/ConfigContext';
import { useNodeRedAvailability } from '../hooks/useNodeRedAvailability';
import { useTranslation } from '../hooks/useTranslation';
import Logo from "./Logo"

export default function Navigation() {
  const { isAuthenticated, logout } = useAuth();
  const [version, setVersion] = useState<string>('');
  const [serialNo, setSerialNo] = useState<string>('');
  const { deviceName } = useDeviceName();
  const [pwaName, setPwaName] = useState<string>('');

  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const response = await axios.get('/api/version');
        setVersion(response.data.version);
        if (response.data.serial_no) {
          setSerialNo(response.data.serial_no);
        }
      } catch (error) {
        console.error('Error fetching version:', error);
      }
    };

    fetchVersion();
  }, []);

  useEffect(() => {
    axios.get('/api/pwa_name').then(({ data }) => {
      setPwaName(data.pwa_name || '');
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (deviceName) {
      document.title = `boneIO Black - ${deviceName}`;
    }
  }, [deviceName]);

  return (
    <>
    <div className="navbar bg-base-200 border-b border-base-content/10 px-4 sticky top-0 z-30">
      <div className="flex-none xl:hidden">
        <label htmlFor="my-drawer" className="btn btn-square btn-ghost">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            className="inline-block w-6 h-6 stroke-current"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 6h16M4 12h16M4 18h16"
            ></path>
          </svg>
        </label>
      </div>
      <div className="flex-1 flex items-center">
        <a className="normal-case text-xl xl:mx-2">
          <Logo />
        </a>
        <div className="hidden xl:flex xl:ml-4 flex-col text-xs">
          {deviceName && (
            <span><span className="opacity-60">boneIO:</span> {deviceName}</span>
          )}
          {version && (
            <span><span className="opacity-60">v</span>{version}</span>
          )}
          {serialNo && (
            <span><span className="opacity-60">S/N:</span> {serialNo}</span>
          )}
        </div>
      </div>
      <Menu />
      <div className="flex xl:gap-2">
        <ThemeChanger />
        <LanguageSelector />
        {isAuthenticated && (
          <button
            onClick={logout}
            className="btn btn-ghost btn-circle"
            title="Logout"
          >
            <FaSignOutAlt className="h-5 w-5" />
          </button>
        )}
      </div>
    </div>
    {/* Mobile sub-header with device info */}
    <div className="xl:hidden bg-base-200/80 border-b border-base-content/5 px-4 py-1 flex items-center justify-between text-xs sticky top-16 z-20">
      <div className="flex items-center gap-3 min-w-0">
        {deviceName && (
          <span className="truncate"><span className="opacity-50">boneIO:</span> {deviceName}</span>
        )}
        {pwaName && (
          <span className="opacity-60 shrink-0">({pwaName})</span>
        )}
      </div>
    </div>
    </>
  );
}

interface MenuItem {
  path: string;
  default?: boolean;
  icon: any;
  label: string;
  experimental?: boolean;
}

function Menu({ sideMenu = false }: { sideMenu?: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { hasBoneioSection } = useConfig();
  const { isNodeRedAvailable } = useNodeRedAvailability();

  const menuItems: MenuItem[] = [
    { path: '/', default: true, icon: FaLightbulb, label: t('navigation.outputs') },
    { path: '/inputs', icon: FaInbox, label: t('navigation.inputs') },
    { path: '/sensors', icon: FaThermometerHalf, label: t('navigation.sensors') },
    { path: '/modbus', icon: FaNetworkWired, label: t('navigation.modbus') },
    { path: '/modbus-helper', icon: FaTerminal, label: t('navigation.modbus_helper') },
    // Settings (experimental) - only show if boneio section exists in config
    ...(hasBoneioSection ? [{ path: '/settings', icon: FaCode, label: t('navigation.settings') }] : []),
    { path: '/config', icon: FaCode, label: t('navigation.config') },
    { path: '/logs', icon: FaList, label: t('navigation.logs') },
    { path: '/system', icon: FaCog, label: t('navigation.system_update') },
    // Node-RED - only show if available via nginx proxy
    ...(isNodeRedAvailable ? [{ path: '/nodered', icon: FaProjectDiagram, label: 'Node-RED' }] : []),
    { path: '/help', icon: FaQuestionCircle, label: t('navigation.help') },
  ];

  const isActive = (item: MenuItem) => 
    (location.pathname === item.path) || 
    (item.path !== '/' && item.path !== '/modbus' && location.pathname.startsWith(item.path)) ||
    (location.pathname === "/" && item?.default);

  const handleClick = (path: string) => {
    // Close drawer if open (for mobile side menu)
    const drawerCheckbox = document.getElementById('my-drawer') as HTMLInputElement;
    if (drawerCheckbox) {
      drawerCheckbox.checked = false;
    }
    navigate(path);
  };

  // Desktop horizontal menu
  if (!sideMenu) {
    return (
      <ul className="menu menu-horizontal hidden xl:flex">
        {menuItems.map((item) => (
          <li key={item.path}>
            <a
              onClick={() => handleClick(item.path)}
              className={clsx({
                'active bg-primary text-primary-content font-semibold': isActive(item),
              })}
            >
              <item.icon className="h-5 w-5 xl:hidden" />
              <span className="hidden xl:inline">
                {item.label}
                {item.experimental && <span className="ml-1 badge badge-warning badge-xs">{t('navigation.experimental')}</span>}
              </span>
            </a>
          </li>
        ))}
      </ul>
    );
  }

  // Mobile side menu - larger, more touch-friendly
  return (
    <ul className="flex flex-col gap-1">
      {menuItems.map((item) => (
        <li key={item.path}>
          <a
            onClick={() => handleClick(item.path)}
            className={clsx(
              'flex items-center gap-4 px-4 py-4 rounded-xl text-lg font-medium transition-all',
              'active:scale-[0.98] cursor-pointer',
              isActive(item)
                ? 'bg-primary text-primary-content shadow-md'
                : 'hover:bg-base-200 text-base-content'
            )}
          >
            <item.icon className="h-6 w-6 shrink-0" />
            <span className="flex-1">
              {item.label}
              {item.experimental && (
                <span className="ml-2 badge badge-warning badge-sm">{t('navigation.experimental')}</span>
              )}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export const DrawerSide = () => {
  const [version, setVersion] = useState<string>('');
  const [serialNo, setSerialNo] = useState<string>('');
  const { deviceName } = useDeviceName();

  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const response = await axios.get('/api/version');
        setVersion(response.data.version);
        if (response.data.serial_no) {
          setSerialNo(response.data.serial_no);
        }
      } catch (error) {
        console.error('Error fetching version:', error);
      }
    };
    fetchVersion();
  }, []);

  return (
    <div className="drawer-side z-40">
      <label htmlFor="my-drawer" aria-label="close sidebar" className="drawer-overlay"></label>
      <div className="bg-base-100 text-base-content min-h-full w-80 p-4 pt-6 shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 px-2 pb-4 mb-2 border-b border-base-300">
          <Logo />
        </div>
        
        {/* Menu */}
        <div className="flex-1 overflow-y-auto">
          <Menu sideMenu={true} />
        </div>

        {/* Footer */}
        <div className="pt-4 mt-2 border-t border-base-300 px-2 text-xs flex flex-col gap-1">
          {deviceName && (
            <span><span className="opacity-60">boneIO:</span> {deviceName}</span>
          )}
          {version && (
            <span><span className="opacity-60">v</span>{version}</span>
          )}
          {serialNo && (
            <span><span className="opacity-60">S/N:</span> {serialNo}</span>
          )}
        </div>
      </div>
    </div>
  );
}