import React from 'react';
import { useTranslation } from '../hooks/useTranslation';

const LanguageSelector: React.FC = () => {
  const { language, changeLanguage, availableLanguages } = useTranslation();

  const handleLanguageChange = (langCode: string) => {
    changeLanguage(langCode);
    // Close dropdown by removing focus
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  };

  const currentLang = availableLanguages.find((lang: any) => lang.code === language);
  const CurrentFlag = currentLang?.flag;

  return (
    <div className="dropdown dropdown-end">
      <div tabIndex={0} role="button" className="btn btn-ghost btn-circle">
        <span className="text-lg">
          {CurrentFlag ? <CurrentFlag className="w-5 h-5" /> : '🌐'}
        </span>
      </div>
      <ul tabIndex={0} className="dropdown-content z-[1] menu p-2 shadow bg-base-100 rounded-box w-40">
        {availableLanguages.map((lang: any) => {
          const FlagComponent = lang.flag;
          return (
            <li key={lang.code}>
              <button
                onClick={() => handleLanguageChange(lang.code)}
                className={language === lang.code ? 'active' : ''}
              >
                <span className="mr-2"><FlagComponent className="w-4 h-4" /></span>
                {lang.name}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default LanguageSelector;
