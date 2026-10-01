# DCP-09..10 — Clean library and scan/load performance

## Approved contract

Existing integration checkout/branch; operator loading confirmed, UI rejected, manual save/reopen untried. Exactly two GPT-6 Luna Max workers own catalog/inspection/tests and browser/tests. Coordinator owns shared package preparation/activation/projection, actual diff review, runtime and controlled records. No new dependencies/formats/robot policy, main promotion or5.12. Preserve concurrent performance progress/watchdog/launcher edits.

Fixed design: <=100 compact case rows/page; search case labels and known teeth; separate package/workflow status text and color; latest dated revision, locations, selected tooth/preparation and checkpoint detail; collapsed technical evidence; native light/dark styling. Metadata preview never authorizes partial projection or activation. Scans explicit and incremental; errors/missing visible; cancelled traversal cannot mark unseen missing. Clear removes only catalog entries and remembered folders after cooperative cancellation/writer completion and stale-generation invalidation.

Full load uses owned short-lived validated extracted MRB, checks source mutation, retains recovery/rollback and exact lineage. Partial retains disposable offline projector/ownership/fresh reopen/independent identity/history; source preparation is reused where safe. No MRML worker-thread access. Final operator UI and manual save→scan→partial load→continuation→Save As→reopen verdict remains required in backlog.

## Baseline

Source HEAD baeee90/source checkpoint50ce208. Preserved source in data/test-artifacts/dentocase-browser-20261001/baseline-source. Unchanged de-identified r29 source134.79MiB SHA2562b80f595f39d9e79d547bbfce1c7d61b0a1feef393175ab92f442cd9210b7c93. Prior host profiling firstscan1.6532s; unchangedscan0.1963s/1fullvalidation;50case eager rows2.986s; fullpreflight0.3382s/3fullvalidations. Native corrected threewarmloads27.5351,23.7723,23.5289s; median23.7723s. Package preflight ~0.66s; restore/display/events dominate. First baseline snapshot lacked robot resources; corrected using unchanged tracked resources, no safety relaxation. Native logs/result at data/test-artifacts/dentocase-browser-20261001/.

## Acceptance evidence

Implementation and results will be appended after source freeze. Host tests establish software contracts, native offline rounds establish restore/lifecycle; neither substitutes for operator UX/continuation verdict. Targets: cached1000 firstpage500ms/search150ms/details100ms; unchanged scan0fullvalidation/0geometry;50summary>=10x faster; fullprep1sourcevalidation; nativefullmedian20% reduction measured separately.


## Final reviewed delivery — 1 October

Affected matrix command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider Testing/test_dentocase_boundaries.py Testing/test_dentocase_browser.py Testing/test_dentocase_catalog.py Testing/test_dentocase_lineage.py Testing/test_dentocase_projection.py Testing/test_dentocase_schema.py Testing/test_dentocase_inventory.py Testing/test_case_bundle.py Testing/test_dentocase_restore_metrics.py` —94PASS0.42s. Scoped `git diff --check` exit0. No unrelated planner/robot campaign.

Final host command: `PYTHONDONTWRITEBYTECODE=1 python3 Testing/benchmark_dentocase_library.py --source /home/light-tarun/dentobot/data/Slicer_Saved/SampleStudy1/SEPT24/oct01_fdi11_offline_home_r29.dentocase --output /home/light-tarun/dentobot/data/test-artifacts/dentocase-browser-20261001/host-portable-sql` —exit0/all6targetsTrue. Fixture manifests/source hashes and package-byte counters in host-benchmark.json.1000synthetic metadata packages; no full inventory/geometry in browsing.

| Phase | Final host seconds | Full validations | Scene bytes |
|---|---:|---:|---:|
| r29metadata |0.002325|0|0|
|1000newscan |2.551599|0|0|
|1000unchangedscan |0.041284|0|0|
|First100of1000 |0.003336|0|0|
|Search |0.002178|0|0|
|Selecteddetails |0.000079|0|0|
|50summary |0.002797|0|0|
|Fullprep |0.096149|1|141307823|

Full native unchanged r29: baseline equivalent samples22.289476,22.459161,24.356517s; final17.610422,17.541778,18.633075s. Median22.459161→17.610422s (21.589% reduction). PackageSHA2b80f595… and installedrobotprofileSHAcac087c6… match; Ubuntu/CPU/memory/source identity in summary.json. Phase logs and instrumented methods are in native-before-equivalent.log/native-after-final.log/json. Loader/full scene transaction measured; this is not whole-workstation or Windows/WSL performance acceptance.

NativeQt/persistence fixed check: Testing/run_dentocase_integration_smoke.py via reserved existing5.10Slicer, privateXvfb/noROS, sourcecheckout modules. ResultPASS, DENTOCASE_INTEGRATION_PASS, exit0, pgrep teardownclear. Actual screenshots library-synthetic.png (1100×700), library-small.png (900×600). Sourcegeometry/history runtimeauthority remainUnverified. Synthetic partial sourceverification0.041–0.599s; childstartup~3.67–3.83s; projection/release total4.605–5.146s; measured5Bactivation0.904s. Childmarkers separate preparation/restore/projection/save/freshreopen. These are synthetic partial timings; no representative135MiB partialtiming claim.

Nativefirstcheck failed browserpopulation; narrow copiedcatalog probe showed bundledSQLite window-query incompatibility. Replaced ROW_NUMBER query, catalog26PASS, portablebenchmarktargetsPASS, then fixednativepersistencePASS. Original failures retained. Standalone guessedPythonSlicerpath was absent (exit127), no GUI launched; used verified Slicer launcher. One automaticpermissionreview timedout before retry launch; permitted single retry with establishedDockercommand succeeded. No unsafeaction inferred.

Final tiny title/error-detail/checked-row/filenamefallback presentation changes followed the nativepass; final94hostgate passed after them. Full runtime-acceptance file identity boundary is recorded honestly in summary.json. Manual redesignedUI/save→scan→partialload→continuation→SaveAs→reopen remains in the sole backlog.
