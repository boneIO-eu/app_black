import { useState, useEffect } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';

export default function HelpView() {
  const { t } = useTranslation();
  const [version, setVersion] = useState<string>('');

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


  return (
    <div className="flex flex-col items-center justify-center h-full bg-base-300 p-4">
      <div className="max-w-lg text-center space-y-4">
        <h1 className="text-2xl font-bold mb-6">{t('help.title')}</h1>
        {version && (
          <p className="text-base-content/70 mb-4">{t('help.version')}: {version}</p>
        )}
        
        <p className="text-lg mb-4">{t('help.description')}</p>
        
        <div className="alert alert-info">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span>{t('help.encouraging_text')}</span>
        </div>
        
        <p className="text-lg flex flex-col">
          {t('help.discord_community')}{' '}
          <a 
            href="https://discord.gg/Hm2CzSjvtu" 
            target="_blank" 
            rel="noopener noreferrer" 
            className="link link-primary"
          >
            https://discord.gg/Hm2CzSjvtu
          </a>
        </p>
        
        <p className="text-lg flex flex-col">
          {t('help.app_repository')}:{' '}
          <a 
            href="https://github.com/boneIO-eu/app_black" 
            target="_blank" 
            rel="noopener noreferrer" 
            className="link link-primary"
          >
            https://github.com/boneIO-eu/app_black
          </a>
        </p>
        
        <p className="text-lg flex flex-col">
          {t('help.documentation')}:{' '}
          <a 
            href="https://boneio.eu/docs/black" 
            target="_blank" 
            rel="noopener noreferrer" 
            className="link link-primary"
          >
            https://boneio.eu/docs/black
          </a>
        </p>
        
        <p className="text-lg flex flex-col">
          {t('help.system_image')}:{' '}
          <a 
            href="https://github.com/boneIO-eu/black_debian_images" 
            target="_blank" 
            rel="noopener noreferrer" 
            className="link link-primary"
          >
            https://github.com/boneIO-eu/black_debian_images
          </a>
        </p>
        
        <div className="alert alert-success mt-6">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <div className="text-left">
            <p className="font-semibold">{t('help.suggestions_title')}</p>
            <p className="text-sm">{t('help.suggestions_text')}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
