import type { OutputEntity } from '@/types/config';

/**
 * Extended output entity with guaranteed id field.
 */
export type NormalizedOutput = OutputEntity & { id: string };

/**
 * Normalize output entity to ensure it has an ID.
 * Strategy: explicit 'id' > 'boneio_output' > 'name' (slugified)
 */
export function normalizeOutput(output: OutputEntity & { boneio_output?: string }, index: number = 0): NormalizedOutput {
  // If id is already set, use it
  if (output.id) {
    return { ...output, id: output.id };
  }
  
  // Use boneio_output as id if available
  if (output.boneio_output) {
    return { ...output, id: output.boneio_output };
  }
  
  // Slugify name as fallback
  if (output.name) {
    const slugified = output.name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '');
    return { ...output, id: slugified };
  }
  
  // Last resort - index-based ID
  return { ...output, id: `output_${index}` };
}

/**
 * Normalize array of outputs to ensure all have IDs.
 */
export function normalizeOutputs(outputs: Array<OutputEntity & { boneio_output?: string }>): NormalizedOutput[] {
  return outputs
    .filter(output => output && typeof output === 'object')
    .map((output, index) => normalizeOutput(output, index));
}

/**
 * Get effective output ID from an output entity.
 * This is a simpler version that just returns the ID without creating a new object.
 */
export function getOutputId(output: OutputEntity & { boneio_output?: string }): string {
  return output.id || output.boneio_output || output.name?.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || '';
}
