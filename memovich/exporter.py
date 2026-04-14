"""
exporter.py — Export the memory store as a browsable folder of markdown files.

Produces:
  output_dir/
    index.md              — table of contents
    namespace_name/
      segment_name.md     — one file per segment, chunks as sections

Streams chunks in paginated batches so memory usage stays bounded
regardless of store size.
"""

import os
import re
from collections import defaultdict
from datetime import datetime

from .metadata_keys import NAMESPACE, SEGMENT
from .palace import get_collection


def _safe_path_component(name: str) -> str:
    """Sanitize a string for use as a directory/file name component."""
    name = re.sub(r'[/\\:*?"<>|]', "_", name)
    name = name.strip(". ")
    return name or "unknown"


def export_palace(palace_path: str, output_dir: str, format: str = "markdown") -> dict:
    """Export all chunks as markdown files organized by namespace/segment.

    Streams chunks in batches of 1000 and writes each segment file
    incrementally, keeping memory usage proportional to batch size rather
    than total store size.

    Args:
        palace_path: Path to the vector store root.
        output_dir: Where to write the exported markdown tree.
        format: Output format (currently only "markdown").

    Returns:
        Stats dict: {"namespaces": N, "segments": N, "chunks": N}
    """
    col = get_collection(palace_path)
    total = col.count()

    if total == 0:
        print("  Store is empty — nothing to export.")
        return {"namespaces": 0, "segments": 0, "chunks": 0}

    os.makedirs(output_dir, exist_ok=True)

    opened_segments: set[tuple[str, str]] = set()
    ns_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_chunks = 0

    print(f"  Streaming {total} chunks...")
    offset = 0
    while offset < total:
        batch = col.get(limit=1000, offset=offset, include=["documents", "metadatas"])
        if not batch["ids"]:
            break

        batch_grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for doc_id, doc, meta in zip(batch["ids"], batch["documents"], batch["metadatas"]):
            ns = meta.get(NAMESPACE, "unknown")
            seg = meta.get(SEGMENT, "general")
            batch_grouped[ns][seg].append(
                {
                    "id": doc_id,
                    "content": doc,
                    "source": meta.get("source_file", ""),
                    "filed_at": meta.get("filed_at", ""),
                    "added_by": meta.get("added_by", ""),
                }
            )

        for ns, segs in batch_grouped.items():
            safe_ns = _safe_path_component(ns)
            ns_dir = os.path.join(output_dir, safe_ns)
            os.makedirs(ns_dir, exist_ok=True)

            for seg, chunks in segs.items():
                safe_seg = _safe_path_component(seg)
                seg_path = os.path.join(ns_dir, f"{safe_seg}.md")
                key = (ns, seg)
                is_new = key not in opened_segments

                with open(seg_path, "a" if not is_new else "w", encoding="utf-8") as f:
                    if is_new:
                        f.write(f"# {ns} / {seg}\n\n")
                        opened_segments.add(key)

                    for chunk in chunks:
                        source = chunk["source"] or "unknown"
                        filed = chunk["filed_at"] or "unknown"
                        added_by = chunk["added_by"] or "unknown"

                        f.write(
                            f"## {chunk['id']}\n"
                            f"\n"
                            f"> {_quote_content(chunk['content'])}\n"
                            f"\n"
                            f"| Field | Value |\n"
                            f"|-------|-------|\n"
                            f"| Source | {source} |\n"
                            f"| Filed | {filed} |\n"
                            f"| Added by | {added_by} |\n"
                            f"\n"
                            f"---\n\n"
                        )

                ns_stats[ns][seg] += len(chunks)
                total_chunks += len(chunks)

        offset += len(batch["ids"])

    index_rows = []
    for ns in sorted(ns_stats):
        segs = ns_stats[ns]
        ns_chunk_count = sum(segs.values())
        index_rows.append((ns, len(segs), ns_chunk_count))
        print(f"  {ns}: {len(segs)} segments, {ns_chunk_count} chunks")

    today = datetime.now().strftime("%Y-%m-%d")
    index_lines = [
        f"# Memory export — {today}\n",
        "",
        "| Namespace | Segments | Chunks |",
        "|-----------|----------|--------|",
    ]
    for ns, seg_count, chunk_count in index_rows:
        index_lines.append(f"| [{ns}]({ns}/) | {seg_count} | {chunk_count} |")
    index_lines.append("")

    index_path = os.path.join(output_dir, "index.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines))

    stats = {
        "namespaces": len(ns_stats),
        "segments": sum(s for _, s, _ in index_rows),
        "chunks": total_chunks,
    }
    print(
        f"\n  Exported {stats['chunks']} chunks across {stats['namespaces']} namespaces, "
        f"{stats['segments']} segment files"
    )
    print(f"  Output: {output_dir}")
    return stats


def _quote_content(text: str) -> str:
    """Format content for a markdown blockquote, handling multiline."""
    lines = text.rstrip("\n").split("\n")
    return "\n> ".join(lines)
