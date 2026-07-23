"""
LEXBRIDGE Knowledge Repository — graph.py (Sprint 2.6, Part 7)
-------------------------------------------------------------------------
Builds a reusable relationship graph from every record's relation arrays
(related_ids, related_articles, related_judgments, related_defenses,
related_procedures, related_contracts, related_principles) plus
citations. This does NOT invent new relationships — it only materializes
the ones already present in the data (per KNOWLEDGE_GRAPH_INDEX.json /
KNOWLEDGE_BASE_REPORT.md §10, deeper entity-level linking such as
article<->defense requires a first-class "legal article" entity, which
already exists here as the `laws` collection).

Output is a compact adjacency index (indexes/graph_index.json) that any
tool (CLI, website Knowledge Engine, future tools) can load directly
instead of re-walking 65k records:
    { "<id>": { "type": "...", "folder": "...", "edges": {"<field>": [ids]} } }

Also exposes `related(graph, id, max_depth=1)` for BFS-style traversal,
used by `kb search --related`.
"""
from collections import defaultdict, deque

from .common import load_registry, iter_all_records, write_json, now_iso
from .validate import RELATION_FIELDS


def build_graph(root: str) -> dict:
    registry = load_registry(root)
    nodes = {}
    edge_type_counts = defaultdict(int)

    for folder, _fp, rec in iter_all_records(root, registry):
        rid = rec.get("id")
        if not rid:
            continue
        edges = {}
        for field in RELATION_FIELDS:
            refs = rec.get(field) or []
            if isinstance(refs, list) and refs:
                edges[field] = refs
                edge_type_counts[field] += len(refs)
        nodes[rid] = {
            "type": rec.get("type") or folder,
            "folder": folder,
            "title": rec.get("title"),
            "edges": edges,
            "citation_count": len(rec.get("citations") or []),
        }

    total_edges = sum(edge_type_counts.values())
    graph = {
        "generated_at": now_iso(),
        "node_count": len(nodes),
        "total_edges": total_edges,
        "edge_counts_by_relation": dict(edge_type_counts),
        "nodes": nodes,
    }
    return graph


def save_graph(root: str, graph: dict, path: str) -> None:
    write_json(path, graph)


def related(graph: dict, node_id: str, max_depth: int = 1):
    """BFS over the adjacency graph starting at node_id. Returns a dict
    id -> depth for every reachable node within max_depth hops."""
    nodes = graph["nodes"]
    if node_id not in nodes:
        return {}
    seen = {node_id: 0}
    q = deque([(node_id, 0)])
    while q:
        cur, depth = q.popleft()
        if depth >= max_depth:
            continue
        for refs in nodes.get(cur, {}).get("edges", {}).values():
            for target in refs:
                if target not in seen:
                    seen[target] = depth + 1
                    q.append((target, depth + 1))
    seen.pop(node_id, None)
    return seen
