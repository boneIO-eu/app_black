import { useState, FormEvent } from 'react';
import { FaEye, FaEyeSlash } from 'react-icons/fa';
import { useAuth } from '../hooks/useAuth';
import { useTranslation } from '../hooks/useTranslation';
import { useNavigate } from 'react-router-dom';
import { useAppInit } from '../contexts/AppInitContext';
import ThemeChanger from './ThemeChanger';
import LanguageSelector from './LanguageSelector';
import Logo from './Logo';

/** A keyboard that pops up on its own covers half a phone screen; a mouse user loses nothing. */
const hasFinePointer = () =>
  typeof window !== 'undefined' && window.matchMedia('(pointer: fine)').matches;

export default function LoginView() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { login } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();
  // /api/init answers before login. The name is in it (the serial is not),
  // and with several controllers on the network it says which one this is.
  const { data: initData } = useAppInit();
  const deviceName = initData?.name || '';

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      await login(username, password);
      navigate('/');
    } catch {
      setError(t('login.invalid'));
      setSubmitting(false);
    }
  };

  return (
    // Phone: the form is the page, edge to edge — a card with a sliver of
    // background around it only wastes the width. From sm up it is a card
    // on the same tinted field the rest of the app sits on.
    <div className="min-h-dvh flex flex-col sm:items-center sm:justify-center stg-backdrop sm:p-6">
      {/* The header that normally carries these only exists after login,
          same as in the onboarding wizard. */}
      <div className="fixed top-2 right-2 z-10 flex items-center gap-1">
        <ThemeChanger />
        <LanguageSelector />
      </div>

      <main className="flex-1 sm:flex-none flex flex-col justify-center w-full sm:max-w-sm bg-base-100 px-6 pt-20 pb-12 sm:p-8 sm:rounded-2xl sm:border sm:border-base-content/10 sm:shadow-xl">
        <div className="flex flex-col items-center text-center">
          <div className="w-28">
            <Logo />
          </div>
          {/* Brand name, not copy — deliberately not translated. */}
          <span className="mt-1 text-xs font-semibold tracking-[0.35em] uppercase opacity-60">
            Black
          </span>
          <h1 className="mt-6 text-2xl font-bold">{t('login.heading')}</h1>
          {deviceName && (
            <p className="mt-1 text-base text-base-content/70 break-words">{deviceName}</p>
          )}
        </div>

        <form className="mt-8 flex flex-col gap-5" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="username" className="text-sm font-medium">
              {t('login.username')}
            </label>
            <input
              id="username"
              name="username"
              type="text"
              required
              autoFocus={hasFinePointer()}
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              className="input input-lg w-full text-base"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium">
              {t('login.password')}
            </label>
            {/* daisyUI styles a wrapper holding an input as the input itself,
                focus ring included, which leaves room for the eye button. */}
            <div className="input input-lg w-full pr-1">
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                required
                autoComplete="current-password"
                className="grow text-base"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="btn btn-ghost btn-square btn-sm h-10 w-10"
                aria-label={showPassword ? t('login.hide_password') : t('login.show_password')}
                aria-pressed={showPassword}
                title={showPassword ? t('login.hide_password') : t('login.show_password')}
              >
                {showPassword ? <FaEyeSlash className="h-5 w-5 opacity-70" /> : <FaEye className="h-5 w-5 opacity-70" />}
              </button>
            </div>
          </div>

          {error && (
            <div role="alert" className="alert alert-error alert-soft text-sm">
              {error}
            </div>
          )}

          <button type="submit" className="btn btn-primary btn-lg w-full mt-1" disabled={submitting}>
            {submitting && <span className="loading loading-spinner loading-sm" />}
            {submitting ? t('login.signing_in') : t('login.submit')}
          </button>
        </form>
      </main>
    </div>
  );
}
