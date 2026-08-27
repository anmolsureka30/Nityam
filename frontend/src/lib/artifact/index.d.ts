/** Types for the ported artifact runtime. The runtime is plain JS, copied from
 *  the sub-module; this only describes what mountArtifact returns and takes. */

export interface EvidenceEvent {
  event: string;
  concept_ids?: string[];
  detail?: string;
  [key: string]: unknown;
}

export interface ArtifactHandle {
  destroy(): void;
  state?(): Record<string, number>;
  evidence?(): EvidenceEvent[];
}

export interface MountOptions {
  themes?: Record<string, Record<string, unknown>>;
  theme?: string;
  onEvidence?: (event: EvidenceEvent) => void;
}

export interface ArtifactNamespace {
  mountArtifact(
    ir: unknown,
    container: HTMLElement,
    opts?: MountOptions,
  ): ArtifactHandle;
  KERNELS: Record<string, unknown>;
}

declare const NS: ArtifactNamespace;
export default NS;
