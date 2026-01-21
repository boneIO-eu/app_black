import { useTranslation } from '@/hooks/useTranslation';
import { FaDownload, FaCopy, FaCheck } from 'react-icons/fa';
import { DeviceConfig } from './types';

interface ActionsSectionProps {
  showPreview: boolean;
  setShowPreview: (value: boolean) => void;
  copied: boolean;
  isValid: boolean;
  generateJSON: () => DeviceConfig;
  onCopyJSON: () => void;
  onDownloadJSON: () => void;
}

export default function ActionsSection({
  showPreview,
  setShowPreview,
  copied,
  isValid,
  generateJSON,
  onCopyJSON,
  onDownloadJSON,
}: ActionsSectionProps) {
  const { t } = useTranslation();

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <div className="flex flex-wrap gap-2 justify-between items-center">
          <div className="flex gap-2">
            <button
              className="btn btn-outline"
              onClick={() => setShowPreview(!showPreview)}
            >
              {showPreview ? t('modbus_creator.hide_preview') : t('modbus_creator.show_preview')}
            </button>
          </div>
          
          <div className="flex gap-2">
            <button
              className="btn btn-outline"
              onClick={onCopyJSON}
              disabled={!isValid}
            >
              {copied ? <FaCheck className="mr-1" /> : <FaCopy className="mr-1" />}
              {copied ? t('modbus_creator.copied') : t('modbus_creator.copy_json')}
            </button>
            <button
              className="btn btn-primary"
              onClick={onDownloadJSON}
              disabled={!isValid}
            >
              <FaDownload className="mr-1" /> {t('modbus_creator.download_json')}
            </button>
          </div>
        </div>
        
        {showPreview && (
          <div className="mt-4">
            <pre className="bg-base-300 p-4 rounded-lg overflow-auto max-h-96 text-sm">
              {JSON.stringify(generateJSON(), null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
