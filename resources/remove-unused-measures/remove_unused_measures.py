#!/usr/bin/env python3
"""
Remove unused report-level measures from Power BI Report (PBIR) files.

Usage:
    python remove_unused_measures.py <report_folder> [--execute] [--ignore-unapplied-filters]
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import argparse


class PBIRMeasureCleaner:
    """Remove unused report-level measures from PBIR reports."""

    def __init__(self, report_path: str):
        """Initialize with path to .Report folder."""
        self.report_path = Path(report_path)
        if not self.report_path.exists():
            raise FileNotFoundError(f"Report path not found: {report_path}")
        
        self.definition_path = self.report_path / "definition"
        self.report_extensions_path = self.definition_path / "reportExtensions.json"
        self.report_json_path = self.definition_path / "report.json"
        
        if not self.definition_path.exists():
            raise FileNotFoundError(f"Definition folder not found: {self.definition_path}")
    
    def _load_json_file(self, file_path: Path) -> dict:
        """Load JSON file with UTF-8 BOM handling."""
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            print(f"⚠️  Error loading {file_path}: {e}")
            return {}
    
    def _save_json_file(self, file_path: Path, data: dict):
        """Save JSON file with proper formatting."""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _load_all_report_parts(self) -> List[dict]:
        """Load all JSON files from the report definition."""
        parts = []
        
        if self.report_json_path.exists():
            parts.append({
                'path': 'definition/report.json',
                'payload': self._load_json_file(self.report_json_path)
            })
        
        pages_path = self.definition_path / "pages"
        if pages_path.exists():
            for page_folder in pages_path.iterdir():
                if page_folder.is_dir():
                    page_json = page_folder / "page.json"
                    if page_json.exists():
                        parts.append({
                            'path': f'definition/pages/{page_folder.name}/page.json',
                            'payload': self._load_json_file(page_json)
                        })
                    
                    visuals_path = page_folder / "visuals"
                    if visuals_path.exists():
                        for visual_folder in visuals_path.iterdir():
                            if visual_folder.is_dir():
                                visual_json = visual_folder / "visual.json"
                                if visual_json.exists():
                                    parts.append({
                                        'path': f'definition/pages/{page_folder.name}/visuals/{visual_folder.name}/visual.json',
                                        'payload': self._load_json_file(visual_json)
                                    })
        
        bookmarks_path = self.definition_path / "bookmarks"
        if bookmarks_path.exists():
            for bookmark_file in bookmarks_path.glob("*.bookmark.json"):
                parts.append({
                    'path': f'definition/bookmarks/{bookmark_file.name}',
                    'payload': self._load_json_file(bookmark_file)
                })
        
        return parts
    
    def list_report_level_measures(self) -> List[Dict[str, str]]:
        """List all report-level measures in the report."""
        if not self.report_extensions_path.exists():
            return []
        
        extensions_data = self._load_json_file(self.report_extensions_path)
        measures = []
        
        for entity in extensions_data.get("entities", []):
            table_name = entity.get("name")
            for measure in entity.get("measures", []):
                measures.append({
                    "Measure Name": measure.get("name"),
                    "Table Name": table_name,
                    "Expression": measure.get("expression"),
                    "Data Type": measure.get("dataType"),
                    "Format String": measure.get("formatString"),
                    "Data Category": measure.get("dataCategory"),
                })
        
        return measures
    
    def _is_measure_referenced(
        self, 
        json_data, 
        measure_name: str, 
        entity_name: str, 
        path: str = "", 
        pattern=None,
        ignore_unapplied_filters: bool = False
    ) -> bool:
        """Recursively check if a measure is referenced in JSON data."""
        if isinstance(json_data, dict):
            if ignore_unapplied_filters and "filterConfig" in path:
                if "field" in json_data and "Measure" in json_data.get("field", {}):
                    measure_obj = json_data["field"]["Measure"]
                    if isinstance(measure_obj, dict):
                        property_name = measure_obj.get("Property")
                        measure_entity = measure_obj.get("Expression", {}).get("SourceRef", {}).get("Entity")
                        if property_name == measure_name and measure_entity == entity_name:
                            return "filter" in json_data
            
            if "Measure" in json_data:
                measure_obj = json_data["Measure"]
                if isinstance(measure_obj, dict):
                    property_name = measure_obj.get("Property")
                    measure_entity = measure_obj.get("Expression", {}).get("SourceRef", {}).get("Entity")
                    if property_name == measure_name and measure_entity == entity_name:
                        return True
            
            if "Expression" in json_data and isinstance(json_data["Expression"], str):
                if pattern and pattern.search(json_data["Expression"]):
                    return True
            
            for key, value in json_data.items():
                new_path = f"{path}.{key}" if path else key
                if self._is_measure_referenced(value, measure_name, entity_name, new_path, pattern, ignore_unapplied_filters):
                    return True
        
        elif isinstance(json_data, list):
            for item in json_data:
                if self._is_measure_referenced(item, measure_name, entity_name, path, pattern, ignore_unapplied_filters):
                    return True
        
        return False
    
    def remove_unused_measures(
        self, 
        dry_run: bool = True, 
        ignore_unapplied_filters: bool = False
    ) -> Tuple[List[Dict[str, str]], int]:
        """Remove unused measures. Returns (removed measures, iteration count)."""
        measures = self.list_report_level_measures()
        if not measures:
            print("ℹ️  No report-level measures found in the report.")
            return [], 0
        
        print(f"📊 Found {len(measures)} report-level measures")
        
        all_removed_measures = []
        virtually_removed = set()
        iteration = 0
        max_iterations = 10
        report_parts = self._load_all_report_parts()
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n🔄 Iteration {iteration}...")
            
            current_measures = [
                m for m in measures 
                if m["Measure Name"] not in virtually_removed
            ]
            
            if not current_measures:
                break
            
            measure_map = {m["Measure Name"]: m["Table Name"] for m in current_measures}
            used_measures = set()
            
            for measure in current_measures:
                measure_name = measure["Measure Name"]
                entity_name = measure["Table Name"]
                measure_pattern = re.compile(r"\[" + re.escape(measure_name) + r"\]")
                
                for part in report_parts:
                    if part['path'] == str(self.report_extensions_path):
                        continue
                    
                    if self._is_measure_referenced(
                        part['payload'], 
                        measure_name, 
                        entity_name, 
                        pattern=measure_pattern,
                        ignore_unapplied_filters=ignore_unapplied_filters
                    ):
                        used_measures.add(measure_name)
                        break
            
            if self.report_extensions_path.exists():
                extensions_data = self._load_json_file(self.report_extensions_path)
                
                for entity in extensions_data.get("entities", []):
                    for measure in entity.get("measures", []):
                        if dry_run and measure.get("name") in virtually_removed:
                            continue
                        
                        expr = measure.get("expression", "")
                        if isinstance(expr, str):
                            for ref in re.findall(r"\[([^\]]+)\]", expr):
                                if ref in measure_map:
                                    used_measures.add(ref)
            
            unused_measures = [
                m["Measure Name"] for m in current_measures 
                if m["Measure Name"] not in used_measures
            ]
            
            if not unused_measures:
                print("✅ No unused measures found in this iteration")
                break
            
            print(f"   Found {len(unused_measures)} unused measure(s)")
            
            removed_in_iteration = [
                m for m in current_measures 
                if m["Measure Name"] in unused_measures
            ]
            
            if not dry_run:
                removed_measure_set = {(m["Measure Name"], m["Table Name"]) for m in removed_in_iteration}
                
                self._remove_measures_from_file(unused_measures)
                
                for part in report_parts:
                    if 'definition/reportExtensions.json' in part['path']:
                        continue
                    
                    payload = part['payload']
                    if "filterConfig" in payload and "filters" in payload["filterConfig"]:
                        original_filters = payload["filterConfig"]["filters"]
                        cleaned_filters = [
                            flt for flt in original_filters
                            if not (
                                "field" in flt and 
                                "Measure" in flt.get("field", {}) and
                                isinstance(flt["field"]["Measure"], dict) and
                                (flt["field"]["Measure"].get("Property"), 
                                 flt["field"]["Measure"].get("Expression", {}).get("SourceRef", {}).get("Entity")) in removed_measure_set
                            )
                        ]
                        
                        if len(cleaned_filters) < len(original_filters):
                            payload["filterConfig"]["filters"] = cleaned_filters
                            file_path = self.definition_path / part['path'].replace('definition/', '')
                            self._save_json_file(file_path, payload)
                
                report_parts = self._load_all_report_parts()
                measures = self.list_report_level_measures()
            else:
                virtually_removed.update(unused_measures)
            
            all_removed_measures.extend(removed_in_iteration)
        
        return all_removed_measures, iteration
    
    def _remove_measures_from_file(self, measure_names: List[str]):
        """Remove specified measures from reportExtensions.json."""
        if not self.report_extensions_path.exists():
            return
        
        extensions_data = self._load_json_file(self.report_extensions_path)
        
        for entity in extensions_data.get("entities", []):
            entity["measures"] = [
                m for m in entity.get("measures", []) 
                if m.get("name") not in measure_names
            ]
        
        extensions_data["entities"] = [
            e for e in extensions_data.get("entities", []) 
            if e.get("measures")
        ]
        
        if extensions_data.get("entities"):
            self._save_json_file(self.report_extensions_path, extensions_data)
        else:
            self.report_extensions_path.unlink()
            print("   🗑️  Removed reportExtensions.json (no measures left)")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Remove unused report-level measures from Power BI Report (PBIR) files."
    )
    
    parser.add_argument(
        "report_path",
        help="Path to the .Report folder (e.g., 'MyReport.Report')"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually remove measures (default is dry-run mode)"
    )
    parser.add_argument(
        "--ignore-unapplied-filters",
        action="store_true",
        help="Consider measures in filter panes without applied logic as unused"
    )
    
    args = parser.parse_args()
    
    try:
        cleaner = PBIRMeasureCleaner(args.report_path)
        
        print(f"🔍 Analyzing report: {args.report_path}")
        print(f"   Mode: {'REMOVE' if args.execute else 'DRY RUN'}")
        print(f"   Ignore unapplied filters: {args.ignore_unapplied_filters}")
        
        removed_measures, iterations = cleaner.remove_unused_measures(
            dry_run=not args.execute,
            ignore_unapplied_filters=args.ignore_unapplied_filters
        )
        
        if removed_measures:
            action = "Removed" if args.execute else "Would remove"
            print(f"\n{'✅' if args.execute else 'ℹ️ '} {action} {len(removed_measures)} unused measure(s) in {iterations} iteration(s):")
            for measure in removed_measures:
                print(f"   - {measure['Table Name']}.{measure['Measure Name']}")
        else:
            print("\n✅ No unused report-level measures found.")
        
        if not args.execute and removed_measures:
            print("\n💡 Run with --execute to actually remove these measures.")
    
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
