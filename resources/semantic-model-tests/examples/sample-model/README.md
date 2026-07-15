# Sales Sample — a runnable end-to-end example

A tiny, self-contained semantic model plus a matching test catalog, so you can see
the tool work against something real before pointing it at your own model.

## What's here

```
sample-model/
├── Sales Sample.SemanticModel/   an Import-mode model that generates its own data
│   └── definition/               (Power Query, no external source) — 2 tables,
│                                 4 measures, 1 relationship
└── tests/
    └── sample.yml                4 example cases (structural, negative, snapshot)
```

The model has a `Sales` fact (240 deterministic rows generated in M) and a `Product`
dimension (5 products across Hardware / Software / Services), with measures
`[Total Amount]`, `[Total Quantity]`, `[Order Count]`, and `[Average Order Value]`.
Because the data is a pure function of the row index, **every refresh produces the
same rows** — which is what makes the snapshot case reproducible.

## 1. Deploy the model

Publish `Sales Sample.SemanticModel` to a Fabric / Power BI workspace with whatever
you already use — Power BI Desktop, Tabular Editor, or
[fabric-cicd](https://github.com/microsoft/fabric-cicd). It's a stock TMDL semantic
model. Then refresh it once (it's Import; the refresh is instant — 240 rows with no
external source).

## 2. Capture the snapshot baseline (one time)

The catalog includes a `snapshot` case. A snapshot needs a captured baseline, so
the first thing to do is capture it (this runs only the snapshot cases and writes
the sidecar):

```bash
python run_tests.py \
    --workspace-id <your-workspace-guid> \
    --model "Sales Sample" \
    --catalog-dir examples/sample-model/tests \
    --update-snapshots
```

Review the generated `tests/__snapshots__/sample.yml` and commit it. From now on
every run asserts that result is unchanged — so a changed calculation, a dropped
category, or a data regression turns the build red.

## 3. Run the tests

```bash
python run_tests.py \
    --workspace-id <your-workspace-guid> \
    --model "Sales Sample" \
    --catalog-dir examples/sample-model/tests
```

All four cases pass. (If you skip step 2, the run stops up front with exit code 2,
telling you the snapshot case has no captured value yet.)

That's the whole loop: **write DAX, say what the result should look like, fail if it
changes.**
