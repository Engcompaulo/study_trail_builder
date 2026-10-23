import { Component, inject, signal, viewChild, ElementRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TrailService, TrailServiceError } from './trail.service';
import { Trail } from './models';
import { TrailView } from './trail-view.component';

/** Maximum topic length in characters (Req 1.1, 1.6). */
export const MAX_TOPIC_LENGTH = 200;

/**
 * Topic-entry root component (Req 1.1-1.7).
 *
 * Presents a single text input (1..200 chars) plus a submit control. On
 * submit it validates the topic client-side (rejecting empty/whitespace-only
 * and over-length topics while preserving the entered text), calls
 * {@link TrailService.getTrail}, shows a loading indicator and disables submit
 * while awaiting the response, and on timeout/error restores the form and
 * surfaces an error message. The resulting trail (or error message) is passed
 * down to the {@link TrailView} component for rendering (task 9.3).
 */
@Component({
  selector: 'app-root',
  imports: [FormsModule, TrailView],
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {
  private readonly trailService = inject(TrailService);

  /** The topic text bound to the input (Req 1.1). */
  protected readonly topic = signal('');

  /** True while awaiting the backend response (Req 1.2, 1.3). */
  protected readonly loading = signal(false);

  /** Client-side validation message shown under the input (Req 1.5, 1.6). */
  protected readonly validationMessage = signal<string | null>(null);

  /** Error message surfaced after a failed/timed-out request (Req 1.4, 5.6). */
  protected readonly errorMessage = signal<string | null>(null);

  /** The last successfully built trail, passed to the trail-view (Req 5.1). */
  protected readonly trail = signal<Trail | null>(null);

  /** The topic input element, used to keep/restore focus (Req 1.5). */
  private readonly topicInput = viewChild<ElementRef<HTMLInputElement>>('topicInput');

  protected readonly maxTopicLength = MAX_TOPIC_LENGTH;

  /**
   * Validates and submits the current topic. Returns early without a request
   * when the topic is empty/whitespace-only or exceeds the max length,
   * preserving the entered text in both cases (Req 1.5, 1.6).
   */
  protected submit(): void {
    if (this.loading()) {
      return;
    }

    const raw = this.topic();
    const trimmed = raw.trim();

    // Reject empty / whitespace-only; keep focus on the input (Req 1.5).
    if (trimmed.length === 0) {
      this.validationMessage.set('Please enter a topic.');
      this.errorMessage.set(null);
      this.topicInput()?.nativeElement.focus();
      return;
    }

    // Reject over-length; preserve the entered text (Req 1.6).
    if (raw.length > MAX_TOPIC_LENGTH) {
      this.validationMessage.set(
        `The maximum topic length is ${MAX_TOPIC_LENGTH} characters.`,
      );
      return;
    }

    // Valid submission. Clear messages and show the loader synchronously so it
    // is visible well within 500 ms of submission (Req 1.2, 1.3).
    this.validationMessage.set(null);
    this.errorMessage.set(null);
    this.loading.set(true);

    this.trailService.getTrail(trimmed).subscribe({
      next: (trail) => {
        this.trail.set(trail);
        this.loading.set(false);
      },
      error: (err: unknown) => {
        // On timeout/error: hide the loader, re-enable submit, preserve the
        // entered topic, and surface an error message (Req 1.4, 5.6).
        this.loading.set(false);
        this.errorMessage.set(this.messageFor(err));
      },
    });
  }

  private messageFor(err: unknown): string {
    if (err instanceof TrailServiceError && err.message) {
      return err.message;
    }
    return 'The topic could not be processed. Please try again.';
  }
}
