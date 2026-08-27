/**
 * @license
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import {ChangeDetectionStrategy, Component, input, output} from '@angular/core';

/** Renders "{session_id}#{turn}" evidence citations as chips. When a
 * citation's session_id matches the session currently open in the Memory
 * tab, it's clickable -- jumpToTurn (memory-tab.component.ts) scrolls the
 * Working Memory turn list to it. A citation from a different (older,
 * possibly no-longer-buffered) session renders as plain text -- there's
 * nothing to scroll to. */
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-evidence-chips',
  standalone: true,
  template: `
    @if (evidence().length > 0) {
      <div class="chips">
        @for (ref of evidence(); track ref) {
          @if (isJumpable(ref)) {
            <button class="chip chip-link" (click)="jumpToTurn.emit(turnOf(ref))" [title]="'Jump to turn ' + turnOf(ref)">{{ shortLabel(ref) }}</button>
          } @else {
            <span class="chip">{{ ref }}</span>
          }
        }
      </div>
    }
  `,
  styles: [`
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 2px;
    }
    .chip {
      font-family: monospace;
      font-size: 0.68rem;
      padding: 1px 7px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.14);
      color: var(--mat-sys-on-surface-variant);
      background: transparent;
    }
    .chip-link {
      cursor: pointer;
      color: var(--mat-sys-primary);
      border-color: var(--mat-sys-primary);
    }
    .chip-link:hover {
      background: rgba(255,255,255,0.06);
    }
  `],
})
export class EvidenceChipsComponent {
  evidence = input<string[]>([]);
  currentSessionId = input('');
  jumpToTurn = output<number>();

  private sessionOf(ref: string): string {
    return ref.split('#')[0];
  }

  private turnPart(ref: string): number {
    return Number(ref.split('#')[1]);
  }

  isJumpable(ref: string): boolean {
    return this.sessionOf(ref) === this.currentSessionId() && !Number.isNaN(this.turnPart(ref));
  }

  turnOf(ref: string): number {
    return this.turnPart(ref);
  }

  shortLabel(ref: string): string {
    const [sessionId, turn] = ref.split('#');
    const short = sessionId.length > 14 ? `${sessionId.slice(0, 14)}…` : sessionId;
    return `${short}#${turn}`;
  }
}
