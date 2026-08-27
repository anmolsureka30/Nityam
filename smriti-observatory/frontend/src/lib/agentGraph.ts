import type { Tier } from "./types";

export type GraphNodeKind = "agent" | "tool";

export interface GraphNode {
  id: string;
  label: string;
  kind: GraphNodeKind;
}

export interface GraphEdge {
  from: string;
  to: string;
}

export interface ParsedGraph {
  nodes: Map<string, GraphNode>;
  edges: GraphEdge[];
}

const NODE_LINE = /^\s*(\w+)\s+\[label="([^"]*)"/;
const EDGE_LINE = /^\s*(\w+)\s*->\s*(\w+)\s*\[/;

/** ADK's dev-ui graph endpoint returns Graphviz DOT source describing the
 * real agent/tool topology (see google/adk/cli/agent_graph.py — 🤖 for
 * agents, 🔧 for tools, ellipse vs box shape). Parsed by line rather than
 * with a full DOT grammar since the server always emits one declaration
 * per line in this exact shape. `strict digraph` means a node declared
 * twice (e.g. a sub-agent that's also exposed as an AgentTool) just
 * repeats its id with the same label emoji, so de-duping by id is safe --
 * the caption never disagrees with itself about agent-vs-tool. */
export function parseDotGraph(dotSrc: string): ParsedGraph {
  const nodes = new Map<string, GraphNode>();
  const edgeKeys = new Set<string>();
  const edges: GraphEdge[] = [];

  for (const line of dotSrc.split("\n")) {
    const edgeMatch = line.match(EDGE_LINE);
    if (edgeMatch) {
      const [, from, to] = edgeMatch;
      const key = `${from}->${to}`;
      if (!edgeKeys.has(key)) {
        edgeKeys.add(key);
        edges.push({ from, to });
      }
      continue;
    }
    const nodeMatch = line.match(NODE_LINE);
    if (nodeMatch) {
      const [, id, label] = nodeMatch;
      nodes.set(id, { id, label, kind: label.startsWith("🤖") ? "agent" : "tool" });
    }
  }
  return { nodes, edges };
}

export interface AgentTree {
  node: GraphNode;
  tools: GraphNode[];
  children: AgentTree[];
}

/** Builds a rooted tree for rendering: the root agent (no incoming
 * agent->agent edge), each agent's owned tools (tool nodes it has a direct
 * edge to), and its child agents (recursively). A tool shared by more than
 * one agent (get_dpm is both TutorAgent's and ArtifactAgent's) legitimately
 * appears under each owner -- that's the real topology, not a bug. */
export function buildAgentTree(graph: ParsedGraph): AgentTree | null {
  const { nodes, edges } = graph;
  const agentIds = [...nodes.values()].filter((n) => n.kind === "agent").map((n) => n.id);
  if (agentIds.length === 0) return null;

  const incomingAgentEdge = new Set(
    edges.filter((e) => nodes.get(e.to)?.kind === "agent").map((e) => e.to)
  );
  const rootId = agentIds.find((id) => !incomingAgentEdge.has(id)) ?? agentIds[0];

  function build(agentId: string, visited: Set<string>): AgentTree {
    const node = nodes.get(agentId)!;
    const outgoing = edges.filter((e) => e.from === agentId);
    const tools = outgoing
      .map((e) => nodes.get(e.to))
      .filter((n): n is GraphNode => !!n && n.kind === "tool");
    const children = outgoing
      .map((e) => nodes.get(e.to))
      .filter((n): n is GraphNode => !!n && n.kind === "agent" && !visited.has(n.id))
      .map((n) => build(n.id, new Set([...visited, n.id])));
    return { node, tools, children };
  }

  return build(rootId, new Set([rootId]));
}

/** Maps our own instrumentation's `source_fn` (the storage-layer function
 * name) onto the ADK tool node id it corresponds to -- these differ for
 * tools whose ADK-facing name doesn't match the store/short_term function
 * they delegate to (log_turn calls short_term.append_turn, for instance).
 * A `null` mapping means the source_fn is a session-close-time operation
 * with no single calling agent (put_dpm, put_teaching_memory, ...) --
 * rendered separately, not highlighted on the agent graph. */
export const SOURCE_FN_TO_TOOL_ID: Record<string, string | null> = {
  append_turn: "log_turn",
  append_artifact_event: "log_artifact_evidence",
  get_dpm: "get_dpm",
  get_teaching_memory: "get_teaching_memory",
  search_grounding: "search_grounding",
  search_grounding_semantic: "search_grounding",
  get_turn_buffer: null,
  clear_session: null,
  get_session_log: null,
  put_session_log: null,
  put_dpm: null,
  put_teaching_memory: null,
  put_grounding_chunk: null,
};

export type ActiveTools = Map<string, Set<Tier>>;
