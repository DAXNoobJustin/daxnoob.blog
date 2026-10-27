---
title: "Unit Testing Semantic Models with DAX"
description: "A tool that runs YAML-defined DAX assertions against your semantic models over the XMLA endpoint, and on Direct Lake, deploys a temporary copy of the model for each pull request to test the change."
draft: true
date:
  created: 2026-10-27
categories:
  - DevOps
  - DAX
tags:
  - Microsoft Fabric
  - Power BI
  - DAX
  - Testing
  - CI/CD
  - Semantic Model
authors:
  - justinmartin
slug: semantic-model-dax-testing
image: assets/images/posts/semantic-model-dax-testing/hero.png
---

## Introduction

Our team is constantly making changes to our semantic models (adding new measures, renaming columns, adding tables, etc.). Just because the changes still result in a valid schema and refreshes are still successful doesn't mean our queries still return the expected results.

I wanted a way to write some DAX, define what the result should look like, and fail the build/deployment if it doesn't match expectations.

In this post, I'll walk through how we accomplished this. I'll start with the tester and then show how we use it in our pull requests, where each PR publishes a temporary copy of the model, tests it, and then deletes it. You can find the code here: [GitHub](https://github.com/DAXNoobJustin/daxnoob.blog/tree/main/resources/semantic-model-tests).

<!-- more -->

## Part 1: the tester

The tester is a small Python command line tool that takes a folder of YAML test cases and runs the DAX for each case over the XMLA endpoint and prints a pass/fail summary. There are three types of assertions:

- **structural**: checks the *shape* of the result (row count, columns, or whether a value is present).
- **negative**: the query *must* fail, and the error must match a regex. For example, does a bad reference return the error you expect?
- **snapshot**: saves the exact result to a file the first time it runs, then fails if the result ever changes. This is useful for locking in the output of a calculation.

```yaml
cases:
  - id: measure_resolves
    category: structural
    dax: "EVALUATE { [Total Amount] }"
    expected_row_count: { exact: 1 }

  - id: bad_measure_errors
    category: negative
    dax: "EVALUATE { [No Such Measure] }"
    expected_error_regex: "cannot be determined|not a valid|no such"

  - id: amount_by_category      # snapshot - baseline captured with --update-snapshots
    category: snapshot
    dax: "EVALUATE SUMMARIZECOLUMNS ( Product[Category], \"Amount\", [Total Amount] ) ORDER BY Product[Category]"
```

That's really all there is to it. You have a folder of these test cases, you run them in your pipeline, and the build fails if one of them breaks.

```mermaid
flowchart LR
    Y["YAML cases"] --> R["run_tests.py"]
    R -->|"DAX over XMLA"| M["Deployed semantic model"]
    M -->|"rows"| R
    R --> P["pass / fail + exit code"]
```

The tool exits with `0` if everything passes, `1` if an assertion fails, or `2` if the tool itself couldn't run (bad login, can't reach the model, etc.).

!!! warning "Snapshots include your data"
    A snapshot compares the result of the model *and* the data, so a normal data refresh can change it too. Point your snapshots at stable test data so a failed build means something actually broke, not that yesterday's numbers changed.

!!! note "Requirements"
    - **Windows only.** Queries run over XMLA using the AdomdClient .NET library, which requires .NET Framework. It's downloaded from NuGet the first time you run the tool.
    - **Auth.** A regular `az login` token gets rejected by the XMLA endpoint, so use `--interactive-auth` when running locally. Service principals work as-is.

## Part 2: a disposable model per pull request

The framework above assumes that you have a model to test against, but how can you test the changes before you actually make them to your production model? 

In our pipelines, we use `--deploy-from` which allows you to point at the `*.SemanticModel/` folder in your repo and deploy a new copy of your model to the service to test against:

```mermaid
flowchart TD
    S["Source TMDL in the PR branch"] --> ST["Stage: copy, rename,<br/>strip RLS"]
    ST --> P["Publish throwaway<br/>TEST_Model_a1b2c3d4"]
    P --> B["Bind connections"]
    B --> R["Refresh"]
    R --> T["Run the catalog over XMLA"]
    T --> D["DELETE the throwaway"]
    D --> X["pass / fail + exit code"]
```

Here's what each step does:

**Stage.** Copies the TMDL to a temp folder and changes the `displayName` in `.platform`. fabric-cicd matches existing items by **type + display name**, so a new name creates a second model instead of overwriting your real one. It also removes `definition/roles/`, since the service principal isn't a member of any RLS role.

