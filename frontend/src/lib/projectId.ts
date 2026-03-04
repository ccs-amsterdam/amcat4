/**
 * Converts a display name to a valid Elasticsearch index / amcat project ID.
 * Valid chars: lowercase letters, digits, hyphens, underscores; no leading hyphen or underscore.
 */
export function idFromName(name: string): string {
  return name
    .replaceAll(" ", "-")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replaceAll(/[^a-z0-9_-]/g, "")
    .replace(/^[_-]+/, "");
}

/**
 * Returns an error message if the given string is not a valid project ID, or null if it is valid.
 */
export function validateProjectId(id: string): string | null {
  if (!id) return "Project ID is required";
  if (/[^a-z0-9_-]/.test(id))
    return "Project ID can only contain lowercase letters, digits, hyphens, and underscores";
  if (/^[_-]/.test(id)) return "Project ID cannot start with a hyphen or underscore";
  if (id.length > 255) return "Project ID must be at most 255 characters";
  return null;
}
