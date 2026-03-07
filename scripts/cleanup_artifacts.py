#!/usr/bin/env python
"""
Artifact Cleanup Utility for Autonomous Coding Agent
=====================================================

Cleans up and organizes scattered files in generated projects:
- Screenshots -> screenshots/
- Test scripts -> scripts/
- Session notes -> docs/
- Old screenshots (>7 days) -> deleted or archived

Usage:
    python cleanup_artifacts.py <project_dir> [--organize] [--cleanup-old] [--dry-run]

Examples:
    # Just show what would be done
    python cleanup_artifacts.py ./generations/my_project --dry-run
    
    # Organize scattered files into proper directories
    python cleanup_artifacts.py ./generations/my_project --organize
    
    # Delete old screenshots (>7 days old)
    python cleanup_artifacts.py ./generations/my_project --cleanup-old
"""

import argparse
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path


def get_file_age_days(path: Path) -> float:
    """Get file age in days."""
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.now() - mtime).total_seconds() / 86400


def organize_files(project_dir: Path, dry_run: bool = False) -> dict:
    """Organize scattered files into proper directories."""
    results = {
        "screenshots": [],
        "scripts": [],
        "docs": [],
        "skipped": []
    }
    
    # Patterns for each category
    script_patterns = [
        'test_', 'check_', 'debug_', 'verify_', 'quick_', 
        'kill_', 'restart_', 'start_', 'mark_test', 'show_', 
        'find_', 'create_sample', 'update_', 'fix_', 'unmark_',
        'wait_', 'force_', 'aggressive_', 'diagnose_', 'add_'
    ]
    
    doc_patterns = ['session', 'SESSION', 'URGENT', 'NEXT_SESSION', 'KNOWN_ISSUES']
    
    # Create directories
    screenshots_dir = project_dir / "screenshots"
    scripts_dir = project_dir / "scripts"
    docs_dir = project_dir / "docs"
    
    if not dry_run:
        screenshots_dir.mkdir(exist_ok=True)
        scripts_dir.mkdir(exist_ok=True)
        docs_dir.mkdir(exist_ok=True)
    
    # Process files in root
    for file in project_dir.iterdir():
        if not file.is_file():
            continue
        
        filename = file.name
        
        # Screenshots
        if filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            dest = screenshots_dir / filename
            if not dry_run:
                shutil.move(str(file), str(dest))
            results["screenshots"].append(filename)
            continue
        
        # Scripts
        if any(filename.startswith(p) for p in script_patterns) and filename.endswith('.py'):
            dest = scripts_dir / filename
            if not dry_run:
                shutil.move(str(file), str(dest))
            results["scripts"].append(filename)
            continue
        
        # Session notes
        if any(p in filename for p in doc_patterns) and filename.endswith(('.md', '.txt')):
            # Don't move claude-progress.txt or README.md
            if filename in ['claude-progress.txt', 'README.md', 'QUICK_START.md', 'PROJECT_MANIFEST.md']:
                results["skipped"].append(filename)
                continue
            dest = docs_dir / filename
            if not dry_run:
                shutil.move(str(file), str(dest))
            results["docs"].append(filename)
            continue
    
    return results


def cleanup_old_screenshots(project_dir: Path, max_age_days: int = 7, dry_run: bool = False) -> list:
    """Delete screenshots older than max_age_days."""
    deleted = []
    
    screenshots_dir = project_dir / "screenshots"
    if not screenshots_dir.exists():
        # Check root for screenshots
        screenshots_dir = project_dir
    
    for file in screenshots_dir.glob("*.png"):
        age = get_file_age_days(file)
        if age > max_age_days:
            if not dry_run:
                file.unlink()
            deleted.append((file.name, f"{age:.1f} days old"))
    
    return deleted


def show_stats(project_dir: Path) -> None:
    """Show statistics about artifacts."""
    print("\n" + "=" * 60)
    print("  ARTIFACT STATISTICS")
    print("=" * 60)
    
    # Count files in root
    root_files = list(project_dir.glob("*"))
    root_py = [f for f in root_files if f.suffix == '.py' and f.is_file()]
    root_png = [f for f in root_files if f.suffix == '.png' and f.is_file()]
    root_md = [f for f in root_files if f.suffix == '.md' and f.is_file()]
    
    print(f"\nIn project root:")
    print(f"  - Python scripts: {len(root_py)}")
    print(f"  - Screenshots: {len(root_png)}")
    print(f"  - Markdown files: {len(root_md)}")
    
    # Count files in organized directories
    for subdir in ['screenshots', 'scripts', 'docs', 'logs']:
        dir_path = project_dir / subdir
        if dir_path.exists():
            files = list(dir_path.iterdir())
            total_size = sum(f.stat().st_size for f in files if f.is_file()) / 1024
            print(f"\nIn {subdir}/:")
            print(f"  - Files: {len(files)}")
            print(f"  - Size: {total_size:.1f} KB")
    
    # Old screenshots
    all_screenshots = list(project_dir.rglob("*.png"))
    old_screenshots = [f for f in all_screenshots if get_file_age_days(f) > 7]
    if old_screenshots:
        print(f"\n⚠️  Old screenshots (>7 days): {len(old_screenshots)}")
    
    print("-" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Clean up and organize artifacts in generated projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Project directory to clean up"
    )
    
    parser.add_argument(
        "--organize", "-o",
        action="store_true",
        help="Organize scattered files into proper directories"
    )
    
    parser.add_argument(
        "--cleanup-old", "-c",
        action="store_true",
        help="Delete old screenshots (>7 days)"
    )
    
    parser.add_argument(
        "--max-age",
        type=int,
        default=7,
        help="Maximum age in days for screenshots (default: 7)"
    )
    
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    project_dir = args.project_dir.resolve()
    if not project_dir.exists():
        print(f"Error: Project directory does not exist: {project_dir}")
        sys.exit(1)
    
    if args.dry_run:
        print("=== DRY RUN MODE - No changes will be made ===\n")
    
    # Show current stats
    show_stats(project_dir)
    
    # Organize files
    if args.organize:
        print("\nOrganizing files...")
        results = organize_files(project_dir, args.dry_run)
        
        if results["screenshots"]:
            print(f"  Screenshots -> screenshots/: {len(results['screenshots'])} files")
        if results["scripts"]:
            print(f"  Scripts -> scripts/: {len(results['scripts'])} files")
        if results["docs"]:
            print(f"  Docs -> docs/: {len(results['docs'])} files")
        if not any(results.values()):
            print("  Nothing to organize!")
    
    # Cleanup old screenshots
    if args.cleanup_old:
        print(f"\nCleaning up screenshots older than {args.max_age} days...")
        deleted = cleanup_old_screenshots(project_dir, args.max_age, args.dry_run)
        if deleted:
            for name, age in deleted:
                print(f"  Deleted: {name} ({age})")
            print(f"  Total: {len(deleted)} files deleted")
        else:
            print("  No old screenshots to clean up!")
    
    if not args.organize and not args.cleanup_old:
        print("\nNo action specified. Use --organize or --cleanup-old")
        print("Use --dry-run to preview changes")


if __name__ == "__main__":
    main()
