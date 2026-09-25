"""Narrow saved-case Slicer check for the FDI11 enclosed pulp candidate."""

import json
from pathlib import Path
import sys
import traceback

import numpy as np
import slicer

sys.path.insert(0, '/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python')
from DENTOCaseBundle import extract_scene_mrb  # noqa: E402


SOURCE = Path('/workspace/data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase')


def run():
    slicer.util.selectModule('DENTOWorkflow')
    slicer.util.mainWindow().resize(1400, 900)
    slicer.app.processEvents()
    widget = slicer.util.getModuleWidget('DENTOWorkflow')
    scene_path, _inspection = extract_scene_mrb(
        SOURCE, Path(slicer.app.temporaryPath) / 'fdi11-pulp-envelope'
    )
    assert slicer.util.loadScene(str(scene_path), {'clear': True})
    slicer.app.processEvents()
    logic = widget.logic
    segmentation = next(node for node in slicer.util.getNodesByClass('vtkMRMLSegmentationNode')
                        if node.GetSegmentation().GetSegmentIdBySegmentName('upper_right_central_incisor_fdi11'))
    tooth_id = segmentation.GetSegmentation().GetSegmentIdBySegmentName('upper_right_central_incisor_fdi11')
    tooth_label = int(segmentation.GetSegmentation().GetSegment(tooth_id).GetLabelValue())
    before = (slicer.util.arrayFromSegmentInternalBinaryLabelmap(segmentation, tooth_id) == tooth_label).copy()
    phases = []
    result = logic.prepareTargetPulpMask(
        segmentation, tooth_id, progress=lambda phase, *args, **kwargs: phases.append(phase)
    )
    assert result['status'] == 'created'
    assert 'Checking tooth surfaces' in phases and 'Committing reviewable pulp mask' in phases, phases
    candidate_id, count = result['pulpSegmentId'], result['voxelCount']
    after = slicer.util.arrayFromSegmentInternalBinaryLabelmap(segmentation, tooth_id) == tooth_label
    assert np.array_equal(before, after), 'source tooth/shared labelmap changed'
    candidate = slicer.util.arrayFromSegmentBinaryLabelmap(segmentation, candidate_id)
    assert count == 52 and np.count_nonzero(candidate) == 52, (count, np.count_nonzero(candidate))
    assert segmentation.GetAttribute('DENTOBOT.ReviewState') == 'Needs Correction'
    reference = logic.getSegmentationSourceVolume(segmentation)
    tooth_aligned = slicer.util.arrayFromSegmentBinaryLabelmap(segmentation, tooth_id, reference)
    candidate_aligned = slicer.util.arrayFromSegmentBinaryLabelmap(segmentation, candidate_id, reference)
    tooth_points = np.argwhere(tooth_aligned > 0)
    candidate_points = np.argwhere(candidate_aligned > 0)
    print('DENTOBOT_FDI11_GEOMETRY ' + json.dumps({
        'sourceShape': list(before.shape), 'referenceShape': list(tooth_aligned.shape),
        'toothBounds': [tooth_points.min(axis=0).tolist(), tooth_points.max(axis=0).tolist()],
        'candidateBounds': [candidate_points.min(axis=0).tolist(), candidate_points.max(axis=0).tolist()],
    }), flush=True)
    logic.setSegmentationReviewState(segmentation, 'Reviewed')
    association = logic.getTargetPulpAssociation(segmentation, tooth_id)
    assert association['pulpSegmentId'] == candidate_id
    assert association['validationState'] == 'VALID'
    assert association['associationConfidence'] == 'HIGH'
    print('DENTOBOT_FDI11_PULP_ENVELOPE_PASS ' + json.dumps({
        'candidateId': candidate_id, 'voxels': count, 'sourceUnchanged': True,
        'reviewStateBeforeSimulatedApproval': 'Needs Correction',
        'association': association['validationState'],
    }), flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
