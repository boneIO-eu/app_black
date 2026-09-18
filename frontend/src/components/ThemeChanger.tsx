import { useEffect, useState } from 'react';
import { FaSun, FaMoon } from 'react-icons/fa';
import { useTranslation } from '../hooks/useTranslation';

/**
 * Returns the localStorage key for theme.
 *
 * - Direct access on device: 'boneio-theme'
 * - Inside HA ingress proxy: 'boneio-theme-proxy-0' (suffix from __BONEIO_BASE_PATH__)
 *
 * This allows each proxied device to have its own theme preference.
 */
function getThemeStorageKey(): string {
  const basePath = window.__BONEIO_BASE_PATH__ || '';
  if (basePath) {
    // Extract suffix like "proxy-0" from "/api/hassio_ingress/xxx/proxy/0"
    const match = basePath.match(/\/(proxy\/\d+)\/?$/);
    if (match) {
      return 'boneio-theme-' + match[1].replace('/', '-');
    }
  }
  return 'boneio-theme';
}

/**
 * Returns the system preferred theme based on prefers-color-scheme media query.
 */
function getSystemTheme(): string {
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

/**
 * Returns the theme from URL query parameter (?theme=dark or ?theme=light),
 * e.g. when loaded inside HA ingress dashboard iframe.
 */
function getUrlTheme(): string | null {
  const params = new URLSearchParams(window.location.search);
  const t = params.get('theme');
  return (t === 'dark' || t === 'light') ? t : null;
}

export default function ThemeChanger() {
  const { t } = useTranslation();
  const storageKey = getThemeStorageKey();

  const [theme, setTheme] = useState(() => {
    // Priority: user choice (localStorage) > HA dashboard (URL) > system
    return localStorage.getItem(storageKey) || getUrlTheme() || getSystemTheme();
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Listen for system theme changes when user hasn't manually chosen
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    const handler = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem(storageKey)) {
        const systemTheme = e.matches ? 'light' : 'dark';
        setTheme(systemTheme);
      }
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [storageKey]);

  const handleThemeChange = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem(storageKey, newTheme);
  };

  // Says what the click does, not what the theme is. The button next to it
  // signs you out, and neither carried a label of any kind — an icon you
  // have to click to find out what it does is how you sign out by accident.
  const label = theme === 'dark' ? t('common.switch_to_light') : t('common.switch_to_dark');

  return (
<div className='flex-none items-center lg:block '>
    <button
      className="btn btn-ghost font-normal"
      onClick={() => handleThemeChange()}
      title={label}
      aria-label={label}
    >
      {theme === 'dark' ? (
      <FaSun className="w-5 h-5" />
    ) : (
      <FaMoon className="w-5 h-5" />
    )} 
    </button>
    </div>
  );
}
