/**
 * Utility functions for filtering boneIO input pins across
 * binary_sensor and event sections.
 *
 * Pin names in YAML data may use mixed case (binary_sensor: 'in_48',
 * event: 'IN_01'). All comparisons MUST be case-insensitive to prevent
 * cross-section input blocking from silently failing.
 */

interface HasBoneioInput {
  boneio_input?: string;
}

/**
 * Collect used input pins from a list of entities, normalized to uppercase.
 *
 * @param entities - Array of entities (binary_sensor or event)
 * @param editingIndex - Index of the entity currently being edited (excluded from results)
 * @returns Array of uppercase pin names that are in use
 */
export function collectUsedInputs(
  entities: HasBoneioInput[],
  editingIndex: number | null | undefined = null,
): string[] {
  return entities
    .filter((entity, index) => {
      if (editingIndex !== null && editingIndex !== undefined && index === editingIndex) {
        return false;
      }
      return !!entity.boneio_input;
    })
    .map(entity => entity.boneio_input!.toUpperCase());
}

/**
 * Compute the list of available (unused) input pins from all possible pins,
 * given used pins from both binary_sensor and event sections.
 *
 * @param allPins - All possible input pin names (from schema enum, typically uppercase)
 * @param binarySensors - All binary_sensor entities
 * @param events - All event entities
 * @param editingIndex - Index of the entity currently being edited in its own section
 * @param sectionType - Which section is being edited ('binary_sensor' or 'event')
 * @returns Object with usedInputs (uppercase) and availableInputs (original case from schema)
 */
export function getInputAvailability(
  allPins: string[],
  binarySensors: HasBoneioInput[],
  events: HasBoneioInput[],
  editingIndex: number | null | undefined,
  sectionType: 'binary_sensor' | 'event',
): { usedInputs: string[]; availableInputs: string[] } {
  // When editing binary_sensor, exclude editingIndex from binary_sensors
  // When editing event, exclude editingIndex from events
  const usedFromBS = collectUsedInputs(
    binarySensors,
    sectionType === 'binary_sensor' ? editingIndex : null,
  );
  const usedFromEvents = collectUsedInputs(
    events,
    sectionType === 'event' ? editingIndex : null,
  );

  const usedInputs = [...new Set([...usedFromBS, ...usedFromEvents])];
  const availableInputs = allPins.filter(
    (pin) => !usedInputs.includes(pin.toUpperCase()),
  );

  return { usedInputs, availableInputs };
}

/**
 * Build the final list of pin options for a select dropdown.
 * Includes the currently selected pin even if it would normally be filtered out
 * (so the user can see what they currently have selected).
 *
 * @param availableInputs - Pins that are not used by other entities
 * @param currentInput - The currently selected pin for the entity being edited
 * @returns Sorted array of pin names for the dropdown
 */
export function buildInputOptions(
  availableInputs: string[],
  currentInput: string | undefined,
): string[] {
  if (!currentInput) {
    return availableInputs;
  }

  const currentAlreadyAvailable = availableInputs.some(
    (pin) => pin.toUpperCase() === currentInput.toUpperCase(),
  );

  if (currentAlreadyAvailable) {
    return availableInputs;
  }

  // Current pin is used elsewhere — still show it so user can see current selection
  return [...new Set([currentInput, ...availableInputs])].sort();
}
