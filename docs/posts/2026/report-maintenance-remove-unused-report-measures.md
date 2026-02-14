---
title: "Report Maintenance: Remove Unused Report Measures"
description: "You spend a lot of time designing a report, carefully crafting measures specific to that report's needs. When it is time for a new report, it is often easiest to copy the existing one as a starting point..."
draft: true
date:
  created: 2026-02-13
categories:
  - Administration
tags:
  - Power BI
  - Python
  - Semantic Model
  - Microsoft Fabric
  - Fabric Notebook
authors:
  - justinmartin
slug: report-maintenance-remove-unused-report-measures
# image: assets/images/posts/report-maintenance-remove-unused-report-measures/image.png
---

## Introduction

You spend a lot of time designing a report — carefully crafting measures specific to that report's needs. When it is time for a new report, it is often easiest to copy the existing one as a starting point. And why wouldn't you? The layout is there, the connections are set, and you have a head start.

From there, it is easy enough to delete unneeded pages and swap out visuals for new ones. But what about the report-level measures? How many of us actually take the time to clean those up? Be honest. 🙂

Before you know it, the snowball effect kicks in. One copied report becomes two, two becomes ten, and each one carries forward a growing collection of measures that no one uses anymore. The measure list in the model object view becomes almost unmanageable — scrolling through hundreds of entries just to find the one you need.

This happened on my team. We had dozens of reports, each with hundreds of unused report-level measures. It was a nightmare.

<!-- TODO: Add screenshot showing bloated measure list -->

## The Solution

The new [PBIR format](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report) changes things. Because report definitions are now stored as structured JSON files, we can programmatically scan for measures that are not referenced anywhere in the report and remove them.

I created two tools to handle this, depending on where your report lives:

1. **[Python Script](https://github.com/DAXNoobJustin/daxnoob.blog/blob/main/resources/remove-unused-measures/remove_unused_measures.py)** — For local PBIP projects with PBIR enabled. Run it against your `.Report` folder to find and remove unused measures.
2. **[Fabric Notebook](https://github.com/DAXNoobJustin/daxnoob.blog/blob/main/resources/remove-unused-measures/Remove%20Unused%20Measures.ipynb)** — For reports in the Fabric service. Uses a monkey-patched version of [Semantic Link Labs](https://github.com/microsoft/semantic-link-labs) to connect to a report and clean up unused measures directly.

Both tools work the same way under the hood:

1. Scan the report definition for all report-level measures
2. Check each measure to see if it is referenced in any visual, filter, page, or bookmark
3. Check if any other report-level measure depends on it
4. Remove unreferenced measures iteratively (since removing one measure might make another one unused)

## The Python Script (Local PBIP)

<!-- TODO: Brief description of how to use the script -->

The script runs from the command line and takes a path to your `.Report` folder.

**Dry run** (preview what would be removed):

```bash
python remove_unused_measures.py "path/to/MyReport.Report"
```

**Execute** (actually remove the measures):

```bash
python remove_unused_measures.py "path/to/MyReport.Report" --execute
```

There is also an `--ignore-unapplied-filters` flag. By default, if a measure appears in a filter pane — even if no filter logic has been applied — it is considered "used." With this flag, those measures will be treated as unused.

<!-- TODO: Add screenshot of script output -->

## The Fabric Notebook (Service)

<!-- TODO: Brief description of how to use the notebook -->

The notebook monkey-patches a `remove_unused_report_level_measures` method onto Semantic Link Labs' `ReportWrapper` class. This lets you connect to any report in the Fabric service and clean up unused measures without downloading anything.

<!-- TODO: Add screenshot of notebook output -->

## Example

<!-- TODO: Walk through a real example with before/after screenshots -->

## Conclusion

Taking a few minutes to clean up unused report measures can make a real difference in the maintainability of your reports. I hope these tools help you and your team keep things tidy.

Like always, if you have any questions or feedback, please reach out. I'd love to hear from you!
