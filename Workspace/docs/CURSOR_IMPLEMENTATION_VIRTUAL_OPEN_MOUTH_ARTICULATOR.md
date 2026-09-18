# Cursor IDE handoff — Virtual Open-Mouth Articulator (Composer 2.5)

**Branch:** `cursor-agent/dentoworkflow-debug-20260918`

**Spec:** [`DentoWorkflow_Virtual_Open_Mouth_Articulator_Agent_Prompt.md`](DentoWorkflow_Virtual_Open_Mouth_Articulator_Agent_Prompt.md)

## Manual Slicer test (Case Foundation panel)

1. Reload Module (Dev). Adopt reviewed segmentation.
2. Set target gap (default 40 mm). Click **Open mouth (AUTO)**. Do not place landmarks.
3. Inspect 3D motion and diagnostics (`hinge_source` AUTO path).
4. Click **Confirm and continue to Step 4A**.
5. Open **Fallback — manual landmarks** only if AUTO failed or you explicitly override.

## Verification

```bash
cd ~/dentobot/ros2_ws/src/DentoBot
PYTHONPATH=DENTOWorkflow/Resources/Python python3 -m pytest Testing/test_virtual_open_mouth_articulator.py -q
docker exec dentobot-slicerros2 sh -lc 'DENTOBOT_CASE_SOURCE=/workspace/data/Slicer_Saved/SampleStudy1/test1_post.mrb timeout 180s xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer --no-splash --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_auto_open_mouth_smoke.py'
```

Pass markers: pytest all green; `DENTOBOT_AUTO_OPEN_MOUTH_PASS` with `hinge_source` `PATIENT_CONDYLES_*` or `ARCH_INFERRED` and `landmarkSource` `AUTO`.
