# Siftelo quick start (synthetic demonstration)

This walk-through uses two synthetic repositories that `examples/build_demo.py` creates. It touches no real
project and needs no network access. It takes about a minute.

Run it from the source tree (or the source distribution), in PowerShell. Install first if you want the
`siftelo` command; otherwise use `python -m siftelo` with `PYTHONPATH` set as shown.

## 1. Build the correct demonstration

Choose a new folder that does not exist yet. The builder refuses an existing folder and writes nothing outside
the one you choose.

```powershell
python examples\build_demo.py C:\siftelo-demo
```

It prints the paths of two new Git repositories, `interrupted-work` and `axe-core-synthetic`, each with a
`handoff.md` and a `manifest.json`. Its own exit code is 0 when the build finishes.

## 2. Run the preflight on the correct build

```powershell
$env:PYTHONPATH = "src"
python -m siftelo --project-root C:\siftelo-demo\interrupted-work --handoff handoff.md --manifest manifest.json
python -m siftelo --project-root C:\siftelo-demo\axe-core-synthetic --handoff handoff.md --manifest manifest.json
```

Each run prints a Markdown report to the screen and exits with code **3** (`review_required`). The handoffs
list pending approvals and unverified claims, which is what the demonstration is meant to show.

Exit 3 is not a pass. It means "a person should review these items". It is not verified readiness.

To keep a copy of a report, redirect stdout:

```powershell
python -m siftelo --project-root C:\siftelo-demo\axe-core-synthetic --handoff handoff.md --manifest manifest.json --format json > report.json
```

## 3. Build the stale variant and see a contradiction

The stale build moves HEAD after recording it and edits one evidence file. Build it into another new folder:

```powershell
python examples\build_demo.py C:\siftelo-demo-stale --stale
python -m siftelo --project-root C:\siftelo-demo-stale\axe-core-synthetic --handoff handoff.md --manifest manifest.json
python -m siftelo --project-root C:\siftelo-demo-stale\interrupted-work --handoff handoff.md --manifest manifest.json
```

Both runs exit with code **1** (`contradiction_found`). Each report marks two things as `stale`: the HEAD
recorded in the handoff and manifest (the repository has moved on), and the SHA-256 of one evidence file (its
content changed). Each stale item names the value it expected and the value it found.

## 4. Read the report

Look for four things:

1. The `Readiness` section: `Verified readiness: no` and `Authorises actions: no`. These are always the values.
2. The `Findings`: each has a status (see `README.md`, "Statuses").
3. The exit code: the table in `README.md` says what each code means.
4. Siftelo writes nothing. The report is printed to the screen only, and the demonstration files are unchanged.

## 5. Clean up

Delete the demonstration folders when you have finished:

```powershell
Remove-Item -Recurse -Force C:\siftelo-demo, C:\siftelo-demo-stale
```

Check the path before you run it. The command deletes everything inside the folders you name.

## Expected results at a glance

| run | exit code |
|---|---|
| correct build, `interrupted-work` | 3 |
| correct build, `axe-core-synthetic` | 3 |
| stale build, `axe-core-synthetic` | 1 |
| stale build, `interrupted-work` | 1 |

The builder itself exits 0 for both variants.
