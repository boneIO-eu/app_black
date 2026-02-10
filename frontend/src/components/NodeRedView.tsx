import { useState } from 'react';
import { FaExternalLinkAlt, FaExpand, FaCompress } from 'react-icons/fa';
import { getBasePath } from '../api/basePath';

/**
 * Component that displays Node-RED editor in an iframe.
 * Only shown when Node-RED is available via nginx reverse proxy.
 */
export default function NodeRedView() {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const basePath = getBasePath();

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  const openInNewTab = () => {
    window.open(`${basePath}/nodered/`, '_blank');
  };

  return (
    <div className={`flex flex-col ${isFullscreen ? 'fixed inset-0 z-50 bg-base-100' : 'h-full'}`}>
      <div className="flex items-center justify-between p-2 bg-base-200 border-b border-base-300">
        <h2 className="text-lg font-semibold">Node-RED</h2>
        <div className="flex gap-2">
          <button
            onClick={openInNewTab}
            className="btn btn-sm btn-ghost"
            title="Open in new tab"
          >
            <FaExternalLinkAlt className="h-4 w-4" />
          </button>
          <button
            onClick={toggleFullscreen}
            className="btn btn-sm btn-ghost"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? (
              <FaCompress className="h-4 w-4" />
            ) : (
              <FaExpand className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
      <iframe
        src={`${basePath}/nodered/`}
        className="flex-1 w-full border-0"
        style={{ minHeight: isFullscreen ? 'calc(100vh - 48px)' : 'calc(100vh - 150px)' }}
        title="Node-RED Editor"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}
