import React, { createContext, useState, useEffect, ReactNode } from 'react';

// Import translations
import enTranslations from '../locales/en/common.json';
import plTranslations from '../locales/pl/common.json';
import enModbusDevices from '../locales/en/modbus_devices.json';
import plModbusDevices from '../locales/pl/modbus_devices.json';

/**
 * Deep merge two translation objects. Source values override target values.
 * Nested objects are merged recursively; arrays and primitives are replaced.
 */
function deepMerge(target: any, source: any): any {
  const result = { ...target };
  for (const key of Object.keys(source)) {
    if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
      result[key] = deepMerge(result[key] || {}, source[key]);
    } else {
      result[key] = source[key];
    }
  }
  return result;
}

// Flag components
export const EnFlag = ({ className }: { className?: string }) => (<svg
  className={className}
  viewBox="0 0 20 20"
  fill="none"
  xmlns="http://www.w3.org/2000/svg"
>
  <g clipPath="url(#clip0_51_175)">
    <path
      d="M10 20C15.5228 20 20 15.5228 20 10C20 4.47715 15.5228 0 10 0C4.47715 0 0 4.47715 0 10C0 15.5228 4.47715 20 10 20Z"
      fill="#F0F0F0"
    />
    <path
      d="M2.06718 3.91187C1.28167 4.93386 0.689365 6.11179 0.344482 7.39144H5.54675L2.06718 3.91187Z"
      fill="#0052B4"
    />
    <path
      d="M19.6555 7.3914C19.3106 6.11179 18.7183 4.93386 17.9328 3.91187L14.4533 7.3914H19.6555Z"
      fill="#0052B4"
    />
    <path
      d="M0.344482 12.6086C0.689404 13.8883 1.28171 15.0662 2.06718 16.0881L5.54663 12.6086H0.344482Z"
      fill="#0052B4"
    />
    <path
      d="M16.0882 2.06722C15.0662 1.28171 13.8883 0.689404 12.6087 0.344482V5.54671L16.0882 2.06722Z"
      fill="#0052B4"
    />
    <path
      d="M3.91177 17.9328C4.93377 18.7183 6.1117 19.3106 7.3913 19.6556V14.4534L3.91177 17.9328Z"
      fill="#0052B4"
    />
    <path
      d="M7.39127 0.344482C6.11166 0.689404 4.93373 1.28171 3.91177 2.06718L7.39127 5.54667V0.344482Z"
      fill="#0052B4"
    />
    <path
      d="M12.6087 19.6556C13.8883 19.3106 15.0662 18.7183 16.0882 17.9329L12.6087 14.4534V19.6556Z"
      fill="#0052B4"
    />
    <path
      d="M14.4533 12.6086L17.9328 16.0882C18.7183 15.0662 19.3106 13.8883 19.6555 12.6086H14.4533Z"
      fill="#0052B4"
    />
    <path
      d="M19.9154 8.69566H11.3044H11.3044V0.0846484C10.8774 0.0290625 10.4421 0 10 0C9.55785 0 9.12262 0.0290625 8.69566 0.0846484V8.69559V8.69563H0.0846484C0.0290625 9.12262 0 9.55793 0 10C0 10.4421 0.0290625 10.8774 0.0846484 11.3043H8.69559H8.69563V19.9154C9.12262 19.9709 9.55785 20 10 20C10.4421 20 10.8774 19.971 11.3043 19.9154V11.3044V11.3044H19.9154C19.9709 10.8774 20 10.4421 20 10C20 9.55793 19.9709 9.12262 19.9154 8.69566Z"
      fill="#D80027"
    />
    <path
      d="M12.6087 12.6087L17.071 17.071C17.2763 16.8659 17.4721 16.6514 17.6589 16.429L13.8385 12.6086H12.6087V12.6087Z"
      fill="#D80027"
    />
    <path
      d="M7.39128 12.6086H7.3912L2.92889 17.0709C3.13405 17.2762 3.34854 17.472 3.57089 17.6588L7.39128 13.8383V12.6086Z"
      fill="#D80027"
    />
    <path
      d="M7.39128 7.39142V7.39134L2.92894 2.92896C2.7237 3.13411 2.52792 3.3486 2.34113 3.57095L6.16155 7.39138H7.39128V7.39142Z"
      fill="#D80027"
    />
    <path
      d="M12.6087 7.39126L17.0711 2.92884C16.8659 2.7236 16.6514 2.52782 16.4291 2.34106L12.6087 6.16149V7.39126Z"
      fill="#D80027"
    />
  </g>
  <defs>
    <clipPath id="clip0_51_175">
      <rect width={20} height={20} fill="white" />
    </clipPath>
  </defs>
</svg>
);

