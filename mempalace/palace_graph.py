"""
palace_graph.py — Graph traversal layer for MemPalace
======================================================

Builds a navigable graph from chunk metadata:
  - Nodes = segments (named ideas / slugs)
  - Edges = segments that appear under multiple namespaces (tunnels)
  - Edge types = halls (optional corridor tags on metadata)

No external graph DB needed — built from vector store metadata.
"""

from collections import Counter, defaultdict

from .config import MempalaceConfig
from .metadata_keys import NAMESPACE, SEGMENT
from .palace import get_collection as _get_palace_collection


def _get_collection(config=None):
    config = config or MempalaceConfig()
    try:
        return _get_palace_collection(
            config.palace_path,
            collection_name=config.collection_name,
            create=False,
        )
    except Exception:
        return None


def build_graph(col=None, config=None):
    """
    Build the memory graph from collection metadata.

    Returns:
        nodes: dict of {segment: {namespaces, halls, count, dates}}
        edges: list of tunnel crossings with namespace_a / namespace_b
    """
    if col is None:
        col = _get_collection(config)
    if not col:
        return {}, []

    total = col.count()
    seg_data = defaultdict(
        lambda: {"namespaces": set(), "halls": set(), "count": 0, "dates": set()}
    )

    offset = 0
    while offset < total:
        batch = col.get(limit=1000, offset=offset, include=["metadatas"])
        for meta in batch["metadatas"]:
            segment = meta.get(SEGMENT, "")
            namespace = meta.get(NAMESPACE, "")
            hall = meta.get("hall", "")
            date = meta.get("date", "")
            if segment and segment != "general" and namespace:
                seg_data[segment]["namespaces"].add(namespace)
                if hall:
                    seg_data[segment]["halls"].add(hall)
                if date:
                    seg_data[segment]["dates"].add(date)
                seg_data[segment]["count"] += 1
        if not batch["ids"]:
            break
        offset += len(batch["ids"])

    edges = []
    for segment, data in seg_data.items():
        namespaces = sorted(data["namespaces"])
        if len(namespaces) >= 2:
            for i, na in enumerate(namespaces):
                for nb in namespaces[i + 1 :]:
                    for hall in data["halls"] or {""}:
                        edges.append(
                            {
                                "segment": segment,
                                "namespace_a": na,
                                "namespace_b": nb,
                                "hall": hall,
                                "count": data["count"],
                            }
                        )

    nodes = {}
    for segment, data in seg_data.items():
        nodes[segment] = {
            "namespaces": sorted(data["namespaces"]),
            "halls": sorted(data["halls"]),
            "count": data["count"],
            "dates": sorted(data["dates"])[-5:] if data["dates"] else [],
        }

    return nodes, edges


def traverse(start_room: str, col=None, config=None, max_hops: int = 2):
    """
    Walk the graph from a starting segment. Finds other segments linked by
    shared namespaces (same segment name filed under overlapping domains).

    MCP parameter remains ``start_room`` for tool-schema stability; value is
    a segment slug.

    Returns list of dicts with segment, namespaces, halls, hop, etc.
    """
    nodes, _edges = build_graph(col, config)

    if start_room not in nodes:
        return {
            "error": f"Segment '{start_room}' not found",
            "suggestions": _fuzzy_match(start_room, nodes),
        }

    start = nodes[start_room]
    visited = {start_room}
    results = [
        {
            "segment": start_room,
            "namespaces": start["namespaces"],
            "halls": start["halls"],
            "count": start["count"],
            "hop": 0,
        }
    ]

    frontier = [(start_room, 0)]
    while frontier:
        current_segment, depth = frontier.pop(0)
        if depth >= max_hops:
            continue

        current = nodes.get(current_segment, {})
        current_ns = set(current.get("namespaces", []))

        for segment, data in nodes.items():
            if segment in visited:
                continue
            shared_ns = current_ns & set(data["namespaces"])
            if shared_ns:
                visited.add(segment)
                results.append(
                    {
                        "segment": segment,
                        "namespaces": data["namespaces"],
                        "halls": data["halls"],
                        "count": data["count"],
                        "hop": depth + 1,
                        "connected_via": sorted(shared_ns),
                    }
                )
                if depth + 1 < max_hops:
                    frontier.append((segment, depth + 1))

    results.sort(key=lambda x: (x["hop"], -x["count"]))
    return results[:50]


def find_tunnels(namespace_a: str = None, namespace_b: str = None, col=None, config=None):
    """Segments that bridge two namespaces (or all tunnels if filters omitted)."""
    nodes, _edges = build_graph(col, config)

    tunnels = []
    for segment, data in nodes.items():
        namespaces = data["namespaces"]
        if len(namespaces) < 2:
            continue

        if namespace_a and namespace_a not in namespaces:
            continue
        if namespace_b and namespace_b not in namespaces:
            continue

        tunnels.append(
            {
                "segment": segment,
                "namespaces": namespaces,
                "halls": data["halls"],
                "count": data["count"],
                "recent": data["dates"][-1] if data["dates"] else "",
            }
        )

    tunnels.sort(key=lambda x: -x["count"])
    return tunnels[:50]


def graph_stats(col=None, config=None):
    """Summary statistics about the memory graph."""
    nodes, edges = build_graph(col, config)

    tunnel_segments = sum(1 for n in nodes.values() if len(n["namespaces"]) >= 2)
    namespace_counts = Counter()
    for data in nodes.values():
        for ns in data["namespaces"]:
            namespace_counts[ns] += 1

    return {
        "total_segments": len(nodes),
        "tunnel_segments": tunnel_segments,
        "total_edges": len(edges),
        "segments_per_namespace": dict(namespace_counts.most_common()),
        "top_tunnels": [
            {"segment": s, "namespaces": d["namespaces"], "count": d["count"]}
            for s, d in sorted(nodes.items(), key=lambda x: -len(x[1]["namespaces"]))[:10]
            if len(d["namespaces"]) >= 2
        ],
    }


def _fuzzy_match(query: str, nodes: dict, n: int = 5):
    """Find segments that approximately match a query string."""
    query_lower = query.lower()
    scored = []
    for segment in nodes:
        if query_lower in segment:
            scored.append((segment, 1.0))
        elif any(word in segment for word in query_lower.split("-")):
            scored.append((segment, 0.5))
    scored.sort(key=lambda x: -x[1])
    return [s for s, _ in scored[:n]]
