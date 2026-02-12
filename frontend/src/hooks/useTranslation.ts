import { useContext } from 'react';
import { TranslationContext, TranslationContextType } from '../contexts/TranslationContext';

/**
 * Hook for accessing translation functionality
 */
export const useTranslation = () => {
  const context = useContext(TranslationContext);
  
  if (!context) {
    throw new Error('useTranslation must be used within a TranslationProvider');
  }

  /**
   * Get translated text by key.
   * Supports nested keys like 'outputs.title' and interpolation with {{param}} syntax.
   *
   * @param key - Dot-separated translation key
   * @param params - Optional object with values to interpolate into {{placeholders}}
   */
  const t = (key: string, params?: Record<string, string | number>): string => {
    const keys = key.split('.');
    let value: any = context.translations;
    
    for (const k of keys) {
      value = value?.[k];
    }
    
    let result: string = value || key;

    if (params) {
      for (const [param, val] of Object.entries(params)) {
        result = result.replace(new RegExp(`\\{\\{${param}\\}\\}`, 'g'), String(val));
      }
    }

    return result;
  };

  return {
    t,
    language: context.language,
    changeLanguage: context.changeLanguage,
    availableLanguages: context.availableLanguages
  };
};

export type { TranslationContextType };
