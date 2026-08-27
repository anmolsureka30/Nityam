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

import {ChangeDetectionStrategy, Component, input} from '@angular/core';

import {EnrichedMemoryEvent} from '../../core/models/Memory';
import {describeMemoryEvent, RECORD_TYPE_LABEL, TIER_LABEL} from '../../utils/memory-labels.utils';

/** One memory operation, rendered the same way regardless of where it's
 * shown -- a trace span's "what did this do to memory" section, or the
 * Memory tab's own event list. */
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-memory-operation-row',
  standalone: true,
  template: `
    <div class="row" [class]="'tier-' + enriched().event.tier">
      <span class="dot"></span>
      <span class="tier-label">{{ tierLabel() }}</span>
      <span class="op-badge" [class.write]="enriched().event.operation === 'write'">{{ enriched().event.operation }}</span>
      <span class="record-type">{{ recordTypeLabel() }}</span>
      <span class="summary">{{ summary() }}</span>
    </div>
    @if (enriched().diff.length > 0) {
      <ul class="diff-list">
        @for (change of enriched().diff; track change.path) {
          <li class="diff-row">
            <span class="diff-path">{{ change.path }}</span>
            @if (change.kind === 'changed') {
              <span class="diff-transition">{{ change.old }} → {{ change.new }}</span>
            } @else {
              <span class="diff-label">{{ change.label }}</span>
            }
          </li>
        }
      </ul>
    }
  `,
  styles: [`
    .row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 5px 8px;
      font-size: 0.78rem;
      border-radius: 4px;
    }
    .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .tier-workflow .dot { background: #7cc4ff; }
    .tier-episodic .dot { background: #e8a33d; }
    .tier-long_term .dot { background: #6bcf8a; }
    .tier-label {
      color: var(--mdc-theme-text-secondary-on-background, #9aa0a6);
      min-width: 96px;
      flex-shrink: 0;
    }
    .op-badge {
      font-family: monospace;
      font-size: 0.68rem;
      padding: 1px 6px;
      border-radius: 3px;
      background: rgba(255,255,255,0.08);
      flex-shrink: 0;
    }
    .op-badge.write {
      background: rgba(124,196,255,0.18);
      color: #7cc4ff;
    }
    .record-type {
      flex-shrink: 0;
      opacity: 0.8;
      min-width: 110px;
    }
    .summary {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
    }
    .diff-list {
      list-style: none;
      margin: 0 0 4px 30px;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .diff-row {
      display: flex;
      gap: 8px;
      font-size: 0.72rem;
      opacity: 0.85;
    }
    .diff-path {
      font-family: monospace;
      color: #9aa0a6;
    }
    .diff-transition {
      color: #6bcf8a;
    }
  `],
})
export class MemoryOperationRowComponent {
  enriched = input.required<EnrichedMemoryEvent>();

  tierLabel(): string {
    return TIER_LABEL[this.enriched().event.tier];
  }

  recordTypeLabel(): string {
    return RECORD_TYPE_LABEL[this.enriched().event.record_type];
  }

  summary(): string {
    return describeMemoryEvent(this.enriched().event);
  }
}
