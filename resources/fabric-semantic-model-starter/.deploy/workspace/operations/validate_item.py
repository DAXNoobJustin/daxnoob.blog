"""Validate item directory structure before deployment."""

import json
from pathlib import Path


def validate_item(item_name, item_type, context, workspace=None, item_directory=None, **kwargs):  # noqa: ARG001
    """Check that an item has a valid .platform file and definition files."""
    item_dir = Path(item_directory) if item_directory else Path(context.repository_directory) / f"{item_name}.{item_type}"

    if not item_dir.exists():
        msg = f"Item directory not found: {item_dir}"
        raise FileNotFoundError(msg)

    # Check .platform metadata
    platform_file = item_dir / ".platform"
    if not platform_file.exists():
        msg = f"Missing .platform file in {item_name}.{item_type}"
        raise FileNotFoundError(msg)

    with platform_file.open() as f:
        platform = json.load(f)

    display_name = platform.get("metadata", {}).get("displayName", "unknown")
    meta_type = platform.get("metadata", {}).get("type", "unknown")

    # Count definition files (exclude .platform and hidden files)
    file_count = sum(
        1 for f in item_dir.rglob("*")
        if f.is_file() and f.name != ".platform" and not f.name.startswith(".")
    )

    if file_count == 0:
        msg = f"No definition files found in {item_name}.{item_type}"
        raise RuntimeError(msg)

    print(f"      [OK] {display_name} ({meta_type}) - {file_count} definition files")
