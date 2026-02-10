import { useState, useEffect, useCallback, useRef } from 'react';
import axios from '@/api/axios';
import { FaSync, FaArrowUp, FaArrowDown, FaCopy } from 'react-icons/fa';

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

export default function LogViewer() {
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

  useEffect(() => {
    fetchLogs();
    
    if (autoRefresh) {
      const interval = setInterval(fetchLogs, 5000);
      return () => clearInterval(interval);
    }
  }, [fetchLogs, autoRefresh]);

  const getLogLevelClass = (level: string) => {
    const levelNum = parseInt(level);
    switch (levelNum) {
      case 0: // emerg
      case 1: // alert
      case 2: // crit
      case 3: // err
        return 'text-error';
      case 4: // warning
        return 'text-warning';
      case 6: // info
        return 'text-info';
      case 7: // debug
        return 'text-success';
      default:
        return 'text-base-content';
    }
  };

  const getLogRowClass = (level: string) => {
    const levelNum = parseInt(level);
    switch (levelNum) {
      case 0: // emerg
      case 1: // alert
      case 2: // crit
      case 3: // err
        return 'border-l-2 border-l-error bg-error/5';
      case 4: // warning
        return 'border-l-2 border-l-warning bg-warning/5';
      default:
        return 'border-l-2 border-l-transparent';
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

  const handleCopyToClipboard = () => {
    const selectedLogs = Array.from(selectedLogIndices)
      .sort((a, b) => a - b)
      .map(index => {
        const log = logs[index];
        return `${formatTimestamp(log.timestamp)} ${log.message}`;
      })
      .join('\n');

    navigator.clipboard.writeText(selectedLogs).then(() => {
      // Show toast notification
      const toast = document.getElementById('toast') as HTMLDivElement;
      if (toast) {
        toast.classList.remove('hidden');
        setTimeout(() => {
          toast.classList.add('hidden');
        }, 2000);
      }
    });
  };

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col bg-base-100">
      <div className="bg-base-200 p-4 border-b border-base-content/10 flex items-center gap-4">
        <select 
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value)}
          className="select select-sm"
        >
          <option value="-15m">Last 15 minutes</option>
          <option value="-1h">Last hour</option>
          <option value="-6h">Last 6 hours</option>
          <option value="-12h">Last 12 hours</option>
          <option value="-1d">Last day</option>
          <option value="-7d">Last week</option>
        </select>
        
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            className="toggle toggle-sm"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          <span className="text-sm">Auto-refresh</span>
        </label>

        <button
            className={`btn btn-sm ${autoScroll ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setAutoScroll(!autoScroll)}
          >
            {autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
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
          {logs.map((log, index) => (
            <div 
              key={index} 
              className={`flex gap-4 cursor-pointer px-2 rounded transition-colors ${
                selectedLogIndices.has(index)
                  ? 'bg-primary/20 hover:bg-primary/30' 
                  : `hover:bg-base-200 ${getLogRowClass(log.level)}`
              }`}
              onClick={(e) => {
                handleLogSelection(index, e.shiftKey);
              }}
              onMouseDown={(e) => {
                if (e.shiftKey) {
                  e.preventDefault(); // Prevent default text selection
                  setIsSelecting(true);
                  handleLogSelection(index, true);
                }
              }}
              onMouseEnter={() => handleMouseMove(index)}
              onMouseUp={() => setIsSelecting(false)}
            >
              <span className={`text-base-content/70 whitespace-nowrap ${
                selectedLogIndices.has(index) ? 'text-primary-content' : ''
              }`}>
                {formatTimestamp(log.timestamp)}
              </span>
              <span className={`${getLogLevelClass(log.level)} flex-1 whitespace-pre-wrap ${
                selectedLogIndices.has(index) ? 'text-primary-content' : ''
              }`}>
                {log.message}
              </span>
            </div>
          ))}
        </div>
        <button
          id="copy-button"
          onClick={handleCopyToClipboard}
          disabled={selectedLogIndices.size === 0}
          className="btn btn-circle btn-sm fixed bottom-20 right-6 bg-base-200 shadow-lg hover:shadow-xl"
          title="Copy selected logs"
        >
          <FaCopy />
        </button>
        <button
          onClick={scrollToPosition}
          className="btn btn-circle btn-sm fixed bottom-6 right-6 bg-base-200 shadow-lg hover:shadow-xl"
          title={isTopHalf ? "Scroll to bottom" : "Scroll to top"}
        >
          {isTopHalf ? <FaArrowDown /> : <FaArrowUp />}
        </button>
        <div id="toast" className="toast toast-end hidden">
          <div className="alert alert-success">
            <span>Copied to clipboard!</span>
          </div>
        </div>
      </div>
    </div>
  );
}
