import React, { useState, useEffect, useContext, useCallback, useRef } from 'react';
import { FaPlay, FaCheck, FaForward, FaTimes, FaSpinner, FaLightbulb, FaToggleOn, FaHandPointer } from 'react-icons/fa';
import { WebSocketContext } from '../../App';
import { OutputEvent, InputEvent } from '../../hooks/useWebSocket';

type TestPhase = 'idle' | 'outputs' | 'inputs' | 'complete';
type TestResult = 'pending' | 'passed' | 'skipped' | 'failed';
type TestMode = 'all' | 'outputs' | 'inputs';

interface TestItem {
  id: string;
  name: string;
  type: 'output' | 'input';
  result: TestResult;
  details?: string;
}

interface SelfTestProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * SelfTest component - Modal for testing outputs and inputs.
 * 
 * Output test: Toggle each output and confirm it works.
 * Input test: Press each input and verify the event is received.
 */
const SelfTest: React.FC<SelfTestProps> = ({ isOpen, onClose }) => {
  const { outputs, inputs } = useContext(WebSocketContext);
  
  const [phase, setPhase] = useState<TestPhase>('idle');
  const [testMode, setTestMode] = useState<TestMode>('all');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [testItems, setTestItems] = useState<TestItem[]>([]);
  const [isToggling, setIsToggling] = useState(false);
  const [waitingForInput, setWaitingForInput] = useState(false);
  
  // Track when we started listening (to ignore old events)
  const listeningStartTimeRef = useRef<number>(0);
  
  // Turn on output
  const turnOnOutput = async (outputId: string) => {
    try {
      await fetch(`/api/outputs/${outputId}/turn_on`, { method: 'POST' });
    } catch (err) {
      console.error('Error turning on output:', err);
    }
  };

  // Turn off output
  const turnOffOutput = async (outputId: string) => {
    try {
      await fetch(`/api/outputs/${outputId}/turn_off`, { method: 'POST' });
    } catch (err) {
      console.error('Error turning off output:', err);
    }
  };

  // Initialize test items from outputs and inputs based on mode
  const initializeTest = useCallback(async (mode: TestMode) => {
    setTestMode(mode);
    
    const outputItems: TestItem[] = (mode === 'all' || mode === 'outputs') 
      ? outputs.map((o: OutputEvent) => ({
          id: o.entity_id,
          name: o.state?.name || o.entity_id,
          type: 'output' as const,
          result: 'pending' as TestResult,
        }))
      : [];
    
    const inputItems: TestItem[] = (mode === 'all' || mode === 'inputs')
      ? inputs.map((i: InputEvent) => ({
          id: i.entity_id,
          name: i.state?.name || i.entity_id,
          type: 'input' as const,
          result: 'pending' as TestResult,
        }))
      : [];
    
    const allItems = [...outputItems, ...inputItems];
    setTestItems(allItems);
    setCurrentIndex(0);
        
    // Set initial phase based on mode
    if (mode === 'inputs') {
      setPhase('inputs');
    } else if (outputItems.length > 0) {
      setPhase('outputs');
      // Auto turn on first output
      await turnOnOutput(outputItems[0].id);
    } else {
      setPhase('inputs');
    }
  }, [outputs, inputs]);

  // Watch for ANY input events during input testing phase (all inputs at once)
  useEffect(() => {
    if (phase !== 'inputs' || !waitingForInput) return;
    
    // Check all pending input items
    const inputItems = testItems.filter(item => item.type === 'input' && item.result === 'pending');
    
    for (const inputItem of inputItems) {
      const matchingInput = inputs.find((i: InputEvent) => i.entity_id === inputItem.id);
      
      if (matchingInput) {
        const clickType = matchingInput.click_type || matchingInput.state?.state;
        if (clickType && clickType !== 'OFF' && clickType !== 'idle') {
          // Check if event timestamp is after we started listening
          const eventTimestampRaw = matchingInput.state?.timestamp || 0;
          const eventTimestamp = eventTimestampRaw * 1000;
          
          if (eventTimestamp > listeningStartTimeRef.current) {
            console.log('Input detected:', inputItem.name, clickType);
            // Mark this input as passed
            setTestItems(prev => prev.map(item => 
              item.id === inputItem.id ? { ...item, result: 'passed', details: clickType } : item
            ));
          }
        }
      }
    }
  }, [inputs, phase, waitingForInput, testItems]);

  // Keyboard handler for SPACE to confirm output
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (phase !== 'outputs' || isToggling) return;
      
      const item = testItems[currentIndex];
      if (e.code === 'Space' && item?.type === 'output') {
        e.preventDefault();
        confirmOutput();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [phase, isToggling, testItems, currentIndex]);

  // Confirm output works - turn off current, mark as passed, move to next with turn on
  const confirmOutput = async () => {
    const currentItem = testItems[currentIndex];
    if (!currentItem || currentItem.type !== 'output') return;
    
    setIsToggling(true);
    
    // Turn off current output
    await turnOffOutput(currentItem.id);
    
    // Mark as passed
    setTestItems(prev => prev.map((item, idx) => 
      idx === currentIndex ? { ...item, result: 'passed' } : item
    ));
    
    // Move to next and turn on if it's an output
    const nextIndex = currentIndex + 1;
    if (nextIndex >= testItems.length) {
      setPhase('complete');
      setIsToggling(false);
      return;
    }
    
    setCurrentIndex(nextIndex);
    const nextItem = testItems[nextIndex];
    
    if (nextItem?.type === 'output') {
      await turnOnOutput(nextItem.id);
    } else if (nextItem?.type === 'input' && testMode !== 'outputs') {
      setPhase('inputs');
    } else {
      // No more items to test
      setPhase('complete');
    }
    
    setIsToggling(false);
  };

  // Skip current test - turn off if output, move to next
  const skipTest = async () => {
    const currentItem = testItems[currentIndex];
    if (!currentItem) return;
    
    setIsToggling(true);
    
    // Turn off if it's an output
    if (currentItem.type === 'output') {
      await turnOffOutput(currentItem.id);
    }
    
    setTestItems(prev => prev.map((item, idx) => 
      idx === currentIndex ? { ...item, result: 'skipped' } : item
    ));
    
    // Move to next
    const nextIndex = currentIndex + 1;
    if (nextIndex >= testItems.length) {
      setPhase('complete');
      setIsToggling(false);
      return;
    }
    
    setCurrentIndex(nextIndex);
    const nextItem = testItems[nextIndex];
    
    if (nextItem?.type === 'output') {
      await turnOnOutput(nextItem.id);
    } else if (nextItem?.type === 'input' && testMode !== 'outputs') {
      setPhase('inputs');
    } else {
      setPhase('complete');
    }
    
    setWaitingForInput(false);
        setIsToggling(false);
  };

  // Fail current test - turn off if output, move to next
  const failTest = async () => {
    const currentItem = testItems[currentIndex];
    if (!currentItem) return;
    
    setIsToggling(true);
    
    // Turn off if it's an output
    if (currentItem.type === 'output') {
      await turnOffOutput(currentItem.id);
    }
    
    setTestItems(prev => prev.map((item, idx) => 
      idx === currentIndex ? { ...item, result: 'failed' } : item
    ));
    
    // Move to next
    const nextIndex = currentIndex + 1;
    if (nextIndex >= testItems.length) {
      setPhase('complete');
      setIsToggling(false);
      return;
    }
    
    setCurrentIndex(nextIndex);
    const nextItem = testItems[nextIndex];
    
    if (nextItem?.type === 'output') {
      await turnOnOutput(nextItem.id);
    } else if (nextItem?.type === 'input' && testMode !== 'outputs') {
      setPhase('inputs');
    } else {
      setPhase('complete');
    }
    
    setWaitingForInput(false);
        setIsToggling(false);
  };

  // Auto-start listening when entering input test phase
  useEffect(() => {
    if (phase !== 'inputs') return;
    
    // Start listening for all inputs at once
    listeningStartTimeRef.current = Date.now();
    setWaitingForInput(true);
  }, [phase]);

  // Get current test item
  const currentItem = testItems[currentIndex];
  
  // Count results
  const passedCount = testItems.filter(i => i.result === 'passed').length;
  const skippedCount = testItems.filter(i => i.result === 'skipped').length;
  const failedCount = testItems.filter(i => i.result === 'failed').length;

  // Reset on close
  const handleClose = () => {
    setPhase('idle');
    setCurrentIndex(0);
    setTestItems([]);
    setWaitingForInput(false);
        onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="modal modal-open">
      <div className="modal-box max-w-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-xl">
            {phase === 'idle' && 'Self Test'}
            {phase === 'outputs' && 'Testing Outputs'}
            {phase === 'inputs' && 'Testing Inputs'}
            {phase === 'complete' && 'Test Complete'}
          </h3>
          <button className="btn btn-ghost btn-sm btn-circle" onClick={handleClose}>
            <FaTimes />
          </button>
        </div>

        {/* Idle - Start screen */}
        {phase === 'idle' && (
          <div className="text-center py-8">
            <FaLightbulb className="text-6xl text-primary mx-auto mb-4" />
            <h4 className="text-lg font-semibold mb-2">Hardware Self Test</h4>
            <p className="text-sm opacity-70 mb-6">
              Choose what you want to test on your device.
            </p>
            <div className="stats stats-vertical lg:stats-horizontal shadow mb-6">
              <div className="stat">
                <div className="stat-title">Outputs</div>
                <div className="stat-value text-primary">{outputs.length}</div>
              </div>
              <div className="stat">
                <div className="stat-title">Inputs</div>
                <div className="stat-value text-secondary">{inputs.length}</div>
              </div>
            </div>
            <div className="flex flex-col gap-3">
              <button 
                className="btn btn-primary btn-lg" 
                onClick={() => initializeTest('all')}
                disabled={outputs.length === 0 && inputs.length === 0}
              >
                <FaPlay /> Test All ({outputs.length + inputs.length})
              </button>
              <div className="flex gap-3 justify-center">
                <button 
                  className="btn btn-outline btn-primary" 
                  onClick={() => initializeTest('outputs')}
                  disabled={outputs.length === 0}
                >
                  <FaToggleOn /> Outputs Only ({outputs.length})
                </button>
                <button 
                  className="btn btn-outline btn-secondary" 
                  onClick={() => initializeTest('inputs')}
                  disabled={inputs.length === 0}
                >
                  <FaHandPointer /> Inputs Only ({inputs.length})
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Output Testing */}
        {phase === 'outputs' && currentItem?.type === 'output' && (
          <div className="py-4">
            {/* Progress */}
            <div className="flex items-center gap-2 mb-4">
              <progress 
                className="progress progress-primary flex-1" 
                value={currentIndex} 
                max={testItems.filter(i => i.type === 'output').length}
              />
              <span className="text-sm opacity-70">
                {currentIndex + 1} / {testItems.filter(i => i.type === 'output').length}
              </span>
            </div>

            {/* Current Output */}
            <div className="card bg-base-200 mb-6">
              <div className="card-body text-center">
                <FaToggleOn className="text-5xl text-primary mx-auto mb-2" />
                <h4 className="text-2xl font-bold">{currentItem.name}</h4>
                <p className="text-sm opacity-70">{currentItem.id}</p>
              </div>
            </div>

            {/* Instructions */}
            <div className="alert alert-success mb-6">
              <FaToggleOn className="text-2xl" />
              <div>
                <p className="font-semibold">Output is ON - check if it's working correctly.</p>
                <p className="text-sm">Press SPACE or click "Confirm" to turn off and go to next.</p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex flex-wrap gap-2 justify-center">
              <button 
                className="btn btn-success btn-lg"
                onClick={confirmOutput}
                disabled={isToggling}
              >
                {isToggling ? <FaSpinner className="animate-spin" /> : <FaCheck />}
                Confirm (Space)
              </button>
              <button className="btn btn-warning" onClick={skipTest} disabled={isToggling}>
                <FaForward /> Skip
              </button>
              <button className="btn btn-error" onClick={failTest} disabled={isToggling}>
                <FaTimes /> Fail
              </button>
            </div>
          </div>
        )}

        {/* Input Testing - Show all inputs as a list */}
        {phase === 'inputs' && (
          <div className="py-4">
            {/* Progress */}
            {(() => {
              const inputItems = testItems.filter(i => i.type === 'input');
              const testedCount = inputItems.filter(i => i.result !== 'pending').length;
              return (
                <div className="flex items-center gap-2 mb-4">
                  <progress 
                    className="progress progress-secondary flex-1" 
                    value={testedCount} 
                    max={inputItems.length}
                  />
                  <span className="text-sm opacity-70">
                    {testedCount} / {inputItems.length}
                  </span>
                </div>
              );
            })()}

            {/* Instructions */}
            <div className="alert alert-info mb-4">
              <FaHandPointer />
              <div>
                <p className="font-semibold">Press each physical button to test it.</p>
                <p className="text-sm">Inputs will turn green when detected. All green = test passed!</p>
              </div>
            </div>

            {/* Input List */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 mb-6 max-h-64 overflow-y-auto">
              {testItems.filter(i => i.type === 'input').map((item) => (
                <div 
                  key={item.id}
                  className={`flex items-center gap-2 p-2 rounded-lg border ${
                    item.result === 'passed' 
                      ? 'bg-success/20 border-success text-success' 
                      : item.result === 'skipped'
                      ? 'bg-warning/20 border-warning text-warning'
                      : item.result === 'failed'
                      ? 'bg-error/20 border-error text-error'
                      : 'bg-base-200 border-base-300'
                  }`}
                >
                  {item.result === 'passed' ? (
                    <FaCheck className="text-success flex-shrink-0" />
                  ) : item.result === 'skipped' ? (
                    <FaForward className="text-warning flex-shrink-0" />
                  ) : item.result === 'failed' ? (
                    <FaTimes className="text-error flex-shrink-0" />
                  ) : (
                    <div className="w-4 h-4 rounded-full border-2 border-base-300 flex-shrink-0" />
                  )}
                  <span className="text-sm truncate">{item.name}</span>
                </div>
              ))}
            </div>

            {/* Actions */}
            <div className="flex flex-wrap gap-2 justify-center">
              {(() => {
                const inputItems = testItems.filter(i => i.type === 'input');
                const allTested = inputItems.every(i => i.result !== 'pending');
                const allPassed = inputItems.every(i => i.result === 'passed');
                
                if (allTested) {
                  return (
                    <button 
                      className={`btn btn-lg ${allPassed ? 'btn-success' : 'btn-primary'}`}
                      onClick={() => setPhase('complete')}
                    >
                      <FaCheck /> {allPassed ? 'All Passed!' : 'Finish Test'}
                    </button>
                  );
                }
                return (
                  <>
                    <button 
                      className="btn btn-success"
                      onClick={() => setPhase('complete')}
                    >
                      <FaCheck /> Finish
                    </button>
                    <button 
                      className="btn btn-warning"
                      onClick={() => {
                        // Mark all pending as skipped
                        setTestItems(prev => prev.map(item => 
                          item.type === 'input' && item.result === 'pending' 
                            ? { ...item, result: 'skipped' } 
                            : item
                        ));
                      }}
                    >
                      <FaForward /> Skip All
                    </button>
                  </>
                );
              })()}
            </div>
          </div>
        )}

        {/* Complete */}
        {phase === 'complete' && (
          <div className="py-4">
            <div className="text-center mb-6">
              <FaCheck className="text-6xl text-success mx-auto mb-4" />
              <h4 className="text-xl font-semibold">Test Complete!</h4>
            </div>

            {/* Summary */}
            <div className="stats stats-vertical lg:stats-horizontal shadow w-full mb-6">
              <div className="stat">
                <div className="stat-title">Passed</div>
                <div className="stat-value text-success">{passedCount}</div>
              </div>
              <div className="stat">
                <div className="stat-title">Skipped</div>
                <div className="stat-value text-warning">{skippedCount}</div>
              </div>
              <div className="stat">
                <div className="stat-title">Failed</div>
                <div className="stat-value text-error">{failedCount}</div>
              </div>
            </div>

            {/* Results table */}
            <div className="overflow-x-auto max-h-64">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {testItems.map((item) => (
                    <tr key={item.id}>
                      <td>{item.name}</td>
                      <td>
                        <span className={`badge badge-sm ${item.type === 'output' ? 'badge-primary' : 'badge-secondary'}`}>
                          {item.type}
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-sm ${
                          item.result === 'passed' ? 'badge-success' :
                          item.result === 'skipped' ? 'badge-warning' :
                          item.result === 'failed' ? 'badge-error' :
                          'badge-ghost'
                        }`}>
                          {item.result}
                          {item.details && ` (${item.details})`}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="modal-action">
              <button className="btn btn-primary" onClick={handleClose}>
                Close
              </button>
            </div>
          </div>
        )}
      </div>
      <div className="modal-backdrop bg-black/50" onClick={handleClose}></div>
    </div>
  );
};

export default SelfTest;
