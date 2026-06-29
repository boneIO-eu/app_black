import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import axios from '@/api/axios';
import { FaSync, FaArrowUp, FaArrowDown, FaCopy, FaFilter, FaEyeSlash, FaSearch, FaDiscord, FaBug, FaCalendarAlt } from 'react-icons/fa';
import { useTranslation } from '../hooks/useTranslation';
import { copyToClipboard } from '@/utils/clipboard';

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

/**
 * Aggregated log entry — collapses consecutive identical messages
 * into a single entry with a repeat count (like Home Assistant).
 */
interface AggregatedLog {
  /** First occurrence timestamp */
  timestamp: string;
  /** Last occurrence timestamp (differs from timestamp when count > 1) */
  lastTimestamp: string;
  message: string;
  level: string;
  /** Number of consecutive identical messages collapsed into this entry */
  count: number;
}

const LOG_LEVELS: { value: string; label: string; color: string; activeColor: string }[] = [
  { value: '3', label: 'ERROR', color: 'var(--log-error)', activeColor: 'var(--log-error-bg)' },
  { value: '4', label: 'WARNING', color: 'var(--log-warning)', activeColor: 'var(--log-warning-bg)' },
  { value: '6', label: 'INFO', color: 'var(--log-info)', activeColor: 'transparent' },
  { value: '7', label: 'DEBUG', color: 'var(--log-debug)', activeColor: 'transparent' },
];

const LOGS_PAGE_SIZE = 200;

