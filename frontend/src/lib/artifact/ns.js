/* One shared namespace, standing in for window.Nityam.
 *
 * Same recipe as lib/avatar/: the runtime files are copied from
 * sub_modules_examples/artifact_generator/runtime/ with exactly one edit each —
 * the IIFE receives this object instead of `window.Nityam = window.Nityam || {}`.
 * Nothing else is touched, so re-copying an updated runtime is a mechanical
 * one-line reapply per file and the physics/rendering stay the sub-module's.
 */
export const NS = {};
