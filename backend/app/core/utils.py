"""
Core utility functions.
"""
import re
import unicodedata


def slugify(text: str, max_length: int = 50) -> str:
    """
    Convert text to a URL/collection-name-safe slug.

    - Converts to lowercase
    - Replaces spaces and special chars with underscores
    - Removes non-alphanumeric characters (except underscores)
    - Truncates to max_length
    - Strips leading/trailing underscores

    Examples:
        "My Knowledge Base" -> "my_knowledge_base"
        "API Docs (v2.0)" -> "api_docs_v2_0"
        "ACME Product Docs" -> "acme_product_docs"
    """
    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Convert to lowercase
    text = text.lower()

    # Replace spaces, hyphens, and other separators with underscores
    text = re.sub(r"[\s\-./]+", "_", text)

    # Remove any characters that aren't alphanumeric or underscores
    text = re.sub(r"[^a-z0-9_]", "", text)

    # Collapse multiple underscores
    text = re.sub(r"_+", "_", text)

    # Strip leading/trailing underscores
    text = text.strip("_")

    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length].rstrip("_")

    # Fallback if empty
    if not text:
        text = "collection"

    return text


def generate_collection_name(name: str, unique_id: str, prefix: str = "") -> str:
    """
    Generate a user-friendly Qdrant collection name.

    Format: {prefix}{slugified_name}_{short_id}

    Examples:
        ("My Docs", "abc123-def456") -> "my_docs_abc123de"
        ("API Reference", "xyz789", "kb_") -> "kb_api_reference_xyz789"

    Args:
        name: Human-readable name to slugify
        unique_id: Unique identifier (UUID) - first 8 chars used
        prefix: Optional prefix for the collection name

    Returns:
        A valid Qdrant collection name
    """
    # Slugify the name (max 50 chars to leave room for prefix and ID)
    slug = slugify(name, max_length=50)

    # Take first 8 characters of the unique ID (remove hyphens first)
    short_id = unique_id.replace("-", "")[:8]

    # Combine: prefix + slug + short_id
    collection_name = f"{prefix}{slug}_{short_id}"

    return collection_name
