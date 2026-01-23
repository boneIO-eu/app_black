import { useState, useEffect } from 'react';
import Editor, { BeforeMount, OnMount } from '@monaco-editor/react';
import axios from '@/api/axios';
import { useTheme } from '../hooks/useTheme';
import { FaChevronRight, FaChevronDown, FaRegFolder, FaRegFolderOpen, FaRegFile } from 'react-icons/fa';
import { GoSidebarExpand } from 'react-icons/go';
import ConfigCheckModal from './ConfigCheckModal';
import { configureMonacoYaml, MonacoYaml } from 'monaco-yaml';


interface FileItem {
  name: string;
  type: 'file' | 'directory';
  path: string;
  children?: FileItem[];
  isOpen?: boolean;
}

let monacoYaml: MonacoYaml | undefined;

export default function ConfigEditor() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [isRestarting, setIsRestarting] = useState(false);
  const [restartStatus, setRestartStatus] = useState<'waiting' | 'checking' | 'ready'>('waiting');
  const [showFileTree, setShowFileTree] = useState(true);
  const [showConfigCheck, setShowConfigCheck] = useState(false);
  const theme = useTheme();

  const loadDirectoryTree = async () => {
    try {
      const uri = '/api/files';
      const response = await axios.get(uri);
      setFiles(response.data.items);
    } catch (error) {
      console.error('Error loading directory:', error);
    }
  };

  const loadFile = async (path: string) => {
    try {
      const uri = `/api/files/${encodeURIComponent(path)}`;
      const response = await axios.get(uri);

      setSelectedFile(path);
      setFileContent(response.data.content);
      // Save the last opened file path to localStorage
      localStorage.setItem('lastOpenedFile', path);
    } catch (error) {
      console.error('Error loading file:', error);
      // toast.error('Failed to load file');
    }
  };

  const handleSave = async () => {
    if (!selectedFile) return;
    
    try {
      await axios.put(`/api/files/${encodeURIComponent(selectedFile)}`, {
        content: fileContent
      });
      console.log('File saved successfully');
    } catch (error) {
      console.error('Error saving file:', error);
    }
  };

  const handleBeforeMount: BeforeMount = async (monaco: any) => {
    if (!monacoYaml) {
      // Load all schemas
      const schemaResponse = await axios.get('/schema/config.schema.json');
      const mainSchema = schemaResponse.data;
      
      monacoYaml = await configureMonacoYaml(monaco, {
        enableSchemaRequest: true,
        schemas: [
          // Main schema for config.yaml
          {
            uri: window.location.origin + "/schema/config.schema.json",
            fileMatch: ["config.yaml", "config.yml"],
            schema: mainSchema
          },
          // Section schemas for included files
          ...Object.keys(mainSchema.properties).map(section => ({
            uri: window.location.origin + `/schema/${section}.schema.json`,
            fileMatch: [`${section}.yaml`, `${section}.yml`],
            schema: mainSchema.properties[section]
          }))
        ],
        validate: true,
      });
    }
  };

  const handleEditorMount: OnMount = async (editor: any, monaco: any) => {

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      handleSave();
    });
  };

  const toggleDirectory = (path: string) => {
    setFiles(prevFiles => {
      const updateFiles = (items: FileItem[]): FileItem[] => {
        return items.map(item => {
          if (item.path === path) {
            return { ...item, isOpen: !item.isOpen };
          }
          if (item.children) {
            return { ...item, children: updateFiles(item.children) };
          }
          return item;
        });
      };
      return updateFiles(prevFiles);
    });
  };

  const renderFileTree = (items: FileItem[], level: number = 0) => {
    return items.map((item) => {
      const isOpen = level == 0 || item.isOpen;
      return (
      <div key={item.path}>
        <button
          className={`flex items-center gap-2 w-full px-2 py-1 hover:bg-base-300 ${
            selectedFile === item.path ? 'bg-primary/10' : ''
          }`}
          style={{ paddingLeft: `${level * 16 + 8}px` }}
          onClick={() => item.type === 'file' ? loadFile(item.path) : toggleDirectory(item.path)}
        >
          {item.type === 'directory' && (
            <span className="text-xs">
              {isOpen ? <FaChevronDown /> : <FaChevronRight />}
            </span>
          )}
          <span className="text-base-content/70">
            {item.type === 'directory' 
              ? (isOpen ? <FaRegFolderOpen /> : <FaRegFolder />)
              : <FaRegFile />
            }
          </span>
          <span className="text-sm truncate">{item.name}</span>
        </button>
        {item.type === 'directory' && isOpen && item.children && (
          renderFileTree(item.children, level + 1)
        )}
      </div>
    )});
  };

  const checkServerStatus = async () => {
    try {
      await axios.get('/api/files');
      return true;
    } catch (error) {
      return false;
    }
  };

  const waitForServerRestart = async () => {
    setIsRestarting(true);
    setRestartStatus('waiting');
    
    // Wait for server to go down first
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Then start checking if it's back up
    setRestartStatus('checking');
    while (true) {
      const isUp = await checkServerStatus();
      if (isUp) {
        setRestartStatus('ready');
        await new Promise(resolve => setTimeout(resolve, 1000));
        setIsRestarting(false);
        loadDirectoryTree();
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  };

  const renderRestartOverlay = () => {
    if (!isRestarting) return null;

    return (
      <div className="fixed inset-0 bg-base-300/80 flex items-center justify-center z-50">
        <div className="bg-base-200 p-8 rounded-lg shadow-lg text-center">
          <div className="loading loading-spinner loading-lg mb-4"></div>
          <h2 className="text-xl font-bold mb-4">
            {restartStatus === 'waiting' && 'Restarting Service...'}
            {restartStatus === 'checking' && 'Waiting for Service...'}
            {restartStatus === 'ready' && 'Service Restarted!'}
          </h2>
          <p className="text-base-content/70">
            {restartStatus === 'waiting' && 'Initiating service restart'}
            {restartStatus === 'checking' && 'Checking if service is back online'}
            {restartStatus === 'ready' && 'Redirecting...'}
          </p>
        </div>
      </div>
    );
  };

  useEffect(() => {
    const initializeEditor = async () => {
      await loadDirectoryTree();
      
      // Load last opened file if it exists
      const lastOpenedFile = localStorage.getItem('lastOpenedFile');
      if (lastOpenedFile) {
        loadFile(lastOpenedFile);
      }
    };

    initializeEditor();
  }, []);

  return (
    <div className="flex h-full bg-base-300">
      {renderRestartOverlay()}
      <div className={`${showFileTree ? 'w-64' : 'w-0'} transition-all duration-300 bg-base-200 border-r border-base-content/10 overflow-hidden`}>
        <div className="p-2 text-sm font-semibold text-base-content/70 uppercase">Explorer</div>
        <div className="overflow-y-auto">
          {renderFileTree(files)}
        </div>
      </div>
      <div className="flex-1 overflow-hidden flex flex-col h-full max-h-screen">
        <div className="flex items-center p-2 border-b border-base-content/10">
          <button 
            onClick={() => setShowFileTree(!showFileTree)} 
            className="btn btn-ghost btn-sm p-1"
            title={showFileTree ? "Hide file tree" : "Show file tree"}
          >
            <GoSidebarExpand className={`h-5 w-5 opacity-70 transition-transform duration-200 ${showFileTree ? '' : 'rotate-180'}`} />
          </button>
          {selectedFile && <span className="ml-2 text-sm opacity-70">{selectedFile}</span>}
        </div>
        <div className="flex-1 overflow-hidden">
          <Editor
            height="100%"
            width="100%"
            defaultLanguage="yaml"
            path={selectedFile || "config.yaml"}
            theme={theme === 'light' ? 'vs-light' : 'vs-dark'}
            value={fileContent}
            onChange={(value) => setFileContent(value || '')}
            onMount={handleEditorMount}
            beforeMount={handleBeforeMount}
            options={{
              minimap: { enabled: true },
              scrollBeyondLastLine: false,
              fontSize: 14,
              automaticLayout: true,
              readOnly: false,
              formatOnType: true,
              formatOnPaste: true,
              quickSuggestions: {
                other: true,
                comments: false,
                strings: true,
              },
            }}
          />
        </div>
        <div className="h-12 bg-base-200 border-t border-base-content/10 flex items-center justify-end px-4 gap-4">
          <button 
            onClick={handleSave}
            disabled={!selectedFile}
            className="btn btn-primary btn-sm"
          >
            Save
          </button>
          <button 
            onClick={() => setShowConfigCheck(true)}
            className="btn btn-primary btn-sm"
          >
            Check Config
          </button>
          <button 
            onClick={async () => {
              await handleSave();
              try {
                const response = await axios.post('/api/restart');
                if (response.data.status === 'not available') {
                  const toast = document.getElementById('toast') as HTMLDivElement;
                  if (toast) {
                    toast.classList.remove('hidden');
                    setTimeout(() => {
                      toast.classList.add('hidden');
                    }, 5000);
                  }
                } else {
                  console.log('Service restarted successfully');
                  waitForServerRestart();
                }
              } catch (error) {
                console.error('Error restarting service:', error);
              }
            }}
            disabled={!selectedFile}
            className="btn btn-secondary btn-sm"
          >
            Save and Restart
          </button>
        </div>
      </div>
      <div id="toast" className="toast toast-end hidden">
        <div className="alert alert-warning">
          <span>Restart not possible. Application is not running as systemd service. Restart manually.</span>
        </div>
      </div>
      <ConfigCheckModal 
        isOpen={showConfigCheck}
        onClose={() => setShowConfigCheck(false)}
      />
    </div>
  );
}
