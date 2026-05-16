/** MQTT scan-and-discover types — shared between scanner UI and backend response. */

export type PayloadType = 'json' | 'string' | 'numeric' | 'binary' | 'empty';

export interface ScanResult {
  topic: string;
  last_payload: string;
  payload_type: PayloadType;
  update_count: number;
  parsed_json: unknown;
}

export interface ScanRequest {
  pattern: string;
  duration_s: number;
}

export interface ScanResponse {
  topics: ScanResult[];
  pattern: string;
  duration_s: number;
}
