import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import axios from '@/api/axios';
import { FaSync, FaArrowUp, FaArrowDown, FaCopy, FaFilter, FaDiscord, FaBug } from 'react-icons/fa';
import { useTranslation } from '../hooks/useTranslation';

// Create formatter once, not on every function call
const dateFormatter = new Intl.DateTimeFormat('sv-SE', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false
});

const formatTimestamp = (timestamp: string): string => {
  // Check if timestamp is in microseconds (numeric)
  if (/^\d+$/.test(timestamp)) {
    // Convert microseconds to milliseconds
    const timestampMs = Math.floor(parseInt(timestamp) / 1000);
    return dateFormatter.format(timestampMs);
  }
  // Return as is if it's already formatted
  return timestamp;
};

interface LogEntry {
  timestamp: string;
  message: string;
  level: string;
}

const LOG_LEVELS: { value: string; label: string; color: string; activeColor: string }[] = [
  { value: '3', label: 'ERROR', color: 'var(--log-error)', activeColor: 'var(--log-error-bg)' },
  { value: '4', label: 'WARNING', color: 'var(--log-warning)', activeColor: 'var(--log-warning-bg)' },
  { value: '6', label: 'INFO', color: 'var(--log-info)', activeColor: 'transparent' },
  { value: '7', label: 'DEBUG', color: 'var(--log-debug)', activeColor: 'transparent' },
];

