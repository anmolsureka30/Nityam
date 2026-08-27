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

import {MemoryEvent, RecordType, Tier} from '../core/models/Memory';

/** Standard, framework-agnostic memory-systems terminology, not SMRITI's
 * internal tier names. Long-term memory is further split below into its
 * real, distinct kinds rather than shown as one blob. */
export const TIER_LABEL: Record<Tier, string> = {
  workflow: 'Working Memory',
  episodic: 'Episodic Memory',
  long_term: 'Long-Term Memory',
};

export const RECORD_TYPE_LABEL: Record<RecordType, string> = {
  turn_buffer: 'Turn Buffer',
  artifact_event: 'Artifact Event',
  session_log: 'Session Log',
  dpm_profile: 'Learner Profile',
  teaching_memory: 'Teaching State',
  grounding_chunk: 'Knowledge Grounding',
};

const SOURCE_FN_VERB: Record<string, string> = {
  append_turn: 'Turn logged',
  append_artifact_event: 'Artifact event logged',
  get_turn_buffer: 'Turn buffer read',
  clear_session: 'Turn buffer cleared',
  get_session_log: 'Session log read',
  put_session_log: 'Session log written',
  get_dpm: 'Learner profile read',
  put_dpm: 'Learner profile updated',
  get_teaching_memory: 'Teaching state read',
  put_teaching_memory: 'Teaching state updated',
  search_grounding: 'Knowledge grounding searched',
  search_grounding_semantic: 'Knowledge grounding searched (semantic)',
  put_grounding_chunk: 'Knowledge chunk added',
};

function truncate(text: string, max = 72): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** One human-readable sentence describing what this event actually did --
 * the point being a reader never has to parse JSON payloads to know what
 * happened. */
export function describeMemoryEvent(event: MemoryEvent): string {
  const verb = SOURCE_FN_VERB[event.source_fn] ?? event.source_fn;
  const payload = event.payload as Record<string, unknown> | unknown[] | null;

  switch (event.source_fn) {
    case 'append_turn': {
      const p = payload as {turn?: number; role?: string; text?: string} | null;
      if (p?.text) return `Turn ${p.turn} (${p.role}): "${truncate(p.text)}"`;
      return verb;
    }
    case 'get_dpm':
    case 'put_dpm': {
      const p = payload as {weaknesses?: Record<string, unknown>} | null;
      const n = p?.weaknesses ? Object.keys(p.weaknesses).length : 0;
      return `${verb} — ${n} tracked concept${n === 1 ? '' : 's'}`;
    }
    case 'get_teaching_memory':
    case 'put_teaching_memory': {
      const p = payload as {covered?: Record<string, unknown>; open_doubts?: unknown[]} | null;
      const covered = p?.covered ? Object.keys(p.covered).length : 0;
      const doubts = p?.open_doubts?.length ?? 0;
      return `${verb} — ${covered} concept${covered === 1 ? '' : 's'} covered, ${doubts} open doubt${doubts === 1 ? '' : 's'}`;
    }
    case 'search_grounding':
    case 'search_grounding_semantic': {
      const n = Array.isArray(payload) ? payload.length : 0;
      return `${verb} — ${n} chunk${n === 1 ? '' : 's'} found`;
    }
    case 'get_session_log': {
      const p = payload as {turns?: unknown[]} | null;
      if (!p) return 'Session log read — not written yet';
      return `${verb} — ${p.turns?.length ?? 0} turns`;
    }
    case 'put_session_log': {
      const p = payload as {turns?: unknown[]} | null;
      return `${verb} — ${p?.turns?.length ?? 0} turns`;
    }
    default:
      return verb;
  }
}
