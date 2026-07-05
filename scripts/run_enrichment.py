#!/usr/bin/env python3
"""
Batch re-enrichment script — classify existing Qdrant chunks with LLM.

Runs on the HOST (not inside Docker). Calls Ollama and Qdrant directly
via HTTP. No backend app imports needed.

Usage:
    .venv/bin/python scripts/run_enrichment.py
    .venv/bin/python scripts/run_enrichment.py --collection kb_gotomarket_75b3223b

Requirements:
    pip install requests qdrant-client
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from functools import partial

# Force unbuffered output so progress is visible in background runs
print = partial(print, flush=True)

try:
    import requests
    from qdrant_client import QdrantClient
except ImportError:
    sys.exit("ERROR: pip install requests qdrant-client")


# ---------------------------------------------------------------------------
# Configuration — auto-loads from .env
# ---------------------------------------------------------------------------

def _load_env() -> dict:
    env_path = Path(__file__).parent.parent / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

_ENV = _load_env()

QDRANT_URL     = os.environ.get("QDRANT_URL") or _ENV.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or _ENV.get("QDRANT_API_KEY", "")
OLLAMA_URL     = os.environ.get("OLLAMA_URL") or _ENV.get("OLLAMA_URL", "http://localhost:11434")
AGENTBASE_URL  = os.environ.get("AGENTBASE_URL") or _ENV.get("AGENTBASE_URL", "http://localhost:8002")

TAXONOMY_ID = "21d774c8-1c7a-4cee-92bc-b07576a19021"
MODEL = "gemma4:31b-cloud"
SCROLL_BATCH = 20
MAX_CHARS = 3000


# ---------------------------------------------------------------------------
# Taxonomy loader (via Agentbase API)
# ---------------------------------------------------------------------------

def load_taxonomy() -> dict[str, list[str]]:
    """Load taxonomy terms grouped by facet."""
    r = requests.get(f"{AGENTBASE_URL}/api/taxonomies/{TAXONOMY_ID}/terms/", timeout=10)
    r.raise_for_status()
    facets: dict[str, list[str]] = {}
    for term in r.json():
        facet = term["facet"]
        facets.setdefault(facet, [])
        if term["value"] not in facets[facet]:
            facets[facet].append(term["value"])
    return facets


# ---------------------------------------------------------------------------
# LLM classification
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a document classifier. Classify this document using ONLY the provided taxonomy values.

DOCUMENT (first {max_chars} chars):
{text_excerpt}

FILENAME: {filename}

TAXONOMY:
{taxonomy_block}

Return ONLY valid JSON with no explanation:
{json_template}"""


def classify_with_llm(text: str, filename: str, facets: dict[str, list[str]]) -> dict | None:
    """Call Ollama to classify a chunk. Returns dict or None on failure."""
    text_excerpt = text[:MAX_CHARS]

    taxonomy_lines = []
    json_keys = {}
    for facet, values in sorted(facets.items()):
        taxonomy_lines.append(f"- {facet}: {', '.join(values)}")
        json_key = "doc_category" if facet == "doc_categories" else f"{facet}s"
        json_keys[json_key] = [] if facet != "doc_categories" else ""

    prompt = _PROMPT_TEMPLATE.format(
        max_chars=MAX_CHARS,
        text_excerpt=text_excerpt,
        filename=filename,
        taxonomy_block="\n".join(taxonomy_lines) or "(no terms)",
        json_template=json.dumps(json_keys),
    )

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "think": False,  # Disable qwen3 thinking mode for clean JSON output
                "options": {"temperature": 0.1, "num_predict": 500},
            },
            timeout=120,
        )
        r.raise_for_status()
        content = r.json().get("response", "")
    except Exception as e:
        return None

    # Parse JSON from response
    cleaned = re.sub(r"```(?:json)?", "", content).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        raw = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    # Validate against taxonomy
    validated = {}
    for key, value in raw.items():
        if key == "doc_category":
            facet = "doc_categories"
        elif key.endswith("s"):
            facet = key[:-1]
        else:
            facet = key
        known = facets.get(facet, [])
        if isinstance(value, list):
            validated[key] = [v for v in value if v in known]
        elif isinstance(value, str):
            validated[key] = value if value in known else ""
        else:
            validated[key] = value
    return validated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CHECKPOINT_FILE = Path(__file__).parent.parent / "data" / "enrichment_checkpoint.json"


def _load_checkpoint() -> dict:
    """Load checkpoint with completed collections and resume state."""
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"completed_collections": [], "total_classified": 0, "total_failed": 0}


def _save_checkpoint(state: dict) -> None:
    """Save checkpoint so enrichment can resume after interruption."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(json.dumps(state, indent=2))


def _check_ollama() -> bool:
    """Verify Ollama is reachable and the model is available."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        base = MODEL.split(":")[0]
        if not any(base in m for m in models):
            print(f"  WARNING: Model '{MODEL}' not found in Ollama. Available: {models[:5]}")
            return False
        return True
    except Exception as e:
        print(f"  ERROR: Ollama not reachable at {OLLAMA_URL}: {e}")
        return False


def _wait_for_ollama(max_retries: int = 60, interval: int = 30) -> bool:
    """Wait for Ollama to come back online (e.g., after restart/update)."""
    print(f"\n  Ollama unavailable. Waiting up to {max_retries * interval // 60} min for it to return...")
    for attempt in range(max_retries):
        time.sleep(interval)
        if _check_ollama():
            print(f"  Ollama is back! Resuming enrichment.")
            return True
        print(f"  Still waiting... ({attempt + 1}/{max_retries})", end="\r")
    print(f"\n  Ollama did not return after {max_retries * interval // 60} min. Saving checkpoint and exiting.")
    return False


