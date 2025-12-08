import { useNavigate, useLocation } from 'react-router-dom';
import { FaCode, FaList, FaLightbulb, FaInbox, FaQuestionCircle, FaThermometerHalf, FaSignOutAlt, FaNetworkWired, FaCog, FaTerminal } from 'react-icons/fa';
import ThemeChanger from './ThemeChanger';
import LanguageSelector from './LanguageSelector';
import { useState, useEffect } from 'react';
import clsx from 'clsx';
import axios from 'axios';
import { useAuth } from '../hooks/useAuth';
import { useDeviceName } from '../hooks/useDeviceName';
import { useConfig } from '../contexts/ConfigContext';
import { useTranslation } from '../hooks/useTranslation';
import Logo from "./Logo"

export default function Navigation() {
  const { isAuthenticated, logout } = useAuth();
  const [version, setVersion] = useState<string>('');
  const { deviceName } = useDeviceName();

  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const response = await axios.get('/api/version');
        setVersion(response.data.version);
      } catch (error) {
        console.error('Error fetching version:', error);
      }
    };

    fetchVersion();
  }, []);

  useEffect(() => {
    if (deviceName) {
      document.title = `boneIO Black - ${deviceName}`;
    }
  }, [deviceName]);

  return (
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

  const menuItems: MenuItem[] = [
    { path: '/', default: true, icon: FaLightbulb, label: t('navigation.outputs') },
    { path: '/inputs', icon: FaInbox, label: t('navigation.inputs') },
    { path: '/sensors', icon: FaThermometerHalf, label: t('navigation.sensors') },
    { path: '/modbus', icon: FaNetworkWired, label: t('navigation.modbus') },
    { path: '/modbus-helper', icon: FaTerminal, label: t('navigation.modbus_helper') },
    { path: '/config', icon: FaCode, label: t('navigation.config') },
    // Settings (experimental) - only show if boneio section exists in config
    ...(hasBoneioSection ? [{ path: '/settings', icon: FaCode, label: t('navigation.settings'), experimental: true }] : []),
    { path: '/logs', icon: FaList, label: t('navigation.logs') },
    { path: '/system-update', icon: FaCog, label: t('navigation.system_update') },
    { path: '/help', icon: FaQuestionCircle, label: t('navigation.help') },
  ];

  return (
    <ul className={clsx('menu', { 'menu-horizontal hidden xl:flex': !sideMenu })}>
      {menuItems.map((item) => (
        <li key={item.path}>
          <a
            onClick={() => navigate(item.path)}
            className={clsx({
              'active bg-primary text-primary-content font-semibold': 
                (location.pathname === item.path) || 
                (item.path !== '/' && item.path !== '/modbus' && location.pathname.startsWith(item.path)) ||
                (location.pathname === "/" && item?.default),
            })}
          >
            <item.icon className={clsx('h-5 w-5', { 'xl:hidden': !sideMenu })} />
            <span className={clsx({ 'hidden xl:inline': !sideMenu })}>
              {item.label}
              {item.experimental && <span className="ml-1 badge badge-warning badge-xs">{t('navigation.experimental')}</span>}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export const DrawerSide = () => {
  return (
  <div className='drawer-side z-40'>
    <label htmlFor="my-drawer" aria-label="close sidebar" className="drawer-overlay"></label>
    <div className='menu menu-lg bg-base-100 text-base-content min-h-full w-80 p-3 pt-4 shadow-lg'>
      <Menu sideMenu={true} />
    </div>
  </div>)
  
}