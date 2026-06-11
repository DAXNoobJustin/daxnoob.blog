# Custom Spark libraries

Binary Spark libraries (JARs and built wheels) are **not committed** to this starter --
they are large, redownloadable build artifacts. Before deploying this environment, add the
libraries this workspace expects to this folder:

- `deequ-<version>-spark-<version>.jar` -- PyDeequ backend for data-quality checks
  (from Maven Central); required by `helixutils.helix_check`.
- `helixutils-<version>-py3-none-any.whl` -- build from `/helixutils` with `uv build`
  and copy the wheel here (see `helixutils/scripts/update_helixutils.py`).