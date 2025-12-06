/**
 * ID validation and sanitization utilities.
 * 
 * IDs must be lowercase, no spaces, no special characters, no Polish characters.
 * Only alphanumeric characters and underscores are allowed.
 */

/**
 * Regex pattern for valid ID characters.
 * Only lowercase letters (a-z), numbers (0-9), and underscores (_) are allowed.
 */
export const ID_PATTERN = /^[a-z0-9_]*$/;

/**
 * Check if an ID is valid.
 * 
 * @param id - The ID to validate
 * @returns true if valid, false otherwise
 */
export function isValidId(id: string): boolean {
  if (!id) return true; // Empty is allowed (optional field)
  return ID_PATTERN.test(id);
}

/**
 * Get validation error message for invalid ID.
 * 
 * @param id - The ID to check
 * @returns Error message or null if valid
 */
export function getIdValidationError(id: string): string | null {
  if (!id) return null;
  
  if (/\s/.test(id)) {
    return 'ID cannot contain spaces';
  }
  if (/[A-Z]/.test(id)) {
    return 'ID must be lowercase';
  }
  if (/[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]/.test(id)) {
    return 'ID cannot contain Polish characters';
  }
  if (!ID_PATTERN.test(id)) {
    return 'ID can only contain lowercase letters, numbers, and underscores';
  }
  return null;
}

/**
 * Sanitize an ID by converting to lowercase and replacing invalid characters.
 * 
 * @param id - The ID to sanitize
 * @returns Sanitized ID
 */
export function sanitizeId(id: string): string {
  if (!id) return '';
  
  return id
    .toLowerCase()
    // Replace Polish characters
    .replace(/ą/g, 'a')
    .replace(/ć/g, 'c')
    .replace(/ę/g, 'e')
    .replace(/ł/g, 'l')
    .replace(/ń/g, 'n')
    .replace(/ó/g, 'o')
    .replace(/ś/g, 's')
    .replace(/ź/g, 'z')
    .replace(/ż/g, 'z')
    // Replace spaces with underscores
    .replace(/\s+/g, '_')
    // Remove any remaining invalid characters
    .replace(/[^a-z0-9_]/g, '');
}

/**
 * Handle ID input change with auto-sanitization.
 * 
 * @param value - The input value
 * @param onChange - Callback to update the value
 * @param autoSanitize - If true, automatically sanitize the input
 */
export function handleIdChange(
  value: string,
  onChange: (sanitized: string) => void,
  autoSanitize: boolean = true
): void {
  if (autoSanitize) {
    onChange(sanitizeId(value));
  } else {
    onChange(value);
  }
}
