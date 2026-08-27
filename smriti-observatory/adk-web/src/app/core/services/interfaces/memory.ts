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

import {InjectionToken} from '@angular/core';
import {Observable} from 'rxjs';

import {EnrichedMemoryEvent, MemorySessionState} from '../../models/Memory';

export const MEMORY_SERVICE = new InjectionToken<MemoryService>('MemoryService');

/**
 * Reads the tutor app's SMRITI memory-layer endpoints
 * (app/app_utils/memory_routes.py) — same origin, same FastAPI process as
 * every other ADK web request, no separate backend.
 */
export declare abstract class MemoryService {
  abstract getState(sessionId: string, studentId: string): Observable<MemorySessionState>;
  abstract getEvents(
      sessionId: string, studentId: string,
      traceId?: string): Observable<EnrichedMemoryEvent[]>;
}
