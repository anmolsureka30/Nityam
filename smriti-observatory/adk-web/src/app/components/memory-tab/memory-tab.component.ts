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

import {DatePipe} from '@angular/common';
import {ChangeDetectionStrategy, Component, effect, inject, input, signal} from '@angular/core';
import {MatButtonModule} from '@angular/material/button';
import {MatIconModule} from '@angular/material/icon';
import {MatProgressSpinner} from '@angular/material/progress-spinner';
import {MatTooltipModule} from '@angular/material/tooltip';

import {CoveredConcept, MemorySessionState, OpenDoubt, SelfReflection, Weakness} from '../../core/models/Memory';
import {MEMORY_SERVICE} from '../../core/services/interfaces/memory';
import {TIER_LABEL} from '../../utils/memory-labels.utils';
import {EvidenceChipsComponent} from './evidence-chips.component';

/** The Memory tab: SMRITI's Working/Episodic/Long-Term memory for the
 * session currently open in ADK web, refetched whenever the session or
 * student changes -- own tab in side-panel.component.html, sibling to
 * ADK's generic "State" tab (which shows raw session.state; this shows
 * the tutor app's own memory layer, same data model as the retired
 * standalone SMRITI Observatory). */
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-memory-tab',
  templateUrl: './memory-tab.component.html',
  styleUrl: './memory-tab.component.scss',
  standalone: true,
  imports: [MatProgressSpinner, MatIconModule, MatButtonModule, MatTooltipModule, EvidenceChipsComponent, DatePipe],
})
export class MemoryTabComponent {
  appName = input('');
  sessionId = input('');
  studentId = input('');
  // Memory only changes as a side effect of a tool call or session close --
  // ADK web's own eventData already grows by one on each of those, so
  // reading its size here (side-panel.component.html passes eventData().
  // size) gives the effect below a reactive "something happened" signal
  // without a new poll timer or websocket of our own.
  eventCount = input(0);

  private readonly memoryService = inject(MEMORY_SERVICE);

  readonly TIER_LABEL = TIER_LABEL;

  state = signal<MemorySessionState | null>(null);
  loading = signal(false);
  loadFailed = signal(false);

  constructor() {
    effect(() => {
      const sessionId = this.sessionId();
      const studentId = this.studentId();
      this.eventCount();  // read only to make this effect re-run on new events
      if (!sessionId || !studentId) {
        this.state.set(null);
        this.loadFailed.set(false);
        return;
      }
      this.loading.set(true);
      this.loadFailed.set(false);
      this.memoryService.getState(sessionId, studentId).subscribe({
        next: (state) => {
          this.state.set(state);
          this.loading.set(false);
        },
        error: () => {
          this.state.set(null);
          this.loading.set(false);
          this.loadFailed.set(true);
        },
      });
    });
  }

  refresh(): void {
    const sessionId = this.sessionId();
    const studentId = this.studentId();
    if (!sessionId || !studentId) return;
    this.loading.set(true);
    this.loadFailed.set(false);
    this.memoryService.getState(sessionId, studentId).subscribe({
      next: (state) => {
        this.state.set(state);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.loadFailed.set(true);
      },
    });
  }

  weaknessEntries(): Array<[string, Weakness]> {
    return Object.entries(this.state()?.long_term.dpm_profile?.weaknesses ?? {});
  }

  selfReflections(): SelfReflection[] {
    return this.state()?.long_term.dpm_profile?.self_reflection ?? [];
  }

  coveredEntries(): Array<[string, CoveredConcept]> {
    return Object.entries(this.state()?.long_term.teaching_memory?.covered ?? {});
  }

  openDoubts(): OpenDoubt[] {
    return this.state()?.long_term.teaching_memory?.open_doubts ?? [];
  }

  // Working Memory (live, ephemeral) and Episodic Memory (written once at
  // close) are mutually exclusive in practice -- a live session has an
  // empty session_log, a closed one has an empty turn_buffer -- but both
  // get their own id scheme defensively rather than relying on that.
  workflowTurnDomId(turn: number): string {
    return `wm-turn-${turn}`;
  }

  episodicTurnDomId(turn: number): string {
    return `em-turn-${turn}`;
  }

  jumpToTurn(turn: number): void {
    const el = document.getElementById(this.workflowTurnDomId(turn)) ??
        document.getElementById(this.episodicTurnDomId(turn));
    if (!el) return;
    el.scrollIntoView({behavior: 'smooth', block: 'center'});
    el.classList.add('turn-highlight');
    setTimeout(() => el.classList.remove('turn-highlight'), 1500);
  }

  masteryLabel(m: string): string {
    return m.replace('_', ' ');
  }
}