export const PlFlag = ({ className }: { className?: string }) => (<svg
  xmlns="http://www.w3.org/2000/svg"
  xmlnsXlink="http://www.w3.org/1999/xlink"
  version="1.1"
  className={className}
  viewBox="0 0 256 256"
  xmlSpace="preserve"
>
  <g
    style={{
      stroke: "none",
      strokeWidth: 0,
      strokeDasharray: "none",
      strokeLinecap: "butt",
      strokeLinejoin: "miter",
      strokeMiterlimit: 10,
      fill: "none",
      fillRule: "nonzero",
      opacity: 1
    }}
    transform="translate(1.4065934065934016 1.4065934065934016) scale(2.81 2.81)"
  >
    <path
      d="M 45 90 C 20.147 90 0 69.853 0 45 h 90 C 90 69.853 69.853 90 45 90 z"
      style={{
        stroke: "none",
        strokeWidth: 1,
        strokeDasharray: "none",
        strokeLinecap: "butt",
        strokeLinejoin: "miter",
        strokeMiterlimit: 10,
        fill: "rgb(220,20,60)",
        fillRule: "nonzero",
        opacity: 1
      }}
      transform=" matrix(1 0 0 1 0 0) "
      strokeLinecap="round"
    />
    <path
      d="M 45 0 C 20.147 0 0 20.147 0 45 h 90 C 90 20.147 69.853 0 45 0 z"
      style={{
        stroke: "none",
        strokeWidth: 1,
        strokeDasharray: "none",
        strokeLinecap: "butt",
        strokeLinejoin: "miter",
        strokeMiterlimit: 10,
        fill: "rgb(243,244,245)",
        fillRule: "nonzero",
        opacity: 1
      }}
      transform=" matrix(1 0 0 1 0 0) "
      strokeLinecap="round"
    />
  </g>
</svg>
);

export interface TranslationContextType {
  language: string;
  translations: any;
  changeLanguage: (lang: string) => void;
  availableLanguages: { code: string; name: string; flag: React.ComponentType<{ className?: string }> }[];
}

export const TranslationContext = createContext<TranslationContextType | null>(null);

// Available languages
const availableLanguages = [
  { code: 'en', name: 'English', flag: EnFlag },
  { code: 'pl', name: 'Polski', flag: PlFlag }
];

// Translation mappings
const translationsMap: Record<string, any> = {
  en: deepMerge(enTranslations, enModbusDevices),
  pl: deepMerge(plTranslations, plModbusDevices),
};

interface TranslationProviderProps {
  children: ReactNode;
}

export const TranslationProvider: React.FC<TranslationProviderProps> = ({ children }) => {
  // Get language from localStorage or default to Polish
  const [language, setLanguage] = useState<string>(() => {
    return localStorage.getItem('boneio-language') || 'pl';
  });

  const [translations, setTranslations] = useState(translationsMap[language]);

  // Update translations when language changes
  useEffect(() => {
    setTranslations(translationsMap[language]);
    localStorage.setItem('boneio-language', language);
    
    // Update document language for accessibility
    document.documentElement.lang = language;
  }, [language]);

  const changeLanguage = (lang: string) => {
    if (translationsMap[lang]) {
      setLanguage(lang);
    }
  };

  const value: TranslationContextType = {
    language,
    translations,
    changeLanguage,
    availableLanguages
  };

  return (
    <TranslationContext.Provider value={value}>
      {children}
    </TranslationContext.Provider>
  );
};