**Publish.** Uses [fabric-cicd](https://github.com/microsoft/fabric-cicd) with `unpublish.skip: true`. By default, fabric-cicd removes anything in the workspace that isn't in your source folder, and in this case your source folder only has the one staged model. Without it, you'd delete the other models in the workspace.

**Bind.** A newly published Direct Lake model doesn't have any connections bound to it, so the refresh could fail until you add them. The tool binds the connection(s) you pass in with `--connection-id`. You need to set up the connection in Fabric ahead of time and give the identity running the tests `Use` permission on it. The refresh runs under the connection's identity, which is how a temporary model in a dev workspace can still refresh against prod data.

**Delete.** Runs in a `finally` block, so the temporary model gets deleted even if an assertion fails or the publish errors out. If the model id was never captured, it looks the model up by name before giving up. If the pipeline gets killed, the `finally` block won't run, so if you're running this a lot, it's a good idea to schedule a cleanup job for leftover `TEST_*` models.

### Direct Lake vs. Import

Many of the benefits of this system depend on having a Direct Lake or DirectQuery model. Both of these model types don't need a long refresh process before you can query them which enables us to quickly spin up a net new model and tear it down on each pull request. Import models have to load all of their data before any data assertion can run, and a `Full` refresh on large models would be impractical. If you're using Import, unless the full refresh is fast, I'd stick with Part 1 and keep your PR tests to metadata and shape checks (does the measure resolve, does the query run, does a bad reference still error, etc.). None of those need data loaded.

There's another benefit to refreshing the temporary model during testing: it proves that the connections bind, the credentials work, and the upstream schema still matches. If someone renamed a lakehouse column, the refresh fails in the PR instead of in tomorrow's scheduled refresh or during query time. Keep in mind that a successful refresh doesn't mean there's data, since an empty table refreshes just fine. If you want to check for that, add an assertion:

```yaml
  - id: sales_has_rows
    category: structural
    dax: "EVALUATE TOPN ( 1, Sales )"
    expected_row_count: { min: 1 }
```

## Trying it

`examples/sample.yml` has an example of each assertion type. There are also pipeline templates in `ci/` for both modes.

```powershell
pip install -r requirements.txt
az login   # or add --interactive-auth to the commands below

# Part 1: test a model you've already deployed.
# Capture the snapshot baseline once, review the sidecar, commit it:
python run_tests.py --workspace-id <ws-guid> --model "Your Model" `
    --catalog-dir tests --update-snapshots

python run_tests.py --workspace-id <ws-guid> --model "Your Model" `
    --catalog-dir tests

# Part 2: publish a throwaway from the TMDL in your branch, test it, delete it.
python run_tests.py --workspace-id <ws-guid> `
    --deploy-from "MODELS/Your Model.SemanticModel" `
    --connection-id <connection-guid> `
    --catalog-dir tests
```

Here is what a Part 2 run looks like:

```terminal
==> Source:     MODELS/Your Model.SemanticModel
==> Throwaway:  TEST_YourModel_530c9cee
==> Workspace:  11111111-2222-3333-4444-555555555555
==> Cases:      4 from 1 dir(s)
==> Publishing throwaway
==> Model id:   aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
    Refreshing (Full/transactional, poll timeout 1200s)
==> Refresh complete in 5.1s
==> Running 4 case(s) via AdomdClient (XMLA)
==> AdomdClient XMLA batch: 4 queries
==> All queries complete in 4.9s
==> Teardown:   deleted

================================================================================
  4 run, 4 passed, 0 failed
================================================================================
  [PASS] structural  order_count_resolves
  [PASS] structural  product_categories_present
  [PASS] negative    missing_measure_errors
  [PASS] snapshot    total_amount_by_category
```

The whole thing (deploy, refresh, four assertions, and teardown) took about 25 seconds. When a snapshot changes, you get the diff:

```terminal
  [FAIL] snapshot    total_amount_by_category
           snapshot mismatch:
           --- expected
           +++ actual
           -[{"Product[Category]": "Hardware", "[Total Amount]": 9999}, ...
           +[{"Product[Category]": "Hardware", "[Total Amount]": 9000}, ...
```

The [README](https://github.com/DAXNoobJustin/daxnoob.blog/tree/main/resources/semantic-model-tests) has all of the parameters, the auth details, and the permissions each mode needs (Viewer for Part 1, Contributor for Part 2 since it creates and deletes items).

## Conclusion

This framework has given us a lot of peace of mind and has stopped us from shipping mistakes several times. The full source code is on [GitHub](https://github.com/DAXNoobJustin/daxnoob.blog/tree/main/resources/semantic-model-tests). I hope you find it helpful.

Like always, if you have any questions or feedback, please reach out. I'd love to hear from you!