export default function LogViewer() {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [timeRange, setTimeRange] = useState('-15m');
  const [isLoading, setIsLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [isTopHalf, setIsTopHalf] = useState(true);
  const [selectedLogIndices, setSelectedLogIndices] = useState<Set<number>>(new Set());
  const [selectionStart, setSelectionStart] = useState<number | null>(null);
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectedModules, setSelectedModules] = useState<Set<string>>(new Set());
  const [moduleDropdownOpen, setModuleDropdownOpen] = useState(false);
  const moduleDropdownRef = useRef<HTMLDivElement>(null);
  const [selectedLevels, setSelectedLevels] = useState<Set<string>>(new Set());
  const [debugActive, setDebugActive] = useState(false);
  const [debugLoading, setDebugLoading] = useState(false);

  const fetchLogs = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await axios.get(`/api/logs?since=${timeRange}`);
      setLogs(response.data.logs);
    } catch (error) {
      console.error('Error fetching logs:', error);
    } finally {
      setIsLoading(false);
    }
  }, [timeRange]);

  const fetchLogLevel = useCallback(async () => {
    try {
      const response = await axios.get('/api/log-level');
      setDebugActive(response.data.debug_active);
    } catch (error) {
      console.error('Error fetching log level:', error);
    }
  }, []);

  const toggleDebug = useCallback(async () => {
    setDebugLoading(true);
    try {
      const newLevel = debugActive ? 'RESTORE' : 'DEBUG';
      await axios.post('/api/log-level', { level: newLevel });
      setDebugActive(!debugActive);
    } catch (error) {
      console.error('Error toggling debug:', error);
    } finally {
      setDebugLoading(false);
    }
  }, [debugActive]);

  useEffect(() => {
    fetchLogs();
    fetchLogLevel();
    
    if (autoRefresh) {
      const interval = setInterval(fetchLogs, 5000);
      return () => clearInterval(interval);
    }
  }, [fetchLogs, fetchLogLevel, autoRefresh]);

  // Close module dropdown when clicking outside + stop drag selection on global mouseup
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (moduleDropdownRef.current && !moduleDropdownRef.current.contains(e.target as Node)) {
        setModuleDropdownOpen(false);
      }
    };
    const handleGlobalMouseUp = () => setIsSelecting(false);
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('mouseup', handleGlobalMouseUp);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('mouseup', handleGlobalMouseUp);
    };
  }, []);

  /**
   * Extract module name from log message, e.g. "[boneio.webui.app]" -> "boneio.webui.app"
   */
  const extractModule = (message: string): string | null => {
    const match = message.match(/\[([\w.]+)\]/);
    return match ? match[1] : null;
  };

  /**
   * All unique modules found in current logs, sorted alphabetically
   */
  const availableModules = useMemo(() => {
    const modules = new Set<string>();
    for (const log of logs) {
      const mod = extractModule(log.message);
      if (mod) modules.add(mod);
    }
    return Array.from(modules).sort((a, b) => a.localeCompare(b));
  }, [logs]);

  /**
   * Normalize log level to match LOG_LEVELS values (0-3 -> '3', 4 -> '4', 6 -> '6', 7 -> '7')
   */
  const normalizeLevel = (level: string): string => {
    const num = parseInt(level);
    if (num <= 3) return '3';
    return level;
  };

  /**
   * Logs filtered by selected modules and log levels
   */
  const filteredLogs = useMemo(() => {
    return logs.filter(log => {
      if (selectedModules.size > 0) {
        const mod = extractModule(log.message);
        if (mod === null || !selectedModules.has(mod)) return false;
      }
      if (selectedLevels.size > 0) {
        if (!selectedLevels.has(normalizeLevel(log.level))) return false;
      }
      return true;
    });
  }, [logs, selectedModules, selectedLevels]);

  const toggleLevel = (level: string) => {
    setSelectedLevels(prev => {
      const next = new Set(prev);
      if (next.has(level)) {
        next.delete(level);
      } else {
        next.add(level);
      }
      return next;
    });
  };

  const toggleModule = (mod: string) => {
    setSelectedModules(prev => {
      const next = new Set(prev);
      if (next.has(mod)) {
        next.delete(mod);
      } else {
        next.add(mod);
      }
      return next;
    });
  };

  const getLogLevelStyle = (level: string): React.CSSProperties => {
    const levelNum = parseInt(level);
    switch (levelNum) {
      case 0: // emerg
      case 1: // alert
      case 2: // crit
      case 3: // err
        return { color: 'var(--log-error)' };
      case 4: // warning
        return { color: 'var(--log-warning)' };
      case 6: // info
        return { color: 'var(--log-info)' };
      case 7: // debug
        return { color: 'var(--log-debug)' };
      default:
        return {};
    }
  };

  const getLogRowStyle = (level: string): React.CSSProperties => {
    const levelNum = parseInt(level);
    switch (levelNum) {
      case 0: // emerg
      case 1: // alert
      case 2: // crit
      case 3: // err
        return { borderLeft: '2px solid var(--log-error-border)', backgroundColor: 'var(--log-error-bg)' };
      case 4: // warning
        return { borderLeft: '2px solid var(--log-warning-border)', backgroundColor: 'var(--log-warning-bg)' };
      default:
        return { borderLeft: '2px solid transparent' };
    }
  };

  const scrollToBottom = () => {
    if (logContainerRef.current && autoScroll) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  };

  const handleScroll = () => {
    if (logContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
      // If we're near the bottom (within 100px), enable auto-scroll
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      setAutoScroll(isNearBottom);
      
      // Check if we're in the top half of the content
      setIsTopHalf(scrollTop < (scrollHeight - clientHeight) / 2);
    }
  };

  const scrollToPosition = () => {
    if (logContainerRef.current) {
      logContainerRef.current.scroll({
        top: isTopHalf ? logContainerRef.current.scrollHeight : 0,
        behavior: 'smooth'
      });
    }
  };

  useEffect(() => {
    // Scroll to bottom when logs change
    scrollToBottom();
  }, [logs]);

  const handleLogSelection = (index: number, isShiftKey: boolean) => {
    if (!isShiftKey) {
      setSelectedLogIndices(new Set([index]));
      setSelectionStart(index);
    } else if (selectionStart !== null) {
      const start = Math.min(selectionStart, index);
      const end = Math.max(selectionStart, index);
      const newSelection = new Set<number>();
      for (let i = start; i <= end; i++) {
        newSelection.add(i);
      }
      setSelectedLogIndices(newSelection);
    }
  };

  const handleMouseMove = (index: number) => {
    if (isSelecting && selectionStart !== null) {
      handleLogSelection(index, true);
    }
  };

  const DISCORD_MAX_CHARS = 2000;
  const DISCORD_WRAPPER_CHARS = '```bash\n\n```'.length; // 12 chars for the code block wrapper

  /**
   * Build the raw text from selected log lines
   */
  const getSelectedLogsText = () => {
    return Array.from(selectedLogIndices)
      .sort((a, b) => a - b)
      .map(index => {
        const log = filteredLogs[index];
        return `${formatTimestamp(log.timestamp)} ${log.message}`;
      })
      .join('\n');
  };

  /**
   * Length of the Discord-formatted message for current selection
   */
  const discordMessageLength = useMemo(() => {
    if (selectedLogIndices.size === 0) return 0;
    const text = getSelectedLogsText();
    return text.length + DISCORD_WRAPPER_CHARS;
  }, [selectedLogIndices, filteredLogs]);

  const isDiscordOverLimit = discordMessageLength > DISCORD_MAX_CHARS;

  const handleCopyToClipboard = () => {
    const selectedLogs = getSelectedLogsText();

    navigator.clipboard.writeText(selectedLogs).then(() => {
      showToast(t('log_viewer.copied_clipboard'));
    });
  };

  const handleCopyForDiscord = () => {
    const selectedLogs = getSelectedLogsText();
    const discordFormatted = '```bash\n' + selectedLogs + '\n```';

    navigator.clipboard.writeText(discordFormatted).then(() => {
      showToast(t('log_viewer.copied_discord'));
    });
  };

  const showToast = (message: string) => {
    const toast = document.getElementById('toast') as HTMLDivElement;
    const toastText = document.getElementById('toast-text');
    if (toast && toastText) {
      toastText.textContent = message;
      toast.classList.remove('hidden');
      setTimeout(() => {
        toast.classList.add('hidden');
      }, 2000);
    }
  };

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col bg-base-100">
      <div className="bg-base-200 p-4 border-b border-base-content/10 flex items-center gap-4">
        <select 
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value)}
          className="select select-sm"
        >
          <option value="-15m">{t('log_viewer.last_15_minutes')}</option>
          <option value="-1h">{t('log_viewer.last_hour')}</option>
          <option value="-6h">{t('log_viewer.last_6_hours')}</option>
          <option value="-12h">{t('log_viewer.last_12_hours')}</option>
          <option value="-1d">{t('log_viewer.last_day')}</option>
          <option value="-7d">{t('log_viewer.last_week')}</option>
        </select>
        
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            className="toggle toggle-sm"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          <span className="text-sm">{t('log_viewer.auto_refresh')}</span>
        </label>

        <button
            className={`btn btn-sm ${autoScroll ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setAutoScroll(!autoScroll)}
          >
            {autoScroll ? t('log_viewer.auto_scroll_on') : t('log_viewer.auto_scroll_off')}
          </button>

        <div className="flex items-center gap-1">
          {LOG_LEVELS.map(level => (
            <button
              key={level.value}
              onClick={() => toggleLevel(level.value)}
              className={`btn btn-xs font-mono ${selectedLevels.has(level.value) ? '' : 'btn-ghost opacity-50'}`}
              style={selectedLevels.has(level.value) ? {
                color: level.color,
                borderColor: level.color,
                backgroundColor: level.activeColor,
              } : {}}
              title={level.label}
            >
              {level.label}
            </button>
          ))}
        </div>

        <div className="relative" ref={moduleDropdownRef}>
          <button
            onClick={() => setModuleDropdownOpen(!moduleDropdownOpen)}
            className={`btn btn-sm gap-1 ${selectedModules.size > 0 ? 'btn-primary' : 'btn-ghost'}`}
          >
            <FaFilter className="w-3 h-3" />
            {selectedModules.size > 0 ? t(selectedModules.size === 1 ? 'log_viewer.modules_count_one' : 'log_viewer.modules_count_other', { count: selectedModules.size }) : t('log_viewer.modules')}
          </button>
          {moduleDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 z-50 bg-base-100 border border-base-content/20 rounded-lg shadow-xl w-72 max-h-80 flex flex-col">
              <div className="p-2 border-b border-base-content/10 flex gap-1">
                <button
                  onClick={() => setSelectedModules(new Set(availableModules))}
                  className="btn btn-ghost btn-xs flex-1"
                >
                  {t('log_viewer.select_all')}
                </button>
                <button
                  onClick={() => setSelectedModules(new Set())}
                  className="btn btn-ghost btn-xs flex-1"
                >
                  {t('log_viewer.clear')}
                </button>
              </div>
              <div className="overflow-y-auto p-1">
                {availableModules.map(mod => (
                  <label
                    key={mod}
                    className="flex items-center gap-2 px-2 py-1 rounded cursor-pointer hover:bg-base-200 text-xs"
                  >
                    <input
                      type="checkbox"
                      className="checkbox checkbox-xs checkbox-primary"
                      checked={selectedModules.has(mod)}
                      onChange={() => toggleModule(mod)}
                    />
                    <span className="font-mono truncate">{mod}</span>
                  </label>
                ))}
                {availableModules.length === 0 && (
                  <div className="text-xs text-base-content/50 p-2 text-center">{t('log_viewer.no_modules_found')}</div>
                )}
              </div>
            </div>
          )}
        </div>

        <button
          onClick={toggleDebug}
          disabled={debugLoading}
          className={`btn btn-sm gap-1 ${debugActive ? 'btn-warning' : 'btn-ghost'}`}
          title={debugActive ? t('log_viewer.debug_disable') : t('log_viewer.debug_enable')}
        >
          <FaBug className={`w-3 h-3 ${debugLoading ? 'animate-pulse' : ''}`} />
          {debugActive ? t('log_viewer.debug_on') : t('log_viewer.debug_off')}
        </button>

        <button
          onClick={fetchLogs}
          disabled={isLoading}
          className="btn btn-sm btn-ghost"
        >
          <FaSync className={`${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div 
        ref={logContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-auto p-4 font-mono text-sm relative"
      >
        <div className="space-y-1">
          {filteredLogs.map((log, index) => (
            <div 
              key={index} 
              className={`flex gap-4 cursor-pointer px-2 rounded transition-colors ${
                selectedLogIndices.has(index)
                  ? '' 
                  : 'hover:bg-base-200'
              }`}
              style={
                selectedLogIndices.has(index)
                  ? { backgroundColor: 'var(--log-selected-bg)', color: 'var(--log-selected-text)' }
                  : getLogRowStyle(log.level)
              }
              onMouseDown={(e) => {
                e.preventDefault(); // Prevent default text selection
                if (e.shiftKey) {
                  // Shift+click: extend selection from selectionStart to this index
                  handleLogSelection(index, true);
                } else {
                  // Normal click: start new selection at this line
                  handleLogSelection(index, false);
                }
                setIsSelecting(true);
              }}
              onMouseEnter={() => handleMouseMove(index)}
              onMouseUp={() => setIsSelecting(false)}
            >
              <span
                className="whitespace-nowrap"
                style={{ color: selectedLogIndices.has(index) ? 'var(--log-selected-timestamp)' : 'var(--log-timestamp)' }}
              >
                {formatTimestamp(log.timestamp)}
              </span>
              <span
                className="flex-1 whitespace-pre-wrap"
                style={selectedLogIndices.has(index) ? { color: 'var(--log-selected-text)' } : getLogLevelStyle(log.level)}
              >
                {log.message}
              </span>
            </div>
          ))}
        </div>
        <div className="fixed bottom-6 right-6 flex flex-col items-end gap-2">
          {/* Discord limit warning */}
          {selectedLogIndices.size > 0 && isDiscordOverLimit && (
            <div className="text-xs text-base-content/40 bg-base-200 rounded px-2 py-1 shadow">
              {t('log_viewer.discord_max_chars', { max: DISCORD_MAX_CHARS, current: discordMessageLength })}
            </div>
          )}
          <div className="flex gap-2">
            {/* Share to Discord */}
            <button
              onClick={handleCopyForDiscord}
              disabled={selectedLogIndices.size === 0 || isDiscordOverLimit}
              className={`btn btn-circle btn-sm shadow-lg hover:shadow-xl ${
                selectedLogIndices.size > 0 && !isDiscordOverLimit
                  ? 'bg-[#5865F2] hover:bg-[#4752C4] text-white border-none'
                  : 'bg-base-200'
              }`}
              title={isDiscordOverLimit ? t('log_viewer.discord_max_chars', { max: DISCORD_MAX_CHARS, current: discordMessageLength }) : t('log_viewer.share_discord')}
            >
              <FaDiscord />
            </button>
            {/* Copy */}
            <button
              onClick={handleCopyToClipboard}
              disabled={selectedLogIndices.size === 0}
              className="btn btn-circle btn-sm bg-base-200 shadow-lg hover:shadow-xl"
              title={t('log_viewer.copy_selected')}
            >
              <FaCopy />
            </button>
            {/* Scroll */}
            <button
              onClick={scrollToPosition}
              className="btn btn-circle btn-sm bg-base-200 shadow-lg hover:shadow-xl"
              title={isTopHalf ? t('log_viewer.scroll_to_bottom') : t('log_viewer.scroll_to_top')}
            >
              {isTopHalf ? <FaArrowDown /> : <FaArrowUp />}
            </button>
          </div>
        </div>
        <div id="toast" className="toast toast-end hidden">
          <div className="alert alert-success">
            <span id="toast-text">Copied to clipboard!</span>
          </div>
        </div>
      </div>
    </div>
  );
}
