import { useState } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';

interface ConfigCheckModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function ConfigCheckModal({ isOpen, onClose }: ConfigCheckModalProps) {
  const { t } = useTranslation();
  const [isChecking, setIsChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<{
    status: 'success' | 'error';
    message?: string;
  } | null>(null);

  const handleCheck = async () => {
    setIsChecking(true);
    try {
      const response = await axios.get('/api/check_configuration');
      setCheckResult({
        status: response.data.status,
        message: response.data.message
      });
    } catch (error) {
      setCheckResult({
        status: 'error',
        message: t('config_check.failed')
      });
    } finally {
      setIsChecking(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-base-300/80 flex items-center justify-center z-50">
      <div className="bg-base-200 p-8 rounded-lg shadow-lg max-w-2xl w-full mx-4">
        <h2 className="text-2xl font-bold mb-6">{t('config_check.title')}</h2>
        
        {isChecking ? (
          <div className="flex flex-col items-center gap-4 py-8">
            <div className="loading loading-spinner loading-lg"></div>
            <p className="text-lg">{t('config_check.checking')}</p>
          </div>
        ) : checkResult ? (
          <div className="space-y-4">
            <div className={`text-lg font-semibold ${
              checkResult.status === 'success' ? 'text-success' : 'text-error'
            }`}>
              {checkResult.status === 'success' ? t('config_check.valid') : t('config_check.error')}
            </div>
            {checkResult.message && (
              <pre className="bg-base-300 p-4 rounded-lg whitespace-pre-wrap">
                {checkResult.message}
              </pre>
            )}
            <div className="flex justify-end gap-4 mt-6">
              <button 
                className="btn btn-ghost"
                onClick={() => {
                  setCheckResult(null);
                  onClose();
                }}
              >
                {t('common.close')}
              </button>
              <button 
                className="btn btn-primary"
                onClick={() => {
                  setCheckResult(null);
                  handleCheck();
                }}
              >
                {t('config_check.check_again')}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            <p className="text-base-content/70">
              {t('config_check.description')}
            </p>
            <div className="flex justify-end gap-4">
              <button 
                className="btn btn-ghost"
                onClick={onClose}
              >
                {t('common.cancel')}
              </button>
              <button 
                className="btn btn-primary"
                onClick={handleCheck}
              >
                {t('config_check.check_button')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
