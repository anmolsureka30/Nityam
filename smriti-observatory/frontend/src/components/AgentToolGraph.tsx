import { useEffect, useState } from "react";
import { buildAgentTree, parseDotGraph, SOURCE_FN_TO_TOOL_ID, type AgentTree, type GraphNode } from "../lib/agentGraph";
import type { Tier } from "../lib/types";
import styles from "./AgentToolGraph.module.css";

const TIER_ORDER: Tier[] = ["workflow", "episodic", "long_term"];
const TIER_CLASS: Record<Tier, string> = { workflow: styles.tierWorkflow, episodic: styles.tierEpisodic, long_term: styles.tierLongTerm };

interface AgentToolGraphProps {
  backendUrl: string;
  /** source_fn -> tiers it touched, from whichever trace is currently
   * selected in the timeline. Empty when nothing is selected -- the graph
   * then renders in its neutral, unhighlighted state (same as ADK web's
   * own default). */
  activeSourceFns: Map<string, Set<Tier>>;
}

function TierDots({ tiers }: { tiers: Set<Tier> }) {
  if (tiers.size === 0) return null;
  return (
    <span className={styles.tierDots}>
      {TIER_ORDER.filter((t) => tiers.has(t)).map((t) => (
        <span key={t} className={`${styles.tierDot} ${TIER_CLASS[t]}`} title={t} />
      ))}
    </span>
  );
}

function ToolChip({ node, tiers }: { node: GraphNode; tiers: Set<Tier> | undefined }) {
  const active = !!tiers && tiers.size > 0;
  return (
    <div className={active ? styles.toolChipActive : styles.toolChip}>
      <span className={styles.toolIcon}>🔧</span>
      <span className={styles.toolLabel}>{node.id}</span>
      {tiers && <TierDots tiers={tiers} />}
    </div>
  );
}

function AgentCard({ tree, toolTiers, depth }: { tree: AgentTree; toolTiers: Map<string, Set<Tier>>; depth: number }) {
  const anyToolActive = tree.tools.some((t) => (toolTiers.get(t.id)?.size ?? 0) > 0);
  const anyChildActive = tree.children.some((c) => childHasActivity(c, toolTiers));
  const active = anyToolActive || anyChildActive;
  return (
    <div className={active ? styles.agentCardActive : styles.agentCard} style={{ marginLeft: depth > 0 ? 20 : 0 }}>
      <div className={styles.agentHeader}>
        <span className={styles.agentIcon}>🤖</span>
        <span className={styles.agentLabel}>{tree.node.id}</span>
      </div>
      {tree.tools.length > 0 && (
        <div className={styles.toolRow}>
          {tree.tools.map((t) => (
            <ToolChip key={t.id} node={t} tiers={toolTiers.get(t.id)} />
          ))}
        </div>
      )}
      {tree.children.map((child) => (
        <AgentCard key={child.node.id} tree={child} toolTiers={toolTiers} depth={depth + 1} />
      ))}
    </div>
  );
}

function childHasActivity(tree: AgentTree, toolTiers: Map<string, Set<Tier>>): boolean {
  if (tree.tools.some((t) => (toolTiers.get(t.id)?.size ?? 0) > 0)) return true;
  return tree.children.some((c) => childHasActivity(c, toolTiers));
}

export function AgentToolGraph({ backendUrl, activeSourceFns }: AgentToolGraphProps) {
  const [tree, setTree] = useState<AgentTree | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    fetch(`${backendUrl}/api/agent-graph`)
      .then((r) => r.json())
      .then((body) => {
        const dotSrc = body.dot_src as string;
        if (!dotSrc) {
          setLoadError(true);
          return;
        }
        setTree(buildAgentTree(parseDotGraph(dotSrc)));
      })
      .catch(() => setLoadError(true));
  }, [backendUrl]);

  // Fold source_fn -> tool node id, merging tier sets for tools that more
  // than one source_fn maps to (search_grounding_semantic also lands on
  // the search_grounding node).
  const toolTiers = new Map<string, Set<Tier>>();
  const systemTiers = new Set<Tier>();
  for (const [sourceFn, tiers] of activeSourceFns) {
    const toolId = SOURCE_FN_TO_TOOL_ID[sourceFn];
    if (toolId === null || toolId === undefined) {
      for (const t of tiers) systemTiers.add(t);
      continue;
    }
    const existing = toolTiers.get(toolId) ?? new Set<Tier>();
    for (const t of tiers) existing.add(t);
    toolTiers.set(toolId, existing);
  }

  if (loadError) return null;

  return (
    <div className={styles.panel}>
      <button className={styles.toggle} onClick={() => setCollapsed((c) => !c)}>
        <span>{collapsed ? "▸" : "▾"}</span> Agent & tool graph
        <span className={styles.hint}>from the tutor app's own ADK topology</span>
      </button>
      {!collapsed && (
        <div className={styles.body}>
          {tree ? <AgentCard tree={tree} toolTiers={toolTiers} depth={0} /> : <p className={styles.loading}>Loading graph…</p>}
          {systemTiers.size > 0 && (
            <div className={styles.systemCardActive}>
              <div className={styles.agentHeader}>
                <span className={styles.agentIcon}>🧠</span>
                <span className={styles.agentLabel}>Session close (reflect)</span>
                <TierDots tiers={systemTiers} />
              </div>
              <p className={styles.systemNote}>
                Runs once, at session end — outside any single agent turn, so it isn't part of the ADK
                agent/tool graph above.
              </p>
            </div>
          )}
          {toolTiers.size === 0 && systemTiers.size === 0 && (
            <p className={styles.hintBody}>Select an event in the timeline to see which agent and tool produced it.</p>
          )}
        </div>
      )}
    </div>
  );
}
