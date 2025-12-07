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
   * Get translated text by key
   * Supports nested keys like 'outputs.title'
   */
  const t = (key: string): string => {
    const keys = key.split('.');
    let value: any = context.translations;
    
    for (const k of keys) {
      value = value?.[k];
    }
    
    return value || key; // Return key if translation not found
  };

  return {
    t,
    language: context.language,
    changeLanguage: context.changeLanguage,
    availableLanguages: context.availableLanguages
  };
};

export type { TranslationContextType };
