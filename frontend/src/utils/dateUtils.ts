/**
 * Parse a date string from the server, handling missing timezone info.
 *
 * If the date string doesn't have timezone info (Z or ±hh:mm),
 * we assume it's UTC and append 'Z'.
 *
 * @param dateString - ISO8601 date string from server
 * @returns A Date object (always parsed as UTC)
 */
export function parseServerDate(dateString?: string): Date {
  if (!dateString) return new Date(0);

  // Check if string already has timezone info (Z or ±hh:mm)
  const hasTZ = /([zZ]|[+-]\d{2}:\d{2})$/.test(dateString);

  // If no timezone, append Z to treat as UTC
  const normalizedString = hasTZ ? dateString : `${dateString}Z`;

  return new Date(normalizedString);
}

/**
 * Sort messages by created_at (ascending), with id as secondary sort key.
 *
 * This ensures a stable, deterministic order regardless of server response order.
 *
 * @param messages - Array of messages with id and created_at
 * @returns Sorted copy of the array
 */
export function sortMessagesByDate<
  T extends { id?: number | string; created_at?: string },
>(messages: T[]): T[] {
  return [...messages].sort((a, b) => {
    // Primary sort: by created_at timestamp
    const dateA = parseServerDate(a.created_at);
    const dateB = parseServerDate(b.created_at);
    const timeA = dateA.getTime();
    const timeB = dateB.getTime();

    if (timeA !== timeB) {
      return timeA - timeB;
    }

    // Secondary sort: by id (fallback for same timestamp)
    const idA = typeof a.id === "string" ? parseInt(a.id, 10) : (a.id ?? 0);
    const idB = typeof b.id === "string" ? parseInt(b.id, 10) : (b.id ?? 0);
    return (Number.isFinite(idA) ? idA : 0) - (Number.isFinite(idB) ? idB : 0);
  });
}

export function formatRelativeTime(timestamp?: string): string {
  if (!timestamp) return "Date inconnue";

  const date = parseServerDate(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);

  if (diffMins < 1) return "À l'instant";
  if (diffMins < 60) return `Il y a ${diffMins}min`;
  if (diffHours < 24) return `Il y a ${diffHours}h`;
  if (diffDays === 1) return "Hier";
  if (diffDays < 7) return `Il y a ${diffDays}j`;
  if (diffWeeks === 1) return "Il y a 1 semaine";
  if (diffWeeks < 4) return `Il y a ${diffWeeks} semaines`;
  if (diffMonths === 1) return "Il y a 1 mois";
  if (diffMonths < 12) return `Il y a ${diffMonths} mois`;

  // Pour les dates plus anciennes, on affiche la date formatée
  return date.toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "short",
    year: diffMs > 365 * 24 * 60 * 60 * 1000 ? "numeric" : undefined,
  });
}

export function formatFullDateTime(timestamp?: string): string {
  if (!timestamp) return "Date inconnue";

  const date = parseServerDate(timestamp);
  return date.toLocaleDateString("fr-FR", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
