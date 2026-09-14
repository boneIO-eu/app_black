import { useState, FormEvent } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useTranslation } from '../hooks/useTranslation';
import { useNavigate } from 'react-router-dom';
import ThemeChanger from './ThemeChanger';
import Logo from './Logo';

export default function LoginView() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const { login } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    try {
      await login(username, password);
      navigate('/');
    } catch (err) {
      setError(t('login.invalid'));
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-100">
      <div className='hidden'>
        <ThemeChanger />
      </div>
      <div className="max-w-md w-full space-y-8 p-8 bg-base-100 rounded-lg shadow-lg">
        <div className="flex flex-col items-center">
          <div className="w-32">
            <Logo />
          </div>
          <h2 className="mt-6 text-center text-3xl font-extrabold">
            <p>{t('login.title')}</p><p>boneIO Black</p>
          </h2>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="rounded-md shadow-xs -space-y-px">
            <div className='my-4'>
              <label htmlFor="username" className="sr-only">
                {t('login.username')}
              </label>
              <input
                id="username"
                name="username"
                type="text"
                required
                className="input  w-full"
                placeholder={t('login.username')}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="mt-4">
              <label htmlFor="password" className="sr-only">
                {t('login.password')}
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                className="input  w-full"
                placeholder={t('login.password')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          {error && (
            <div className="text-error text-center text-sm">
              {error}
            </div>
          )}

          <div>
            <button type="submit" className="btn btn-primary w-full">
              {t('login.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
