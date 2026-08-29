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
  // The syllabus codes the planner uses.
  "PHY-11-K2": "Maximum range",
  "PHY-11-K5": "Independence of axes",
  "PHY-11-K3": "Time of flight",
  "PHY-11-K7": "Symmetry of complementary angles",

  // The grounding corpus's own ids. These come from Shruti's ingestion of the
  // real lectures, so they are the ids the MEMORY LAYER actually stores —
  // which means they are what the profile and the session recaps render. They
  // were missing here, so every one of them fell through to the raw id and
  // "projectile.vector_resolution" appeared on screen as though it were a
  // name. Naming them is most of what makes those screens readable.
  "projectile.vector_resolution": "Resolving a vector into components",
  "projectile.projectile_motion": "Projectile motion",
  "projectile.time_of_flight": "Time of flight",
  "projectile.maximum_height": "Maximum height",
  "projectile.trajectory_equation_in_two-dimensional_motion": "The trajectory equation",
  "projectile.trajectory_equation_comparison_method": "Comparing trajectory equations",
  "projectile.trajectory_equation_parameter_extraction": "Reading values off a trajectory",
  "projectile.impact_angle_condition_in_2d_motion": "Angle of impact",
  "projectile.perpendicular_condition_for_projectile_velocity_vectors": "When velocities are perpendicular",
  "projectile.perpendicular_velocity_condition_in_projectile_motion": "Perpendicular velocity condition",
  "projectile.perpendicularity_condition_for_velocity_vectors": "Perpendicular velocity vectors",
  "projectile.projectile_launched_perpendicular_to_an_inclined_plane": "Launching onto an incline",
  "projectile.staircase_projectile_problem": "The staircase problem",
  "projectile.staircase_projectile_analysis": "Analysing the staircase problem",
  "projectile.staircase_projectile_collision_method": "Staircase problem by collisions",
  "projectile.rolling_body_topmost_point_velocity_rule": "Top of a rolling body",
  "projectile.rolling_motion_velocity_of_topmost_point": "Velocity at the top of a roll",
  "projectile.topmost_point_velocity_of_a_rolling_body": "Speed at the topmost point",
};

/** A readable name for a concept id, with a fallback that is still readable.
 *
 *  The table above cannot be complete and never will be: the end-of-session
 *  reflection MINTS NEW CONCEPT IDS when it sees something the corpus has no
 *  id for — a real session produced `projectile_maximum_range` this way. A
 *  bare `?? conceptId` therefore guarantees raw snake_case leaks onto the
 *  profile eventually, so the fallback tidies rather than surrenders:
 *  namespace off, underscores to spaces, first letter up. Not as good as a
 *  real name, but never embarrassing. */
export function conceptName(conceptId: string): string {
  const known = CONCEPT_NAMES[conceptId];
  if (known) return known;
  if (!conceptId) return "";
  const tail = conceptId.includes(".") ? conceptId.slice(conceptId.indexOf(".") + 1) : conceptId;
  const words = tail.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : conceptId;
}
