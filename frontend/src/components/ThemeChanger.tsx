import { useEffect, useState } from 'react';
import { FaSun, FaMoon } from 'react-icons/fa';

/**
 * Returns the system preferred theme based on prefers-color-scheme media query.
 */
function getSystemTheme(): string {
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

export default function ThemeChanger() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('theme');
    return saved || getSystemTheme();
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Listen for system theme changes when user hasn't manually chosen
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    const handler = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem('theme')) {
        const systemTheme = e.matches ? 'light' : 'dark';
        setTheme(systemTheme);
      }
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const handleThemeChange = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
  };

  return (
<div className='flex-none items-center lg:block '>
    <button className="btn btn-ghost font-normal" onClick={() => handleThemeChange()}>
      {theme === 'dark' ? (
      <FaSun className="w-5 h-5" />
    ) : (
      <FaMoon className="w-5 h-5" />
    )} 
    </button>
    </div>
  );
}
