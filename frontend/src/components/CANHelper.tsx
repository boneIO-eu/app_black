import { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  FaPlay,
  FaStop,
  FaCopy,
  FaTrash,
  FaPaperPlane,
  FaPlug,
  FaSpinner,
  FaCheck,
  FaExclamationTriangle,
  FaHeartbeat,
  FaBroadcastTower,
} from 'react-icons/fa';
import axios from '@/api/axios';
import { copyToClipboard } from '@/utils/clipboard';

interface CANStatus {
  interface: string;
  is_up: boolean;
  exists: boolean;
  bitrate: number | null;
  details: string;
}

export default function CANHelper() {
  const { t: _t } = useTranslation();

  // Interface state
  const [canInterface, setCanInterface] = useState('can0');
  const [bitrate, setBitrate] = useState(125000);
  const [sudoPassword, setSudoPassword] = useState('');
  const [status, setStatus] = useState<CANStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [ifUpResult, setIfUpResult] = useState<{ status: string; message: string } | null>(null);
  const [ifUpLoading, setIfUpLoading] = useState(false);

  // candump state
  const [dumpRunning, setDumpRunning] = useState(false);
  const [dumpDuration, setDumpDuration] = useState(30);
  const [dumpLines, setDumpLines] = useState<string[]>([]);
  const dumpAbortRef = useRef<AbortController | null>(null);
  const dumpEndRef = useRef<HTMLDivElement | null>(null);
  const [dumpCopied, setDumpCopied] = useState(false);

  // cansend state
  const [sendFrame, setSendFrame] = useState('');
  const [sendResult, setSendResult] = useState<{ status: string; message: string } | null>(null);
  const [sendLoading, setSendLoading] = useState(false);

  // Auto-scroll candump output
  useEffect(() => {
    if (dumpEndRef.current && dumpRunning) {
      dumpEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [dumpLines, dumpRunning]);

  // Check CAN interface status
  const checkStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const { data } = await axios.get(`/api/can/status?interface=${canInterface}`);
      setStatus(data);
    } catch (err) {
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  }, [canInterface]);

  // Check status on mount and interface change
  useEffect(() => {
    checkStatus();
  }, [checkStatus]);

  // Bring interface up
  const handleInterfaceUp = useCallback(async () => {
    if (!sudoPassword) return;
    setIfUpLoading(true);
    setIfUpResult(null);
    try {
      const { data } = await axios.post('/api/can/interface-up', {
        interface: canInterface,
        bitrate,
        password: sudoPassword,
      });
      setIfUpResult(data);
      if (data.status === 'success') {
        setSudoPassword('');
        checkStatus();
      }
    } catch (err: any) {
      setIfUpResult({ status: 'error', message: err.message || 'Request failed' });
    } finally {
      setIfUpLoading(false);
    }
  }, [canInterface, bitrate, sudoPassword, checkStatus]);

  // Start candump SSE stream
  const startDump = useCallback(() => {
    setDumpLines([]);
    setDumpRunning(true);

    const controller = new AbortController();
    dumpAbortRef.current = controller;

    const baseUrl = axios.defaults.baseURL || '';
    const url = `${baseUrl}/api/can/dump?interface=${canInterface}&duration=${dumpDuration}`;

    fetch(url, {
      signal: controller.signal,
      credentials: 'include',
    })
      .then(async (response) => {
        const reader = response.body?.getReader();
        if (!reader) {
          setDumpRunning(false);
          return;
        }
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split('\n');
          buffer = parts.pop() || '';

          for (const part of parts) {
            const trimmed = part.trim();
            if (trimmed.startsWith('data: ')) {
              const payload = trimmed.slice(6);
              if (payload === '[DONE]') {
                setDumpRunning(false);
                return;
              }
              setDumpLines((prev) => [...prev, payload]);
            }
          }
        }
        setDumpRunning(false);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setDumpLines((prev) => [...prev, `[ERROR] ${err.message}`]);
        }
        setDumpRunning(false);
      });
  }, [canInterface, dumpDuration]);

  // Stop candump
  const stopDump = useCallback(() => {
    dumpAbortRef.current?.abort();
    dumpAbortRef.current = null;
    setDumpRunning(false);
  }, []);

  // Copy dump output
  const handleCopyDump = () => {
    copyToClipboard(dumpLines.join('\n')).then(() => {
      setDumpCopied(true);
      setTimeout(() => setDumpCopied(false), 2000);
    });
  };

  // Send CAN frame
  const handleSend = useCallback(async () => {
    if (!sendFrame) return;
    setSendLoading(true);
    setSendResult(null);
    try {
      const { data } = await axios.post('/api/can/send', {
        interface: canInterface,
        frame: sendFrame,
      });
      setSendResult(data);
    } catch (err: any) {
      setSendResult({ status: 'error', message: err.response?.data?.detail || err.message });
    } finally {
      setSendLoading(false);
    }
  }, [canInterface, sendFrame]);

  // Quick-send presets
  const presets = [
    {
      label: 'Heartbeat (node 1)',
      icon: <FaHeartbeat className="w-3 h-3" />,
      frame: '701#05',
      hint: 'NMT Operational heartbeat, COB-ID 0x701',
    },
    {
      label: 'Discovery blk',
      icon: <FaBroadcastTower className="w-3 h-3" />,
      frame: '7FF#446973636F766572', // "Discover" in ASCII hex
      hint: 'Broadcast discovery message on COB-ID 0x7FF',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Interface Status & Configuration */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h2 className="card-title text-lg">
            <FaPlug className="text-primary" /> CAN Interface
          </h2>

          <div className="flex flex-wrap items-end gap-4">
            <div className="form-control">
              <label className="label">
                <span className="label-text">Interface</span>
              </label>
              <select
                className="select select-bordered select-sm"
                value={canInterface}
                onChange={(e) => setCanInterface(e.target.value)}
              >
                <option value="can0">can0</option>
                <option value="can1">can1</option>
                <option value="vcan0">vcan0 (virtual)</option>
              </select>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text">Bitrate</span>
              </label>
              <select
                className="select select-bordered select-sm"
                value={bitrate}
                onChange={(e) => setBitrate(parseInt(e.target.value))}
              >
                <option value={125000}>125 kbps (boneIO default)</option>
                <option value={250000}>250 kbps</option>
                <option value={500000}>500 kbps</option>
                <option value={1000000}>1 Mbps</option>
              </select>
            </div>

            <button
              className={`btn btn-sm btn-ghost gap-1 ${statusLoading ? 'loading' : ''}`}
              onClick={checkStatus}
              disabled={statusLoading}
            >
              Status
            </button>
          </div>

          {/* Status badge */}
          {status && (
            <div className="mt-3">
              {status.is_up ? (
                <div className="badge badge-success gap-1">
                  <FaCheck className="w-3 h-3" /> {canInterface} UP
                  {status.bitrate && ` @ ${status.bitrate / 1000} kbps`}
                </div>
              ) : (
                <div className="badge badge-error gap-1">
                  <FaExclamationTriangle className="w-3 h-3" /> {canInterface}{' '}
                  {status.exists ? 'DOWN' : 'not found'}
                </div>
              )}
            </div>
          )}

          {/* Bring up section */}
          {status && !status.is_up && (
            <div className="mt-3 p-3 bg-base-300 rounded-lg">
              <p className="text-sm mb-2">
                Enter sudo password to bring <code className="font-mono">{canInterface}</code> up:
              </p>
              <div className="flex gap-2 items-center">
                <input
                  type="password"
                  className="input input-bordered input-sm flex-1"
                  placeholder="sudo password"
                  value={sudoPassword}
                  onChange={(e) => setSudoPassword(e.target.value)}
                  disabled={ifUpLoading}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && sudoPassword) handleInterfaceUp();
                  }}
                />
                <button
                  className={`btn btn-sm btn-primary gap-1 ${ifUpLoading ? 'loading' : ''}`}
                  onClick={handleInterfaceUp}
                  disabled={!sudoPassword || ifUpLoading}
                >
                  {ifUpLoading ? <FaSpinner className="animate-spin" /> : <FaPlug />}
                  Bring Up
                </button>
              </div>
              {ifUpResult && (
                <p
                  className={`mt-2 text-xs ${ifUpResult.status === 'success' ? 'text-success' : 'text-error'}`}
                >
                  {ifUpResult.status === 'success' ? (
                    <FaCheck className="inline mr-1" />
                  ) : (
                    <FaExclamationTriangle className="inline mr-1" />
                  )}
                  {ifUpResult.message}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* candump */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h2 className="card-title text-lg">candump</h2>
          <p className="text-sm text-base-content/70">
            Capture CAN bus traffic in real-time. Requires <code>can-utils</code> package.
          </p>

          <div className="flex flex-wrap items-end gap-4 mt-2">
            <div className="form-control">
              <label className="label">
                <span className="label-text">Duration (s)</span>
              </label>
              <input
                type="number"
                className="input input-bordered input-sm w-24"
                value={dumpDuration}
                onChange={(e) => setDumpDuration(Math.max(5, Math.min(120, parseInt(e.target.value) || 30)))}
                min={5}
                max={120}
                disabled={dumpRunning}
              />
            </div>

            {!dumpRunning ? (
              <button
                className="btn btn-sm btn-primary gap-1"
                onClick={startDump}
                disabled={!status?.is_up}
              >
                <FaPlay className="w-3 h-3" /> Start Capture
              </button>
            ) : (
              <button className="btn btn-sm btn-error gap-1" onClick={stopDump}>
                <FaStop className="w-3 h-3" /> Stop
              </button>
            )}

            {dumpLines.length > 0 && !dumpRunning && (
              <>
                <button className="btn btn-sm btn-ghost gap-1" onClick={handleCopyDump}>
                  <FaCopy className="w-3 h-3" />
                  {dumpCopied ? 'Copied!' : 'Copy'}
                </button>
                <button
                  className="btn btn-sm btn-ghost gap-1"
                  onClick={() => setDumpLines([])}
                >
                  <FaTrash className="w-3 h-3" /> Clear
                </button>
              </>
            )}
          </div>

          {/* Output window */}
          {(dumpLines.length > 0 || dumpRunning) && (
            <div className="mt-3 bg-base-300 rounded-lg p-3 font-mono text-xs max-h-80 overflow-y-auto">
              {dumpLines.length === 0 && dumpRunning && (
                <div className="text-base-content/50 flex items-center gap-2">
                  <FaSpinner className="animate-spin" /> Waiting for CAN frames...
                </div>
              )}
              {dumpLines.map((line, i) => (
                <div key={i} className="whitespace-pre select-all hover:bg-base-100/30">
                  {line}
                </div>
              ))}
              <div ref={dumpEndRef} />
            </div>
          )}

          {dumpRunning && (
            <div className="text-xs text-base-content/50 mt-1">
              {dumpLines.length} frames captured
            </div>
          )}
        </div>
      </div>

      {/* cansend */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h2 className="card-title text-lg">cansend</h2>
          <p className="text-sm text-base-content/70">
            Send CAN frames. Format: <code>COB-ID#DATA</code> (hex), e.g.{' '}
            <code>701#05</code>
          </p>

          {/* Quick presets */}
          <div className="flex flex-wrap gap-2 mt-2">
            {presets.map((preset) => (
              <button
                key={preset.frame}
                className="btn btn-sm btn-outline gap-1"
                onClick={() => {
                  setSendFrame(preset.frame);
                  setSendResult(null);
                }}
                title={preset.hint}
              >
                {preset.icon} {preset.label}
              </button>
            ))}
          </div>

          {/* Manual frame input */}
          <div className="flex gap-2 items-end mt-3">
            <div className="form-control flex-1">
              <label className="label">
                <span className="label-text">CAN Frame</span>
              </label>
              <input
                type="text"
                className="input input-bordered input-sm font-mono"
                value={sendFrame}
                onChange={(e) => {
                  setSendFrame(e.target.value.toUpperCase());
                  setSendResult(null);
                }}
                placeholder="701#05"
                disabled={sendLoading}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && sendFrame) handleSend();
                }}
              />
            </div>
            <button
              className={`btn btn-sm btn-primary gap-1 ${sendLoading ? 'loading' : ''}`}
              onClick={handleSend}
              disabled={!sendFrame || sendLoading || !status?.is_up}
            >
              {sendLoading ? (
                <FaSpinner className="animate-spin" />
              ) : (
                <FaPaperPlane className="w-3 h-3" />
              )}
              Send
            </button>
          </div>

          {sendResult && (
            <div
              className={`alert text-sm mt-3 ${sendResult.status === 'success' ? 'alert-success' : 'alert-error'}`}
            >
              {sendResult.status === 'success' ? (
                <FaCheck />
              ) : (
                <FaExclamationTriangle />
              )}
              <span>{sendResult.message}</span>
            </div>
          )}

          {/* Help text */}
          <div className="text-xs text-base-content/50 mt-3 space-y-1">
            <p>
              <strong>COB-ID reference:</strong> 0x000=NMT, 0x080+N=SYNC/Emergency,
              0x180+N=TPDO1, 0x200+N=RPDO1, 0x580+N=SDO TX, 0x600+N=SDO RX,
              0x700+N=Heartbeat, 0x7FF=Broadcast
            </p>
            <p>
              <strong>Example heartbeats:</strong> 701#05 (node 1 operational),
              702#00 (node 2 boot-up), 701#7F (node 1 pre-operational)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
