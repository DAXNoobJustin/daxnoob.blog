# Activator (Data Activator / Reflex)

`ReflexEntities.json` is the **Data Activator** definition — the every-minute
clock that drives the whole system. It was exported from the live workspace and
cleaned (all GUIDs, cluster hosts, and item references are placeholders).

## What's in it

18 entities make up **three rules** — one per detector. Each rule is **two
`container`s** + a `kqlSource` + two `timeSeriesView`s + a `fabricItemAction`
(2 + 1 + 2 + 1 = 6 entities × 3 rules = 18):

| Part | Role |
|------|------|
| `kqlSource-v1` | Runs one detector's KQL **every 60 seconds** (`runSettings.executionIntervalInSeconds: 60`) against the Monitoring Eventhouse. |
| `timeSeriesView-v1` | Wraps the query result as the event stream the rule watches. |
| `fabricItemAction-v1` | On a triggering row, **starts the alert-handler pipeline** (`pipeline/DataActivatorAlertHandler.json`). The detector's output columns are mapped onto the pipeline parameters in the Activator UI on import — the export captures the action, not the field→parameter binding. |
| `container-v1` | Groups the rule. |

So: **detector fires → Activator picks it up within a minute → runs the
handler pipeline → cooldown → incident / Teams / refresh.**

## One change from the production export

In production the **OneLake** rule reads the Analysis Services engine trace from
an internal source not reachable
by customers, so this copy **repoints the OneLake rule onto the Monitoring
Eventhouse** and swaps its embedded query for the portable
[`kql/OneLakeSecurityError.kql`](../kql/OneLakeSecurityError.kql) (the
`permissions defined in OneLake` signal in `SemanticModelLogs`). All three rules
now read the same Eventhouse — see the README's "Portable detection vs. the
internal engine trace".

## Using it

This is a **reference**, not a drop-in. The `eventhouseItem`, `fabricItem`
(pipeline), and `querySet` references are placeholder GUIDs. To stand it up:
import (or recreate) it as an Activator/Reflex item, then rewire each rule's
KQL source to your Monitoring Eventhouse and its action to your imported
`DataActivatorAlertHandler` pipeline. The embedded KQL in each `kqlSource` is the
authoritative copy of the detector logic — identical to the files in `../kql/`.
