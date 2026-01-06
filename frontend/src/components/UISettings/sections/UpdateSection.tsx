import React from 'react';
import {
  FaDownload,
  FaExclamationTriangle,
  FaSpinner,
  FaCheck,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

interface UpdateSectionProps {
  updateInfo: any;
  isChecking: boolean;
  isUpdating: boolean;
  updateStatus: any;
  error: string | null;
  onCheckForUpdates: () => void;
  onStartUpdate: (version?: string) => void;
}

export const UpdateSection: React.FC<UpdateSectionProps> = ({
  updateInfo,
  isChecking,
  isUpdating,
  updateStatus,
  error,
  onCheckForUpdates,
  onStartUpdate,
}) => {
  const { t } = useTranslation();

  return (
    <div className="card bg-base-200 shadow-xl">
      <div className="card-body">
        <div className="space-y-6">
          {/* Header */}
          <div className="flex lg:items-center justify-between flex-col lg:flex-row gap-2">
            <h2 className="text-2xl font-bold">{t('system_update.title')}</h2>
            <div>
              <button
                className="btn btn-sm"
                onClick={onCheckForUpdates}
                disabled={isChecking || isUpdating}
              >
                {isChecking ? (
                  <FaSpinner className="animate-spin" />
                ) : (
                  t('system_update.check_for_updates')
                )}
              </button>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="alert alert-error">
              <FaExclamationTriangle />
              <span>{error}</span>
            </div>
          )}

          {/* Current Version Card */}
          <div className="card bg-base-200">
            <div className="card-body">
              <h3 className="card-title">{t('system_update.current_version')}</h3>
              <div className="flex lg:items-center gap-4 flex-col lg:flex-row">
                <span className="text-3xl font-mono font-bold text-primary">
                  {updateInfo?.current_version || '...'}
                </span>
                {updateInfo?.current_is_prerelease && (
                  <span className="badge badge-warning">{t('system_update.prerelease')}</span>
                )}
              </div>
            </div>
          </div>

          {/* Prerelease Update Available */}
          {updateInfo?.prerelease_update_available && !updateInfo?.update_available && (
            <div className="card bg-warning/10 border border-warning">
              <div className="card-body">
                <h3 className="card-title text-warning">
                  <FaExclamationTriangle /> {t('system_update.prerelease_available')}
                </h3>
                <p className="text-sm opacity-70">
                  {t('system_update.prerelease_description')}
                </p>
                <div className="flex lg:items-center gap-4 flex-col lg:flex-row mt-4">
                  <div>
                    <div className="text-sm opacity-70">{t('system_update.latest_prerelease')}</div>
                    <div className="text-2xl font-mono font-bold text-warning">
                      {updateInfo.latest_prerelease}
                    </div>
                  </div>
                  <div className="flex-1"></div>
                  <button
                    className="btn btn-warning"
                    onClick={() => onStartUpdate(updateInfo.latest_prerelease)}
                    disabled={isUpdating}
                  >
                    <FaDownload />
                    {t('system_update.update_to_prerelease')}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Stable Update Available */}
          {updateInfo?.update_available && (
            <div className="card bg-success/10 border border-success">
              <div className="card-body">
                <h3 className="card-title text-success">
                  <FaDownload /> {t('system_update.new_version_available')}
                </h3>

                <div className="flex lg:items-center gap-4 flex-col lg:flex-row mt-4">
                  <div>
                    <div className="text-sm opacity-70">{t('system_update.latest_version')}</div>
                    <div className="text-2xl font-mono font-bold text-success">
                      {updateInfo.latest_version}
                    </div>
                  </div>
                  <div className="flex-1"></div>
                  <button
                    className="btn btn-success"
                    onClick={() => onStartUpdate()}
                    disabled={isUpdating}
                  >
                    <FaDownload />
                    {t('system_update.update_now')}
                  </button>
                </div>

                {updateInfo.release_url && (
                  <div className="mt-4">
                    <a
                      href={updateInfo.release_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="link link-primary text-sm"
                    >
                      {t('system_update.view_release_notes')}
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Update in Progress */}
          {isUpdating && updateStatus && (
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">
                  <FaSpinner className="animate-spin" />
                  {t('system_update.update_in_progress')}
                </h3>
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>{updateStatus.step}</span>
                      <span>{updateStatus.progress}%</span>
                    </div>
                    <progress
                      className="progress progress-primary w-full"
                      value={updateStatus.progress}
                      max="100"
                    ></progress>
                  </div>

                  {updateStatus.log && updateStatus.log.length > 0 && (
                    <div className="bg-base-300 p-4 rounded-lg max-h-64 overflow-y-auto">
                      <pre className="text-xs font-mono whitespace-pre-wrap">
                        {updateStatus.log.join('\n')}
                      </pre>
                    </div>
                  )}

                  {updateStatus.status === 'success' && (
                    <div className="alert alert-success">
                      <FaCheck />
                      <span>{t('system_update.update_complete')}</span>
                    </div>
                  )}

                  {updateStatus.status === 'error' && (
                    <div className="alert alert-error">
                      <FaExclamationTriangle />
                      <span>{updateStatus.error || t('system_update.update_failed')}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
