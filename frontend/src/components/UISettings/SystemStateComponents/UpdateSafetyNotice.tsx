import React, { useState } from 'react';
import { FaDownload, FaExternalLinkAlt, FaLifeRing, FaSpinner } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { NoticeCallout } from '../ui';

/**
 * Where the system images and the recovery instructions live. The backend
 * sends the same address with the OS update state; it is repeated here so the
 * notice also shows on update screens that never ask for that state.
 */
export const RECOVERY_IMAGES_URL = 'https://github.com/boneIO-eu/black_debian_images';

interface UpdateSafetyNoticeProps {
  /**
   * Also tell the operator to download a Node-RED backup — on the Node-RED
   * screen, and before a system update when Node-RED is in use.
   */
  nodeRed?: boolean;
  className?: string;
}

/**
 * Shown next to every update: boneIO, Node-RED and the operating system.
 *
 * An update that goes wrong on a controller in a cabinet ends in a reflash, and
 * then two things decide how bad the day is: whether the configuration left the
 * device before the update, and whether the operator knows where the image is.
 * Both are said here, every time, rather than in documentation nobody opens
 * until it is too late.
 */
export const UpdateSafetyNotice: React.FC<UpdateSafetyNoticeProps> = ({
  nodeRed = false,
  className,
}) => {
  const { t } = useTranslation();
  const [downloading, setDownloading] = useState(false);
  const [failed, setFailed] = useState(false);

  const downloadConfig = async () => {
    setDownloading(true);
    setFailed(false);
    try {
      const response = await axios.get('/api/config/download', { responseType: 'blob' });
      const match = /filename=(.+)/.exec(response.headers['content-disposition'] || '');
      const url = window.URL.createObjectURL(response.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = match ? match[1] : 'boneio_config.tar.gz';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Error downloading configuration backup:', err);
      setFailed(true);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <NoticeCallout
      variant="warning"
      icon={<FaLifeRing />}
      className={className}
      title={t('update_safety.title')}
      message={
        <div className="space-y-2">
          <p>{t('update_safety.backup')}</p>
          {nodeRed && <p>{t('update_safety.backup_nodered')}</p>}
          <p>
            {t('update_safety.recovery')}{' '}
            <a
              href={RECOVERY_IMAGES_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="link link-primary inline-flex items-center gap-1 font-mono"
            >
              github.com/boneIO-eu/black_debian_images
              <FaExternalLinkAlt className="text-[10px]" />
            </a>
          </p>
          {failed && <p className="text-error">{t('update_safety.download_failed')}</p>}
        </div>
      }
      action={
        <button
          type="button"
          className="btn btn-sm gap-2"
          onClick={downloadConfig}
          disabled={downloading}
        >
          {downloading ? <FaSpinner className="animate-spin" /> : <FaDownload />}
          {t('update_safety.download_config')}
        </button>
      }
    />
  );
};

export default UpdateSafetyNotice;
