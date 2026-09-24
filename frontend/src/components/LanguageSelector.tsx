import React, { useState } from 'react';
import { FaCheck } from 'react-icons/fa';
import { useTranslation } from '../hooks/useTranslation';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';

const LanguageSelector: React.FC = () => {
  const { t, language, changeLanguage, availableLanguages } = useTranslation();
  const [sheetOpen, setSheetOpen] = useState(false);

  const handleLanguageChange = (langCode: string) => {
    changeLanguage(langCode);
    // Close dropdown by removing focus
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  };

  const currentLang = availableLanguages.find((lang) => lang.code === language);
  const CurrentFlag = currentLang?.flag;

  // The flag alone is a coloured circle in a row of bare circles, one of
  // which signs you out. Name the control, and name the language it is
  // currently set to.
  const label = currentLang?.name
    ? `${t('common.language')}: ${currentLang.name}`
    : t('common.language');

  const flag = (
    <span className="text-lg">
      {CurrentFlag ? <CurrentFlag className="w-5 h-5" /> : '🌐'}
    </span>
  );

  return (
    <>
    {/* Phone: a bottom sheet, like the rest of the app's pickers there — a
        dropdown hanging off the top corner is out of the thumb's reach and
        its rows are too small to hit. Below sm, where Dialog is a sheet. */}
    <button
      type="button"
      className="sm:hidden btn btn-ghost btn-circle"
      title={label}
      aria-label={label}
      onClick={() => setSheetOpen(true)}
    >
      {flag}
    </button>
    <Dialog open={sheetOpen} onOpenChange={setSheetOpen}>
      <DialogContent className="gap-3">
        <DialogHeader>
          <DialogTitle>{t('common.language')}</DialogTitle>
        </DialogHeader>
        <ul className="flex flex-col gap-1">
          {availableLanguages.map((lang) => {
            const FlagComponent = lang.flag;
            const active = language === lang.code;
            return (
              <li key={lang.code}>
                <button
                  type="button"
                  onClick={() => { changeLanguage(lang.code); setSheetOpen(false); }}
                  aria-current={active ? 'true' : undefined}
                  className={`flex items-center gap-4 w-full h-14 px-4 rounded-xl text-base text-left cursor-pointer transition-colors ${active ? 'nav-active font-semibold' : 'font-medium hover:bg-base-content/8 active:bg-base-content/10'}`}
                >
                  <FlagComponent className="w-6 h-6 shrink-0" />
                  <span className="flex-1">{lang.name}</span>
                  {active && <FaCheck className="w-4 h-4" />}
                </button>
              </li>
            );
          })}
        </ul>
      </DialogContent>
    </Dialog>

    <div className="hidden sm:block dropdown dropdown-end">
      <div
        tabIndex={0}
        role="button"
        className="btn btn-ghost btn-circle"
        title={label}
        aria-label={label}
      >
        {flag}
      </div>
      <ul tabIndex={0} className="dropdown-content z-1  menu p-2 shadow bg-base-100 rounded-box w-40">
        {availableLanguages.map((lang) => {
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
    </>
  );
};

export default LanguageSelector;
