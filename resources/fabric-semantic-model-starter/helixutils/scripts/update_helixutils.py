#!/usr/bin/env python
"""
CLI to build helixutils and update wheels across the workspace.

Note: this replaces *existing* helixutils-*.whl files under the workspace
Environments. A fresh checkout ships no committed wheels, so the first build
has nothing to replace and exits as a no-op — drop a built wheel into each
Env_*/Libraries/CustomLibraries/ folder once, then this keeps them in sync.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def find_built_wheel(dist_dir: Path) -> Path | None:
    """Find the helixutils wheel in dist directory."""
    wheels = list(dist_dir.glob("helixutils-*.whl"))
    return wheels[0] if wheels else None


def find_target_wheels(workspace_dir: Path) -> list[Path]:
    """Find all helixutils wheels in the workspace."""
    return list(workspace_dir.rglob("helixutils-*.whl"))


def main():
    """Build the helixutils wheel and replace the copies under each workspace environment's CustomLibraries/."""
    # Resolve paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    repo_root = project_root.parent
    dist_dir = project_root / "dist"
    workspace_dir = repo_root / "workspace"

    if not workspace_dir.exists():
        print(f"Error: Workspace directory not found: {workspace_dir}")
        sys.exit(1)

    # Clean dist directory
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    # Build wheel
    print("Building helixutils...")
    result = subprocess.run(
        ["uv", "build"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Build failed:\n{result.stderr}")
        sys.exit(1)

    print(result.stdout)

    # Find new wheel
    new_wheel = find_built_wheel(dist_dir)
    if not new_wheel:
        print("Error: No wheel found in dist directory after build")
        sys.exit(1)

    print(f"Built: {new_wheel.name}")

    # Find target wheels
    target_wheels = find_target_wheels(workspace_dir)

    if not target_wheels:
        print(f"No helixutils wheels found in {workspace_dir}")
        sys.exit(0)

    print(f"\nFound {len(target_wheels)} wheel(s) to update:")
    for wheel in target_wheels:
        print(f"  - {wheel}")

    # Replace wheels
    print("\nUpdating wheels...")
    for target_wheel in target_wheels:
        target_path = target_wheel.parent / new_wheel.name
        # Remove old wheel
        target_wheel.unlink()
        # Copy new wheel
        shutil.copy(new_wheel, target_path)
        print(f"  Updated: {target_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
