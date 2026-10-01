"""Reserved offline native restore timing; no ROS initialization or motion."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
import slicer

root = Path(os.environ['DENTOCASE_BENCH_ROOT'])
sys.path.insert(0, str(root / 'DENTOWorkflow/Resources/Python'))

def run():
    from DENTOCaseBundle import sha256_file
    source = Path(os.environ['DENTOCASE_BENCH_SOURCE'])
    slicer.util.selectModule('DENTOWorkflow')
    widget = slicer.util.getModuleWidget('DENTOWorkflow')
    slicer.mrmlScene.Clear(0)
    # Warmup establishes the same saved prior scene for each measured load.
    widget._openCaseBundle(source)
    samples = []
    measured = {}
    for obj, name in ((widget.logic, 'caseFoundationSourceVolumeFingerprint'),
                      (widget.logic, 'caseFoundationSourceSegmentationFingerprint'),
                      (widget.logic, 'rebuildCaseFoundationDisplayVolumes'),
                      (widget.logic, 'validateLoadedCaseBundleWorkflow'),
                      (widget.logic, 'hydrateDentoCaseStateAfterLoad'),
                      (widget, '_updateFromParameterNodeOnce')):
        original = getattr(obj, name, None)
        if original is None:
            continue
        def wrapped(*args, _original=original, _name=name, **kwargs):
            started = time.perf_counter()
            try:
                return _original(*args, **kwargs)
            finally:
                record = measured.setdefault(_name, {'calls': 0, 'seconds': 0})
                record['calls'] += 1
                record['seconds'] += time.perf_counter() - started
        setattr(obj, name, wrapped)
    method_samples = []
    for index in range(3):
        measured.clear()
        print('DENTOCASE_BENCH_SAMPLE', index, flush=True)
        start = time.perf_counter()
        widget._openCaseBundle(source)
        samples.append(time.perf_counter() - start)
        method_samples.append({name: dict(value) for name, value in measured.items()})
    result = {'source': str(source), 'sha256': sha256_file(source),
              'bytes': source.stat().st_size, 'root': str(root),
              'samples_seconds': samples, 'median_seconds': sorted(samples)[1],
              'methods': method_samples, 'robot_profile_sha256': widget.logic.caseBundleRobotProfile()['identitySha256'],
              'ros_initialized': False}
    Path(os.environ['DENTOCASE_BENCH_RESULT']).write_text(json.dumps(result, indent=2)+'\n')
    print('DENTOCASE_BENCH_PASS', json.dumps(result), flush=True)

try:
    run()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
else:
    slicer.util.exit(0)
