/**
 * Response models for the Study Trail Builder frontend.
 *
 * These TypeScript interfaces mirror the backend REST contract for
 * `POST /api/trail` exactly (see design.md "REST Endpoint Contract" and
 * "Data Models"). The response shape is identical whether the AI path or the
 * heuristic fallback produced the trail.
 */

/** The three fixed difficulty levels, in ascending order (Req 3.5, 5.1, 6.3). */
export type Level = 'Basic' | 'Intermediate' | 'Advanced';

/** A single video in the study trail (Req 6.2). */
export interface Video {
  id: string;
  title: string;
  url: string;
  level: Level;
}

/** A difficulty-level section containing zero or more videos (Req 5.1, 5.5). */
export interface Section {
  level: Level;
  videos: Video[];
}

/**
 * The complete study trail. `sections` is always exactly three entries in
 * Basic -> Intermediate -> Advanced order. `insufficient` is true when fewer
 * than ten videos were available (Req 2.7, 4.6).
 */
export interface Trail {
  topic: string;
  insufficient: boolean;
  sections: Section[];
}

/**
 * The backend error response shape, e.g. `invalid_topic`, `search_failed`,
 * or `no_trail` (see design.md error-responses table).
 */
export interface TrailError {
  error: string;
  detail?: string;
}
