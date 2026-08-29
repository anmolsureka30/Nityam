/* Curriculum metadata: what a concept id is actually called.
 *
 * The memory store (backend/app/memory/schemas.py) keys everything by
 * concept_id — "PHY-11-K2" — and never carries a human-readable name,
 * because naming a concept is a curriculum-authoring concern, not a memory
 * one. This is that mapping: static content (what the syllabus calls
 * something), not student data — the student's actual mastery, interests,
 * and doubts always come from the real memory endpoint (lib/memory.ts),
 * never from here. A concept id with no entry falls back to itself, so a
 * new concept the catalogue hasn't caught up with still renders something
 * legible instead of disappearing.
 */
export const CONCEPT_NAMES: Record<string, string> = {
  "PHY-11-K2": "Maximum range",
  "PHY-11-K5": "Independence of axes",
  "PHY-11-K3": "Time of flight",
  "PHY-11-K7": "Symmetry of complementary angles",
};

export function conceptName(conceptId: string): string {
  return CONCEPT_NAMES[conceptId] ?? conceptId;
}
