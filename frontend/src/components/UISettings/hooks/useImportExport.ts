/**
 * useImportExport - Hook for YAML/JSON import and export functionality.
 */
import { useState, useRef, useCallback } from 'react';
import * as yaml from 'js-yaml';
import { useTranslation } from '@/hooks/useTranslation';

interface UseImportExportProps {
  sectionType: string;
  value: any[];
  onChange: (value: any[]) => void;
}

/**
 * Hook encapsulating import/export state and handlers for array sections.
 */
export function useImportExport({ sectionType, value, onChange }: UseImportExportProps) {
  const { t } = useTranslation();
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importData, setImportData] = useState<any[] | null>(null);
  const [importMode, setImportMode] = useState<'replace' | 'merge'>('merge');
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /** Export current section data as YAML file. */
  const handleExport = useCallback(() => {
    const exportData = {
      section: sectionType,
      version: '1.0',
      exported_at: new Date().toISOString(),
      data: value
    };

    const yamlContent = yaml.dump(exportData, { indent: 2, lineWidth: -1, noRefs: true });
    const blob = new Blob([yamlContent], { type: 'application/x-yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `boneio_${sectionType}_${new Date().toISOString().split('T')[0]}.yaml`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [sectionType, value]);

  /** Handle file selection for import (supports YAML and JSON). */
  const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        let parsed: any;
        try {
          parsed = yaml.load(content);
        } catch {
          parsed = JSON.parse(content);
        }

        if (!parsed.data || !Array.isArray(parsed.data)) {
          setImportError(t('import_export.invalid_format'));
          setImportData(null);
          setImportDialogOpen(true);
          return;
        }

        if (parsed.section && parsed.section !== sectionType) {
          console.warn(`Import section mismatch: expected ${sectionType}, got ${parsed.section}`);
        }

        setImportData(parsed.data);
        setImportError(null);
        setImportDialogOpen(true);
      } catch {
        setImportError(t('import_export.parse_error'));
        setImportData(null);
        setImportDialogOpen(true);
      }
    };
    reader.readAsText(file);

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [sectionType, t]);

  /** Confirm import with selected mode. */
  const confirmImport = useCallback(() => {
    if (!importData) return;

    if (importMode === 'replace') {
      onChange(importData);
    } else {
      const existingIds = new Set(value.map(item => item.id || item.name || item.boneio_output || item.boneio_input));
      const newItems = importData.filter(item => {
        const itemId = item.id || item.name || item.boneio_output || item.boneio_input;
        return !existingIds.has(itemId);
      });
      onChange([...value, ...newItems]);
    }

    setImportDialogOpen(false);
    setImportData(null);
    setImportMode('merge');
  }, [importData, importMode, value, onChange]);

  /** Cancel import. */
  const cancelImport = useCallback(() => {
    setImportDialogOpen(false);
    setImportData(null);
    setImportError(null);
    setImportMode('merge');
  }, []);

  return {
    fileInputRef,
    importDialogOpen,
    importData,
    importMode,
    importError,
    setImportMode,
    handleExport,
    handleFileSelect,
    confirmImport,
    cancelImport,
  };
}
