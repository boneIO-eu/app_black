import { useState, useCallback, useEffect } from 'react';
import { FaServer, FaPlus, FaSave, FaEdit, FaCheck, FaExclamationTriangle } from 'react-icons/fa';
import axios from '@/api/axios';
import { NumericInput } from '@/components/ui/NumericInput';

interface CANNode {
  node_id: number;
  is_online: boolean;
  nmt_state: string;
  last_heartbeat: number | null;
}

export default function CANNetwork() {
  const [nodes, setNodes] = useState<CANNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [assigningId, setAssigningId] = useState<number | null>(null);
  const [newNodeId, setNewNodeId] = useState<number>(2);

  const [editingNode, setEditingNode] = useState<number | null>(null);
  const [configYaml, setConfigYaml] = useState<string>('');
  const [savingConfig, setSavingConfig] = useState(false);
  const [saveResult, setSaveResult] = useState<{ status: string; message: string } | null>(null);

  const fetchNodes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await axios.get('/api/can/nodes');
      setNodes(data.nodes || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch CAN nodes');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNodes();
    const interval = setInterval(fetchNodes, 5000);
    return () => clearInterval(interval);
  }, [fetchNodes]);

  const handleAssignId = async (targetNodeId: number) => {
    setAssigningId(targetNodeId);
    try {
      await axios.post('/api/can/nodes/assign', {
        target_node_id: targetNodeId,
        new_node_id: newNodeId,
      });
      setNewNodeId((prev) => prev + 1);
      fetchNodes();
    } catch (err: any) {
      alert('Failed to assign ID: ' + (err.response?.data?.detail || err.message));
    } finally {
      setAssigningId(null);
    }
  };

  const handleSaveConfig = async () => {
    if (editingNode === null) return;
    setSavingConfig(true);
    setSaveResult(null);
    try {
      const { data } = await axios.post(`/api/can/nodes/${editingNode}/config`, {
        config_yaml: configYaml,
      });
      setSaveResult({ status: 'success', message: data.message });
      setTimeout(() => setSaveResult(null), 3000);
    } catch (err: any) {
      setSaveResult({ status: 'error', message: err.response?.data?.detail || err.message });
    } finally {
      setSavingConfig(false);
    }
  };

  const unconfiguredNodes = nodes.filter((n) => n.node_id === 127);
  const activeNodes = nodes.filter((n) => n.node_id !== 127 && n.node_id !== 1); // Exclude master (1) and unconfigured (127)

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold">CAN Network Management</h2>
        <button
          className={`btn btn-sm btn-ghost gap-2 ${loading ? 'loading' : ''}`}
          onClick={fetchNodes}
          disabled={loading}
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="alert alert-error">
          <FaExclamationTriangle />
          <span>{error}</span>
        </div>
      )}

      {/* Unconfigured Nodes */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h2 className="card-title text-lg text-warning">
            <FaPlus /> Pending Devices (Unconfigured)
          </h2>
          <p className="text-sm text-base-content/70">
            Devices with Node ID 127 waiting to be assigned a permanent ID.
          </p>

          {unconfiguredNodes.length === 0 ? (
            <p className="text-sm italic opacity-50">No pending devices found.</p>
          ) : (
            <div className="overflow-x-auto mt-4">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>Current ID</th>
                    <th>State</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {unconfiguredNodes.map((node) => (
                    <tr key={node.node_id}>
                      <td>{node.node_id}</td>
                      <td>
                        <div className={`badge ${node.is_online ? 'badge-success' : 'badge-error'}`}>
                          {node.nmt_state}
                        </div>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <NumericInput
                            className="input-sm w-20"
                            value={newNodeId}
                            onChange={(v) => setNewNodeId(v === '' ? 2 : v)}
                            min={2}
                            max={126}
                          />
                          <button
                            className={`btn btn-sm btn-primary ${assigningId === node.node_id ? 'loading' : ''}`}
                            onClick={() => handleAssignId(node.node_id)}
                            disabled={assigningId !== null}
                          >
                            Assign ID
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Active Slaves */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h2 className="card-title text-lg text-success">
            <FaServer /> Active Slaves
          </h2>

          {activeNodes.length === 0 ? (
            <p className="text-sm italic opacity-50">No active slaves found on the bus.</p>
          ) : (
            <div className="overflow-x-auto mt-4">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>Node ID</th>
                    <th>State</th>
                    <th>Config</th>
                  </tr>
                </thead>
                <tbody>
                  {activeNodes.map((node) => (
                    <tr key={node.node_id}>
                      <td className="font-bold">{node.node_id}</td>
                      <td>
                        <div className={`badge ${node.is_online ? 'badge-success' : 'badge-error'}`}>
                          {node.nmt_state}
                        </div>
                      </td>
                      <td>
                        <button
                          className="btn btn-sm btn-outline gap-2"
                          onClick={() => {
                            setEditingNode(node.node_id);
                            setConfigYaml('# Write YAML configuration here for Node ' + node.node_id + '\n');
                          }}
                        >
                          <FaEdit /> Edit Config
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* YAML Editor Modal */}
      {editingNode !== null && (
        <div className="modal modal-open">
          <div className="modal-box w-11/12 max-w-5xl">
            <h3 className="font-bold text-lg mb-4">Edit Configuration for Node {editingNode}</h3>
            
            <div className="form-control mb-4">
              <textarea
                className="textarea textarea-bordered font-mono h-64"
                value={configYaml}
                onChange={(e) => setConfigYaml(e.target.value)}
                placeholder="event:\n  - id: IN_01\n..."
              />
            </div>

            {saveResult && (
              <div className={`alert ${saveResult.status === 'success' ? 'alert-success' : 'alert-error'} mb-4`}>
                {saveResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
                <span>{saveResult.message}</span>
              </div>
            )}

            <div className="modal-action">
              <button
                className={`btn btn-primary gap-2 ${savingConfig ? 'loading' : ''}`}
                onClick={handleSaveConfig}
                disabled={savingConfig}
              >
                {!savingConfig && <FaSave />} Save & Push to Slave
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setEditingNode(null);
                  setSaveResult(null);
                }}
                disabled={savingConfig}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
