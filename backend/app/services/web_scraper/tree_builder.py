"""
Site tree building utilities.

Builds hierarchical tree structures from URL lists.
"""

from urllib.parse import urlparse
from .types import SiteNode


def build_tree_from_urls(urls: list[str], base_title: str = "Sitemap") -> SiteNode:
    """
    Build a SiteNode tree structure from a flat list of URLs.

    Groups URLs by path segments for a hierarchical view.
    """
    if not urls:
        return SiteNode(url="", title=base_title, path="/")

    # Parse all URLs and group by path segments
    parsed_urls = [(url, urlparse(url)) for url in urls]

    # Create root node
    root = SiteNode(
        url=urls[0] if urls else "",
        title=base_title,
        path="/",
    )

    # Group URLs by first significant path segment
    groups: dict[str, list[str]] = {}
    for url, parsed in parsed_urls:
        # Get path segments
        segments = [s for s in parsed.path.split('/') if s]
        if len(segments) >= 2:
            # Use second-to-last segment as group (e.g., "guide" from /docs/.../guide/page.html)
            group_key = segments[-2] if len(segments) > 1 else segments[0]
        else:
            group_key = "root"

        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(url)

    # Create child nodes for each group
    for group_name, group_urls in sorted(groups.items()):
        group_node = SiteNode(
            url=group_urls[0],
            title=f"{group_name} ({len(group_urls)} pages)",
            path=f"/{group_name}",
        )

        # Add individual pages as children
        for url in group_urls:
            parsed = urlparse(url)
            page_name = parsed.path.split('/')[-1] or parsed.path
            page_node = SiteNode(
                url=url,
                title=page_name,
                path=parsed.path,
            )
            group_node.children.append(page_node)

        root.children.append(group_node)

    return root


def organize_nodes_into_tree(root: SiteNode, nodes: list[SiteNode], base_url: str):
    """Organize flat list of nodes into tree structure by URL path."""
    base_parsed = urlparse(base_url)

    # Sort nodes by path depth
    nodes = sorted(nodes, key=lambda n: len(urlparse(n.url).path.split('/')))

    # Build parent-child relationships
    for node in nodes:
        if node.url == root.url:
            continue

        # Find the best parent (longest matching path prefix)
        node_path = urlparse(node.url).path
        best_parent = root
        best_depth = 0

        for potential_parent in nodes:
            if potential_parent.url == node.url:
                continue

            parent_path = urlparse(potential_parent.url).path

            # Check if this could be a parent (node path starts with parent path)
            if node_path.startswith(parent_path) and node_path != parent_path:
                parent_depth = len(parent_path.split('/'))
                if parent_depth > best_depth:
                    best_parent = potential_parent
                    best_depth = parent_depth

        # Add as child if not already there
        if node not in best_parent.children:
            best_parent.children.append(node)