export default function LogViewer() {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [isTopHalf, setIsTopHalf] = useState(true);
  const [selectedLogIndices, setSelectedLogIndices] = useState<Set<number>>(new Set());
  const [selectionStart, setSelectionStart] = useState<number | null>(null);
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectedModules, setSelectedModules] = useState<Set<string>>(new Set());
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressTriggered = useRef(false);
  const [moduleDropdownOpen, setModuleDropdownOpen] = useState(false);
  const moduleDropdownRef = useRef<HTMLDivElement>(null);
  const [excludedModules, setExcludedModules] = useState<Set<string>>(new Set());
  const [excludeDropdownOpen, setExcludeDropdownOpen] = useState(false);
  const excludeDropdownRef = useRef<HTMLDivElement>(null);
  const [selectedLevels, setSelectedLevels] = useState<Set<string>>(new Set());
  const [debugActive, setDebugActive] = useState(false);
  const [debugLoading, setDebugLoading] = useState(false);
  const [logSource, setLogSource] = useState<'systemd' | 'standalone' | null>(null);
  const [serverPriority, setServerPriority] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [dateFilterOpen, setDateFilterOpen] = useState(false);
  const dateFilterRef = useRef<HTMLDivElement>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedGrep, setDebouncedGrep] = useState('');
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isSystemd = logSource === 'systemd';

  /**
   * Build query string for log API requests with current filter state.
   */
  const buildLogParams = useCallback((extra: Record<string, string> = {}) => {
    const params = new URLSearchParams();
    params.set('limit', String(LOGS_PAGE_SIZE));
    if (serverPriority) params.set('priority', serverPriority);
    if (dateFrom) params.set('since', dateFrom);
    if (dateTo) params.set('until', dateTo);
    if (debouncedGrep) params.set('grep', debouncedGrep);
    for (const [k, v] of Object.entries(extra)) {
      if (v) params.set(k, v);
    }
    return params.toString();
  }, [serverPriority, dateFrom, dateTo, debouncedGrep]);

  const fetchLogs = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await axios.get(`/api/logs?${buildLogParams()}`, { timeout: 30000 });
      setLogs(response.data.logs);
      setHasMore(response.data.has_more);
      setLogSource(response.data.source || 'standalone');
    } catch (error) {
      console.error('Error fetching logs:', error);
    } finally {
      setIsLoading(false);
    }
  }, [buildLogParams]);

  const fetchOlderLogs = useCallback(async () => {
    if (isLoadingMore || !hasMore || logs.length === 0) return;
    const oldestTimestamp = logs[0]?.timestamp;
    if (!oldestTimestamp) return;

    try {
      setIsLoadingMore(true);
      const container = logContainerRef.current;
      const prevScrollHeight = container?.scrollHeight || 0;

      const response = await axios.get(
        `/api/logs?${buildLogParams({ before: oldestTimestamp })}`,
        { timeout: 30000 }
      );
      const olderLogs: LogEntry[] = response.data.logs;
      setHasMore(response.data.has_more);

      if (olderLogs.length > 0) {
        setLogs(prev => [...olderLogs, ...prev]);
        // Preserve scroll position after prepending
        requestAnimationFrame(() => {
          if (container) {
            const newScrollHeight = container.scrollHeight;
            container.scrollTop += newScrollHeight - prevScrollHeight;
          }
        });
      }
    } catch (error) {
      console.error('Error fetching older logs:', error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, hasMore, logs, buildLogParams]);

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
  }, []);

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(fetchLogs, 5000);
      return () => clearInterval(interval);
    }
  }, [fetchLogs, autoRefresh]);

  // Close dropdowns when clicking outside + stop drag selection on global mouseup
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (moduleDropdownRef.current && !moduleDropdownRef.current.contains(e.target as Node)) {
        setModuleDropdownOpen(false);
      }
      if (excludeDropdownRef.current && !excludeDropdownRef.current.contains(e.target as Node)) {
        setExcludeDropdownOpen(false);
      }
      if (dateFilterRef.current && !dateFilterRef.current.contains(e.target as Node)) {
        setDateFilterOpen(false);
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
   * Create a normalised "fingerprint" of a log message for fuzzy matching.
   * Strips parts that change between otherwise-identical repetitions:
   *   - thread names in parentheses, e.g. "(modbus_worker_0)" → "(…)"
   *   - ISO-ish timestamps and bare numbers that look like durations / IDs
   */
  const fingerprint = useCallback((msg: string): string => {
    return msg
      // Strip thread name: "(MainThread)" / "(modbus_worker_0)" → "(…)"
      .replace(/\([A-Za-z_]+[\w]*\)/g, '(…)')
      // Strip float durations like "45.0 seconds" → "… seconds"
      .replace(/\d+\.\d+\s*(seconds?|s\b)/gi, '… $1')
      // Keep the rest — module names, actual error text, etc.
      ;
  }, []);

  /**
   * Logs filtered by selected modules and log levels, then aggregated.
   *
   * Aggregation works in two passes:
   *  1. Consecutive lines with identical (level, fingerprint) are collapsed
   *     (original behaviour, covers the simple case).
   *  2. Repeating *sequences* of N lines (N = 2..5) are detected and collapsed.
   *     E.g. [ERROR, WARNING, ERROR, WARNING, …] where each pair has the same
   *     fingerprints → shown once with ×count.
   */
  const filteredLogs = useMemo((): AggregatedLog[] => {
    const filtered = logs.filter(log => {
      if (selectedModules.size > 0) {
        const mod = extractModule(log.message);
        if (mod === null || !selectedModules.has(mod)) return false;
      }
      if (excludedModules.size > 0) {
        const mod = extractModule(log.message);
        if (mod !== null && excludedModules.has(mod)) return false;
      }
      if (selectedLevels.size > 0) {
        if (!selectedLevels.has(normalizeLevel(log.level))) return false;
      }
      return true;
    });

    // --- Pass 1: collapse identical consecutive lines (fast path) ----------
    const pass1: AggregatedLog[] = [];
    for (const log of filtered) {
      const last = pass1[pass1.length - 1];
      if (last && last.message === log.message && last.level === log.level) {
        last.count += 1;
        last.lastTimestamp = log.timestamp;
      } else {
        pass1.push({
          timestamp: log.timestamp,
          lastTimestamp: log.timestamp,
          message: log.message,
          level: log.level,
          count: 1,
        });
      }
    }

    // --- Pass 2: detect repeating sequences (seqLen = 2..5) ----------------
    // Build fingerprint keys once
    const keys = pass1.map(e => `${e.level}\x00${fingerprint(e.message)}`);

    /**
     * Check if a sequence of length `seqLen` starting at `start` repeats
     * at `start + seqLen`. Returns the number of consecutive full repetitions
     * (minimum 1 = the original, so 2 means one repeat).
     */
    const countSequenceRepeats = (start: number, seqLen: number): number => {
      let reps = 1;
      let pos = start + seqLen;
      while (pos + seqLen <= keys.length) {
        let match = true;
        for (let j = 0; j < seqLen; j++) {
          if (keys[pos + j] !== keys[start + j]) {
            match = false;
            break;
          }
        }
        if (!match) break;
        reps++;
        pos += seqLen;
      }
      return reps;
    };

    const result: AggregatedLog[] = [];
    let i = 0;
    while (i < pass1.length) {
      let collapsed = false;

      // Try sequence lengths 2..5 (longest first for greedier grouping)
      for (let seqLen = 5; seqLen >= 2; seqLen--) {
        if (i + seqLen * 2 > pass1.length) continue; // not enough room

        const reps = countSequenceRepeats(i, seqLen);
        if (reps >= 2) {
          // Collapse: keep the first occurrence of each line in the sequence,
          // but multiply their counts by the number of repetitions.
          for (let j = 0; j < seqLen; j++) {
            const entry = pass1[i + j];
            const totalCount = entry.count * reps;
            // Find last timestamp across all repetitions for this slot
            const lastEntry = pass1[i + (reps - 1) * seqLen + j];
            result.push({
              ...entry,
              count: totalCount,
              lastTimestamp: lastEntry.lastTimestamp,
            });
          }
          i += seqLen * reps;
          collapsed = true;
          break;
        }
      }

      if (!collapsed) {
        result.push(pass1[i]);
        i++;
      }
    }

    return result;
  }, [logs, selectedModules, excludedModules, selectedLevels, fingerprint]);

  // Clear selection when filter criteria change (indices become stale)
  useEffect(() => {
    setSelectedLogIndices(new Set());
    setSelectionStart(null);
  }, [selectedModules, excludedModules, selectedLevels]);

  const toggleLevel = (level: string) => {
    if (isSystemd) {
      // Server-side: toggle priority filter and re-fetch
      // journalctl --priority shows entries at that level and above (more critical)
      // Map: '3' = err+crit+alert+emerg, '4' = warning+above, '6' = info+above, '7' = debug+above (all)
      setServerPriority(prev => prev === level ? null : level);
    } else {
      // Client-side: toggle local filter
      setSelectedLevels(prev => {
        const next = new Set(prev);
        if (next.has(level)) {
          next.delete(level);
        } else {
          next.add(level);
        }
        return next;
      });
    }
  };

  // Re-fetch when server-side filters change (priority or grep)
  useEffect(() => {
    if (logSource !== null) {
      fetchLogs();
    }
  }, [serverPriority, debouncedGrep]);

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

  const toggleExcludedModule = (mod: string) => {
    setExcludedModules(prev => {
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

      // Load older logs when scrolled near top
      if (scrollTop < 200 && hasMore && !isLoadingMore) {
        fetchOlderLogs();
      }
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
      .filter(index => index < filteredLogs.length)
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

    copyToClipboard(selectedLogs).then(() => {
      showToast(t('log_viewer.copied_clipboard'));
    });
  };

  const handleCopyForDiscord = () => {
    const selectedLogs = getSelectedLogsText();
    const discordFormatted = '```bash\n' + selectedLogs + '\n```';

    copyToClipboard(discordFormatted).then(() => {
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
    <div className="h-[calc(100vh-8rem)] flex flex-col bg-base-100 overflow-hidden">
      <div className="bg-base-200 p-2 sm:p-4 border-b border-base-content/10 flex flex-wrap items-center gap-2 sm:gap-4">
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

        <div className="flex items-center gap-1" title={!isSystemd && logSource !== null ? t('log_viewer.filter_client_only') : ''}>
          {LOG_LEVELS.map(level => {
            const isActive = isSystemd
              ? serverPriority === level.value
              : selectedLevels.has(level.value);
            return (
              <button
                key={level.value}
                onClick={() => toggleLevel(level.value)}
                className={`btn btn-xs font-mono ${isActive ? '' : 'btn-ghost opacity-50'}`}
                style={isActive ? {
                  color: level.color,
                  borderColor: level.color,
                  backgroundColor: level.activeColor,
                } : {}}
                title={isSystemd
                  ? `${level.label} (${t('log_viewer.filter_server')})`
                  : logSource === null
                    ? level.label
                    : `${level.label} (${t('log_viewer.filter_client_only')})`
                }
              >
                {level.label}
              </button>
            );
          })}
        </div>

        <div className="relative flex items-center">
          <FaSearch className="absolute left-2 w-3 h-3 text-base-content/40 pointer-events-none" />
          <input
            type="text"
            className="input input-sm input-bordered pl-7 w-36 sm:w-48 font-mono text-xs"
            placeholder={t('log_viewer.search_placeholder')}
            value={searchQuery}
            onChange={(e) => {
              const val = e.target.value;
              setSearchQuery(val);
              if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
              searchDebounceRef.current = setTimeout(() => {
                setDebouncedGrep(val.trim());
              }, 600);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
                setDebouncedGrep(searchQuery.trim());
              }
            }}
          />
          {searchQuery && (
            <button
              onClick={() => {
                setSearchQuery('');
                if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
                setDebouncedGrep('');
              }}
              className="absolute right-1 btn btn-ghost btn-xs px-1 text-base-content/40 hover:text-base-content"
            >
              ✕
            </button>
          )}
        </div>

        <div className="relative" ref={dateFilterRef}>
          <button
            onClick={() => setDateFilterOpen(!dateFilterOpen)}
            className={`btn btn-sm gap-1 ${dateFrom || dateTo ? 'btn-primary' : 'btn-ghost'}`}
            title={t('log_viewer.date_range')}
          >
            <FaCalendarAlt className="w-3 h-3" />
            {dateFrom || dateTo ? t('log_viewer.date_active') : t('log_viewer.date_range')}
          </button>
          {dateFilterOpen && (
            <div className="absolute top-full left-0 mt-1 z-50 bg-base-100 border border-base-content/20 rounded-lg shadow-xl p-3 w-72 flex flex-col gap-2">
              <label className="text-xs font-semibold text-base-content/70">{t('log_viewer.date_from')}</label>
              <input
                type="datetime-local"
                className="input input-sm input-bordered w-full"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
              <label className="text-xs font-semibold text-base-content/70">{t('log_viewer.date_to')}</label>
              <input
                type="datetime-local"
                className="input input-sm input-bordered w-full"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
              <div className="flex gap-1 mt-1">
                <button
                  onClick={() => { fetchLogs(); setDateFilterOpen(false); }}
                  className="btn btn-sm btn-primary flex-1"
                >
                  {t('log_viewer.date_apply')}
                </button>
                <button
                  onClick={() => { setDateFrom(''); setDateTo(''); }}
                  className="btn btn-sm btn-ghost flex-1"
                >
                  {t('log_viewer.clear')}
                </button>
              </div>
            </div>
          )}
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

        <div className="relative" ref={excludeDropdownRef}>
          <button
            onClick={() => setExcludeDropdownOpen(!excludeDropdownOpen)}
            className={`btn btn-sm gap-1 ${excludedModules.size > 0 ? 'btn-error btn-outline' : 'btn-ghost'}`}
          >
            <FaEyeSlash className="w-3 h-3" />
            {excludedModules.size > 0 ? t(excludedModules.size === 1 ? 'log_viewer.excluded_count_one' : 'log_viewer.excluded_count_other', { count: excludedModules.size }) : t('log_viewer.exclude_modules')}
          </button>
          {excludeDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 z-50 bg-base-100 border border-base-content/20 rounded-lg shadow-xl w-72 max-h-80 flex flex-col">
              <div className="p-2 border-b border-base-content/10 flex gap-1">
                <button
                  onClick={() => setExcludedModules(new Set())}
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
                      className="checkbox checkbox-xs checkbox-error"
                      checked={excludedModules.has(mod)}
                      onChange={() => toggleExcludedModule(mod)}
                    />
                    <span className={`font-mono truncate ${excludedModules.has(mod) ? 'line-through opacity-50' : ''}`}>{mod}</span>
                  </label>
                ))}
                {availableModules.length === 0 && (
                  <div className="text-xs text-base-content/50 p-2 text-center">{t('log_viewer.no_modules_found')}</div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="relative group">
          <button
            onClick={toggleDebug}
            disabled={debugLoading}
            className={`btn btn-sm gap-1 ${debugActive ? 'btn-warning' : 'btn-ghost'}`}
            title={debugActive ? t('log_viewer.debug_disable') : t('log_viewer.debug_enable')}
          >
            <FaBug className={`w-3 h-3 ${debugLoading ? 'animate-pulse' : ''}`} />
            {debugActive ? t('log_viewer.debug_on') : t('log_viewer.debug_off')}
          </button>
          {debugActive && (
            <div className="absolute top-full left-0 mt-1 z-50 hidden group-hover:block bg-warning text-warning-content text-xs rounded px-2 py-1 shadow-lg whitespace-nowrap">
              {t('log_viewer.debug_warning')}
            </div>
          )}
        </div>

        <span className="text-xs text-base-content/50 ml-auto">
          {t('log_viewer.log_count', { count: logs.length })}
        </span>

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
        className="flex-1 overflow-auto p-2 sm:p-4 font-mono text-xs sm:text-sm relative min-w-0"
      >
        {isLoading && logs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <span className="loading loading-spinner loading-lg text-primary"></span>
            <span className="text-sm text-base-content/50">{t('log_viewer.loading')}</span>
          </div>
        )}
        {isLoadingMore && (
          <div className="flex justify-center py-2">
            <span className="loading loading-spinner loading-sm"></span>
            <span className="ml-2 text-sm text-base-content/50">{t('log_viewer.loading_older')}</span>
          </div>
        )}
        {hasMore && !isLoadingMore && (
          <div className="flex justify-center py-2">
            <button
              onClick={fetchOlderLogs}
              className="btn btn-ghost btn-xs text-base-content/50"
            >
              {t('log_viewer.load_more')}
            </button>
          </div>
        )}
        <div className="space-y-1">
          {filteredLogs.map((log, index) => (
            <div 
              key={index} 
              className={`flex gap-2 sm:gap-4 cursor-pointer px-1 sm:px-2 rounded transition-colors ${
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
                longPressTriggered.current = false;
                longPressTimer.current = setTimeout(() => {
                  longPressTriggered.current = true;
                  copyToClipboard(log.message).then(() => {
                    showToast(t('log_viewer.copied_line'));
                  });
                }, 500);
                if (e.shiftKey) {
                  handleLogSelection(index, true);
                } else {
                  handleLogSelection(index, false);
                }
                setIsSelecting(true);
              }}
              onMouseEnter={() => {
                handleMouseMove(index);
                if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null; }
              }}
              onMouseUp={() => {
                if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null; }
                setIsSelecting(false);
              }}
              onTouchStart={() => {
                longPressTriggered.current = false;
                longPressTimer.current = setTimeout(() => {
                  longPressTriggered.current = true;
                  copyToClipboard(log.message).then(() => {
                    showToast(t('log_viewer.copied_line'));
                  });
                }, 500);
              }}
              onTouchEnd={() => {
                if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null; }
              }}
              onTouchMove={() => {
                if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null; }
              }}
            >
              <span
                className="whitespace-nowrap shrink-0 hidden sm:inline"
                style={{ color: selectedLogIndices.has(index) ? 'var(--log-selected-timestamp)' : 'var(--log-timestamp)' }}
              >
                {formatTimestamp(log.timestamp)}
              </span>
              <span
                className="whitespace-nowrap shrink-0 sm:hidden"
                style={{ color: selectedLogIndices.has(index) ? 'var(--log-selected-timestamp)' : 'var(--log-timestamp)' }}
              >
                {formatTimestamp(log.timestamp).split(' ')[1] || formatTimestamp(log.timestamp)}
              </span>
              <span
                className="flex-1 whitespace-pre-wrap break-all min-w-0"
                style={selectedLogIndices.has(index) ? { color: 'var(--log-selected-text)' } : getLogLevelStyle(log.level)}
              >
                {log.message}
              </span>
              {log.count > 1 && (
                <span
                  className="shrink-0 self-center badge badge-sm font-mono opacity-80"
                  style={{
                    backgroundColor: 'var(--log-error-bg, oklch(0.3 0.05 25))',
                    color: 'var(--log-error, oklch(0.8 0.15 25))',
                    borderColor: 'var(--log-error-border, oklch(0.5 0.1 25))',
                  }}
                  title={log.count > 1 && log.timestamp !== log.lastTimestamp
                    ? `${formatTimestamp(log.timestamp)} — ${formatTimestamp(log.lastTimestamp)}`
                    : undefined
                  }
                >
                  ×{log.count}
                </span>
              )}
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
