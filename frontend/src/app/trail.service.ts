import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, throwError, TimeoutError } from 'rxjs';
import { catchError, timeout } from 'rxjs/operators';
import { Trail } from './models';

/** Client-side request timeout in milliseconds (Req 1.3: 30 seconds). */
export const REQUEST_TIMEOUT_MS = 30_000;

/** Backend endpoint; same-origin so the nginx proxy forwards it to the backend. */
export const TRAIL_ENDPOINT = '/api/trail';

/**
 * Error thrown by {@link TrailService.getTrail} when the request fails or
 * exceeds the client timeout. The topic-entry component (task 9.2) inspects
 * `isTimeout` to show an appropriate message while preserving the entered
 * topic (Req 1.4).
 */
export class TrailServiceError extends Error {
  constructor(
    message: string,
    readonly isTimeout: boolean,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'TrailServiceError';
  }
}

/**
 * Issues the `POST /api/trail` request for a topic and returns the resulting
 * {@link Trail}. Applies a 30-second client timeout (Req 1.3) and normalizes
 * every failure into a {@link TrailServiceError} so the component can show an
 * error message and re-enable submit (Req 1.4).
 */
@Injectable({ providedIn: 'root' })
export class TrailService {
  private readonly http = inject(HttpClient);

  getTrail(topic: string): Observable<Trail> {
    return this.http.post<Trail>(TRAIL_ENDPOINT, { topic }).pipe(
      timeout(REQUEST_TIMEOUT_MS),
      catchError((err: unknown) => throwError(() => this.toTrailError(err))),
    );
  }

  private toTrailError(err: unknown): TrailServiceError {
    if (err instanceof TimeoutError) {
      return new TrailServiceError(
        'The request timed out. The topic could not be processed.',
        true,
      );
    }

    // HttpErrorResponse (and anything else) is surfaced as a non-timeout error.
    const status =
      typeof err === 'object' && err !== null && 'status' in err
        ? (err as { status?: number }).status
        : undefined;
    const detail =
      typeof err === 'object' && err !== null && 'error' in err
        ? (err as { error?: { detail?: string } }).error?.detail
        : undefined;

    return new TrailServiceError(
      detail ?? 'The topic could not be processed. Please try again.',
      false,
      status,
    );
  }
}