def main():
    parser = argparse.ArgumentParser(description="Batch LLM re-enrichment for kb_* collections")
    parser.add_argument("--collection", help="Process a single collection (default: all kb_*)")
    parser.add_argument("--dry-run", action="store_true", help="Classify but don't update Qdrant")
    parser.add_argument("--reset", action="store_true", help="Clear checkpoint and start fresh")
    args = parser.parse_args()

    print(f"Enrichment Script (host-native)")
    print(f"  Ollama:  {OLLAMA_URL} / {MODEL}")
    print(f"  Qdrant:  {QDRANT_URL}")
    print(f"  API:     {AGENTBASE_URL}")

    # Check Ollama before starting
    print("\nChecking Ollama...")
    if not _check_ollama():
        if not _wait_for_ollama():
            sys.exit(1)

    # Load/reset checkpoint
    if args.reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("  Checkpoint cleared.")
    checkpoint = _load_checkpoint()
    completed = set(checkpoint.get("completed_collections", []))
    if completed:
        print(f"\n  Resuming: {len(completed)} collection(s) already done (use --reset to start fresh)")

    # Load taxonomy
    print("\nLoading taxonomy...")
    facets = load_taxonomy()
    print(f"  {sum(len(v) for v in facets.values())} terms across {len(facets)} facets")

    # Connect to Qdrant
    kw = {"api_key": QDRANT_API_KEY} if QDRANT_API_KEY else {}
    client = QdrantClient(url=QDRANT_URL, timeout=60, **kw)

    # Get collections
    if args.collection:
        collections = [args.collection]
    else:
        collections = sorted([
            c.name for c in client.get_collections().collections
            if c.name.startswith("kb_")
        ])
    print(f"  {len(collections)} collection(s) total, {len(collections) - len(completed)} remaining\n")

    total_classified = checkpoint.get("total_classified", 0)
    total_skipped = 0
    total_failed = checkpoint.get("total_failed", 0)
    consecutive_failures = 0
    start_time = time.time()

    for coll_name in collections:
        # Skip completed collections (resume support)
        if coll_name in completed:
            continue

        info = client.get_collection(coll_name)
        point_count = info.points_count
        if point_count == 0:
            completed.add(coll_name)
            continue

        print(f"{'='*60}")
        print(f"Collection: {coll_name} ({point_count} points)")
        print(f"{'='*60}")

        offset = None
        coll_classified = 0
        coll_skipped = 0
        coll_failed = 0

        while True:
            points, next_offset = client.scroll(
                collection_name=coll_name,
                offset=offset,
                limit=SCROLL_BATCH,
                with_payload=True,
                with_vectors=False,
            )

            if not points:
                break

            for point in points:
                payload = point.payload or {}
                content = payload.get("content", "")
                source = payload.get("source", "")
                title = payload.get("title", "")
                metadata = payload.get("metadata", {})

                if not content.strip():
                    coll_skipped += 1
                    continue

                filename = source or title or "unknown"
                classification = classify_with_llm(content, filename, facets)

                if classification:
                    if not args.dry_run:
                        updated_metadata = {**metadata, **classification}
                        for attempt in range(3):
                            try:
                                client.set_payload(
                                    collection_name=coll_name,
                                    payload={"metadata": updated_metadata},
                                    points=[point.id],
                                )
                                break
                            except Exception as e:
                                if attempt < 2:
                                    print(f"  Qdrant write retry {attempt+1}/3: {e}")
                                    time.sleep(5 * (attempt + 1))
                                else:
                                    print(f"  Qdrant write failed after 3 attempts: {e}")
                                    raise
                    coll_classified += 1
                    consecutive_failures = 0  # reset on success
                else:
                    coll_failed += 1
                    consecutive_failures += 1
                    if coll_failed <= 3:
                        print(f"  FAIL: {filename[:60]}")

                    # If many consecutive failures, Ollama may be down
                    if consecutive_failures >= 5:
                        print(f"\n  {consecutive_failures} consecutive failures — checking Ollama...")
                        if not _check_ollama():
                            # Save checkpoint before waiting
                            _save_checkpoint({
                                "completed_collections": list(completed),
                                "total_classified": total_classified + coll_classified,
                                "total_failed": total_failed + coll_failed,
                            })
                            if not _wait_for_ollama():
                                print("  Exiting. Run again to resume from checkpoint.")
                                sys.exit(1)
                        consecutive_failures = 0

            offset = next_offset
            if offset is None:
                break

            processed = coll_classified + coll_skipped + coll_failed
            pct = (processed / point_count * 100) if point_count else 0
            print(f"  {processed}/{point_count} ({pct:.0f}%) — "
                  f"classified={coll_classified} skipped={coll_skipped} failed={coll_failed}",
                  end="\r")

        print(f"\n  Done: classified={coll_classified}, skipped={coll_skipped}, failed={coll_failed}")
        total_classified += coll_classified
        total_skipped += coll_skipped
        total_failed += coll_failed
        completed.add(coll_name)

        # Save checkpoint after each collection
        _save_checkpoint({
            "completed_collections": list(completed),
            "total_classified": total_classified,
            "total_failed": total_failed,
        })

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"ENRICHMENT COMPLETE{'  (dry run)' if args.dry_run else ''}")
    print(f"{'='*60}")
    print(f"  Collections: {len(collections)}")
    print(f"  Classified:  {total_classified}")
    print(f"  Skipped:     {total_skipped}")
    print(f"  Failed:      {total_failed}")
    print(f"  Time:        {elapsed:.0f}s ({elapsed/60:.1f} min)")

    # Clean up checkpoint on successful completion
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print(f"  Checkpoint cleared (run complete).")


if __name__ == "__main__":
    main()
