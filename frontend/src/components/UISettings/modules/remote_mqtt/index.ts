/**
 * Public API for the remote_mqtt module.
 *
 * BoneIO files MUST import only from this index — never reach into module internals.
 * Components, hooks, and helpers wire up across Phase 1–6; this file evolves with them.
 */

// Types
export type { PayloadType, ScanResult, ScanRequest, ScanResponse } from './types/scan';
export type {
  MqttEntityKind,
  MqttRemoteInput,
  MqttRemoteOutput,
} from './types/entity';

// Helpers — pure functions
export { jsonPathToJinja, type JsonPathSegment } from './helpers/jsonPathToJinja';
export {
  isValidSubscriptionPattern,
  isValidPublicationTopic,
} from './helpers/topicValidation';

// Hooks (stateful + side-effects; consumable by alternative UI skins)
export { useMqttScan, type UseMqttScanReturn } from './hooks/useMqttScan';
export {
  useJinjaPreview,
  type UseJinjaPreviewReturn,
  type TemplatePreviewResult,
} from './hooks/useJinjaPreview';

// Components (Presentational; safe to swap for alternative skins)
export {
  default as MqttScanDialog,
  type MqttScanDialogProps,
} from './components/MqttScanDialog';
export {
  default as MqttTopicInspector,
  type MqttTopicInspectorProps,
} from './components/MqttTopicInspector';
export {
  default as MqttDeviceEntitiesEditor,
  type MqttDeviceEntitiesEditorProps,
  type MqttDeviceConfig,
  type MqttDeviceInputRow,
  type MqttDeviceOutputRow,
} from './components/MqttDeviceEntitiesEditor';
