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

// (Hooks + components — added in Phase 2, 3, 6)
