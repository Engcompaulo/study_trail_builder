import { Component, Input } from '@angular/core';
import { Level, Section, Trail, Video } from './models';

/**
 * The three fixed difficulty levels, top-to-bottom in ascending order
 * (Req 5.1). Used to guarantee all three section labels always render, even if
 * the backend response is incomplete.
 */
const LEVEL_ORDER: Level[] = ['Basic', 'Intermediate', 'Advanced'];

/**
 * Renders a {@link Trail} as three labeled sections (Basic, Intermediate,
 * Advanced) from top to bottom (Req 5.1). Within each section every video
 * shows its title and link on the same horizontal row, opening the YouTube URL
 * in a new tab (Req 5.2, 5.3). Malformed videos render a non-activatable
 * "Video unavailable" placeholder (Req 5.4); empty sections show a message
 * under their label (Req 5.5); on error, a null trail, or an insufficient
 * response a visible status message is shown (Req 5.6).
 *
 * Shared contract with the topic-entry component (task 9.2): selector
 * `app-trail-view`, class `TrailView`, inputs `trail` and `errorMessage`.
 */
@Component({
  selector: 'app-trail-view',
  standalone: true,
  imports: [],
  template: `
    <section class="trail-view" aria-live="polite">
      @if (showNoTrailMessage()) {
        <p class="trail-error" role="alert">
          {{ errorMessage || 'No trail could be built for this topic.' }}
        </p>
      } @else {
        @if (trail?.insufficient) {
          <p class="trail-note" role="status">
            Fewer than ten videos were available for this topic, so the trail is
            shorter than usual.
          </p>
        }

        @for (level of levelOrder; track level) {
          <div class="trail-section">
            <h2 class="trail-section__label">{{ level }}</h2>

            @let videos = videosFor(level);
            @if (videos.length === 0) {
              <p class="trail-section__empty">
                No videos in this section.
              </p>
            } @else {
              <ul class="trail-section__list">
                @for (video of videos; track $index) {
                  <li class="trail-row">
                    @if (isPlayable(video)) {
                      <span class="trail-row__title">{{ video.title }}</span>
                      <a
                        class="trail-row__link"
                        [href]="video.url"
                        target="_blank"
                        rel="noopener"
                      >Watch</a>
                    } @else {
                      <span class="trail-row__title trail-row__title--unavailable">
                        Video unavailable
                      </span>
                      <span
                        class="trail-row__link trail-row__link--disabled"
                        aria-disabled="true"
                      >Unavailable</span>
                    }
                  </li>
                }
              </ul>
            }
          </div>
        }
      }
    </section>
  `,
  styles: [
    `
      .trail-view {
        display: flex;
        flex-direction: column;
        gap: 1.5rem;
      }

      .trail-error {
        padding: 0.75rem 1rem;
        border: 1px solid #c0392b;
        border-radius: 6px;
        color: #c0392b;
        background: #fdecea;
        font-weight: 600;
      }

      .trail-note {
        padding: 0.5rem 0.75rem;
        border-radius: 6px;
        color: #8a6d3b;
        background: #fcf8e3;
      }

      .trail-section__label {
        margin: 0 0 0.5rem;
        font-size: 1.25rem;
      }

      .trail-section__empty {
        margin: 0;
        color: #777;
        font-style: italic;
      }

      .trail-section__list {
        list-style: none;
        margin: 0;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
      }

      .trail-row {
        display: flex;
        flex-direction: row;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.4rem 0.5rem;
        border-radius: 4px;
        background: #f6f6f6;
      }

      .trail-row__title {
        flex: 1 1 auto;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .trail-row__title--unavailable {
        color: #999;
        font-style: italic;
      }

      .trail-row__link {
        flex: 0 0 auto;
      }

      .trail-row__link--disabled {
        color: #aaa;
        cursor: not-allowed;
        text-decoration: none;
      }
    `,
  ],
})
export class TrailView {
  /** The trail to render, or null when no trail could be built (Req 5.6). */
  @Input() trail: Trail | null = null;

  /** An error message to surface instead of a trail (Req 5.6). */
  @Input() errorMessage: string | null = null;

  /** Fixed top-to-bottom section order (Req 5.1). */
  protected readonly levelOrder = LEVEL_ORDER;

  /**
   * Show the "no trail" message when an error is set or no trail is present
   * (Req 5.6). The `insufficient` flag is handled separately as an
   * informational note (Req 4.6) and still renders the sections.
   */
  protected showNoTrailMessage(): boolean {
    return this.errorMessage != null || this.trail == null;
  }

  /**
   * Returns the videos for a given level, guarding against a missing or
   * malformed `sections` array so labels always render (Req 5.1, 5.5).
   */
  protected videosFor(level: Level): Video[] {
    const section: Section | undefined = this.trail?.sections?.find(
      (s) => s?.level === level,
    );
    return section?.videos ?? [];
  }

  /**
   * A video is playable when it has a non-empty title and a well-formed URL
   * (http:// or https://). Otherwise it renders as a "Video unavailable"
   * placeholder with a non-activatable link (Req 5.4).
   */
  protected isPlayable(video: Video): boolean {
    return this.hasTitle(video) && this.isValidUrl(video.url);
  }

  private hasTitle(video: Video): boolean {
    return typeof video?.title === 'string' && video.title.trim().length > 0;
  }

  /** A URL is valid only when it starts with http:// or https:// (Req 5.4). */
  private isValidUrl(url: unknown): boolean {
    return typeof url === 'string' && /^https?:\/\//i.test(url.trim());
  }
}
