# Renaming the framework namespace

This package ships with the brand **AskADIA** baked in. The upstream repo keeps
it verbatim, so its build output is byte-for-byte stable and it never runs the
rename tool. If you **fork or vendor** this package and want it to carry your own
brand, use `rename_namespace.py`.

## TL;DR

```bash
# from inside the package directory
python rename_namespace.py --pascal DataChat --lower datachat
```

That rewrites the brand everywhere inside the package, renames the brand-named
files (and, by default, the package directory), re-blesses the golden artifacts,
and runs the roundtrip tests so you end up with a clean, self-consistent package.

Then update the **host wiring** that lives *outside* the package (see below) and
commit.

## The brand appears in three case forms

The replacement is case-sensitive and the three forms are disjoint, so each maps
independently:

| Canonical | Flag | Example | Where it appears |
| --------- | ---- | ------- | ---------------- |
| `AskADIA` | `--pascal` | `DataChat` | brand text in instructions/READMEs **and** the `Local.AskADIA.*` DAX UDF namespace |
| `ASKADIA` | `--upper`  | `DATACHAT` | constants & env vars: `ASKADIA_ROOT`, `ASKADIA_CONFIG_JSON`, `SHARED_ASKADIA_CONFIG_PATH` |
| `askadia` | `--lower`  | `datachat` | package/dir name, op names (`setup_askadia_framework`), config keys, path strings |

`--upper` defaults to `--lower` uppercased; override it only if your brand needs
a non-trivial uppercasing.

## What the tool changes

* **Text content** — every `.py/.md/.json/.yml/.yaml/.csx/.tmdl/...` file in the
  package (skipping `__pycache__`, `.pytest_cache`, `.git`, and this tool + this
  doc).
* **Brand-named files** (`git mv` in a repo, plain move otherwise):
  * `udf/common/askadia_config.json` → `<lower>_config.json`
  * `deploy/setup_askadia_framework.py` → `setup_<lower>_framework.py`
* **Package directory** `askadia/` → `<lower>/` (skip with `--keep-dir-name`).
* **Goldens** — re-blessed via `emit_model.py --update-golden` (per model) and
  `emit_router.py --update-golden`, then validated with `test_roundtrip.py`
  (skip the whole step with `--no-rebless`).

## ⚠️ Two things the tool does NOT do (you must)

1. **Rename the runtime contract on the consumer side.** The
   `Local.<Pascal>.*` UDF entrypoints (`GenerateQuery`, `AnswerQuestion`,
   `Discover*`, `SearchValues`, `SearchHierarchy`, …) are called **by literal
   name** by whatever skill/agent consumes this model. If you rename them here,
   rename them in the consumer too — otherwise every query fails at runtime.

2. **Update host wiring outside the package.** The tool only rewrites files
   *inside* the package. A host that embeds this package typically also has:
   * an orchestrator import — `from setup_askadia_framework import setup_askadia_framework`
     (the file and symbol are now `setup_<lower>_framework`);
   * a `sys.path` insert pointing at `.../askadia/deploy`;
   * deploy config(s) that name the `setup_askadia_framework` /
     `generate_copilot_schema` operations and an `askadia` package key.

   Grep your host for `askadia`/`ASKADIA`/`AskADIA` after running the tool and
   fix those references by hand.

## CI guard

To stop an accidental rename from sneaking into the **upstream** repo, wire this
into CI:

```bash
python rename_namespace.py --check   # exits non-zero if the canonical brand drifted
```

## Flags

| Flag | Effect |
| ---- | ------ |
| `--pascal` / `--lower` | New brand forms (required unless `--check`). |
| `--upper` | Override the upper-case form (default: `--lower` uppercased). |
| `--root` | Package root to rewrite (default: this script's directory). |
| `--keep-dir-name` | Don't rename the package directory. |
| `--keep-filenames` | Don't rename brand-named files. |
| `--no-rebless` | Skip golden re-bless + roundtrip tests. |
| `--check` | CI guard: assert canonical brand intact, then exit. |
