import { useNavigate, useLocation } from 'react-router-dom';
import { FaCode, FaList, FaLightbulb, FaInbox, FaQuestionCircle, FaThermometerHalf, FaSignOutAlt, FaNetworkWired, FaCog } from 'react-icons/fa';
import ThemeChanger from './ThemeChanger';
import { useState, useEffect } from 'react';
import clsx from 'clsx';
import axios from 'axios';
import { useAuth } from '../hooks/useAuth';
import { useDeviceName } from '../hooks/useDeviceName';
import { useConfig } from '../contexts/ConfigContext';
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
      <div className="flex-none lg:hidden">
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
        <a className="normal-case text-xl lg:mx-2">
          <Logo />
        </a>
        <div className="grid grid-cols-2 lg:ml-4 gap-2">
          {deviceName && (
            <>
              <div className='hidden lg:block text-sm opacity-80'>boneIO name:</div>
              <div className='text-sm justify-self-end border-r-2 px-2 lg:border-r-0 lg:px-0'>{deviceName}</div>
            </>
          )}
          {version && (
            <>
              <div className='hidden lg:block text-sm opacity-80'>App version:</div>
              <div className='text-sm justify-self-end'>{version}</div>
            </>
          )}
        </div>
      </div>
      <Menu />
      <div className="flex lg:gap-2">
        <ThemeChanger />
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
  const navigate = useNavigate();
  const location = useLocation();
  const { hasBoneioSection } = useConfig();

  const menuItems: MenuItem[] = [
    { path: '/', default: true, icon: FaLightbulb, label: 'Outputs' },
    { path: '/inputs', icon: FaInbox, label: 'Inputs' },
    { path: '/sensors', icon: FaThermometerHalf, label: 'Sensors' },
    { path: '/modbus', icon: FaNetworkWired, label: 'Modbus' },
    { path: '/config', icon: FaCode, label: 'Config' },
    // Settings (experimental) - only show if boneio section exists in config
    ...(hasBoneioSection ? [{ path: '/settings', icon: FaCode, label: 'Settings', experimental: true }] : []),
    { path: '/logs', icon: FaList, label: 'Logs' },
    { path: '/system-update', icon: FaCog, label: 'System' },
    { path: '/help', icon: FaQuestionCircle, label: 'Help' },
  ];

  return (
    <ul className={clsx('menu', { 'menu-horizontal hidden lg:flex': !sideMenu })}>
      {menuItems.map((item) => (
        <li key={item.path}>
          <a
            onClick={() => navigate(item.path)}
            className={clsx({
              'active bg-primary text-primary-content font-semibold': location.pathname === item.path || location.pathname === "/" && item?.default,
            })}
          >
            <item.icon className={clsx('h-5 w-5', { 'lg:hidden': !sideMenu })} />
            <span className={clsx({ 'hidden lg:inline': !sideMenu })}>
              {item.label}
              {item.experimental && <span className="ml-1 text-xs bg-yellow-500 text-black px-1 rounded">EXPERIMENTAL</span>}
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
    <div className='menu bg-base-200 text-base-content min-h-full w-48 p-4'>
      <Menu sideMenu={true} />
    </div>
  </div>)
  
}