"""Prepared Slicer-only frame regression; never launches/connects ROS.

Requires an explicit runtime-free .dentocase fixture with >=2 VALID branches,
including a lower branch, and a new run-local output directory. It replaces the
isolated test scene. Full MoveIt all-object fidelity is a separate L6 campaign.
"""
from pathlib import Path
import json
import sys

import numpy as np

import step6_frame_audit as audit
import step6_frame_sync_export as export
import step6_scene_mesh_compare as compare


def source_to_base_rows(logic, parameter):
    """Compare production outgoing proxy transform with the world-accessor route."""
    rows = []
    inverse = np.linalg.inv(export.matrix_world(parameter.robotBaseTransform))
    for field in ('finalPrintableTemplateModel', 'targetDockingAssemblyModel', 'patientContactShellModel'):
        model = getattr(parameter,field,None)
        if model is None:
            raise ValueError(f'Fixture is missing {field}.')
        world = audit.model_world_polydata(model)
        vertices, triangles = audit.polydata_mesh(world)
        expected = export.apply_matrix(inverse,vertices)
        proxy = logic._polydataWorldToRobotBase(world,parameter.robotBaseTransform)
        outgoing, outgoing_triangles = audit.polydata_mesh(proxy)
        result = compare._object_comparison(expected,triangles,outgoing,outgoing_triangles)
        passed = (result['sampled_hausdorff_mm'] <= .05
                  and result['vertex_count']['match'] and result['triangle_count']['match'])
        rows.append({'source':field,'status':'PASS' if passed else 'FAIL',**result})
    return rows


def run_known_answers(case_path, out_dir, logic_factory):
    """Load isolated approved fixture, apply known edits, save/reopen, retain results."""
    import slicer
    import vtk
    from DENTOCaseBundle import extract_scene_mrb
    from DENTOStep6State import parse_trajectory_registry

    destination=Path(out_dir); destination.mkdir(parents=True,exist_ok=False)
    scene_path,inspection=extract_scene_mrb(case_path,destination/'fixture')
    if not slicer.util.loadScene(str(scene_path), {'clear':True}):
        raise ValueError('Could not load the explicitly supplied frame-sync fixture.')
    logic=logic_factory(); parameter=logic.getParameterNode()
    logic.hydrateDentoCaseStateAfterLoad(parameter,str(inspection.manifest['schemaVersion']))
    registry=logic.syncDentoCaseTrajectoryRegistry(parameter)
    valid=[bid for bid in registry['prepared_branches']
           if logic.evaluatePreparedBranchEligibility(parameter,bid,registry=registry).get('eligible')]
    if len(valid)<2:
        raise ValueError('Frame-sync fixture must contain at least two VALID PreparedBranches.')
    # A lower branch makes opening invariance a meaningful assertion.
    lower=[]
    for bid in valid:
        logic.activateDentoCasePreparedBranch(parameter,bid)
        if logic.nodeJawOwner(parameter,parameter.finalPrintableTemplateModel)=='MovingLower': lower.append(bid)
    if not lower: raise ValueError('Frame-sync fixture requires a lower-jaw branch.')
    logic.activateDentoCasePreparedBranch(parameter,lower[0])
    if logic.isRos2MotionControlActive(parameter.robotBaseTransform):
        raise ValueError('Known-transform fixture must be offline, without ROS motion control.')
    trajectories=logic.getSelectedTemplateGuideTrajectories()
    canonical=logic.canonicalTrajectoryGeometry(trajectories)
    original_gap=float(parameter.step6CaseJawTargetGapMm)
    base=parameter.robotBaseTransform
    original_base=export.matrix_world(base)
    results=[]

    def capture(label):
        rows=source_to_base_rows(logic,parameter)
        results.append({'label':label,'rows':rows,'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL'})
        (destination/'known-answers.json').write_text(json.dumps(results,indent=2))
        if results[-1]['status']!='PASS':raise AssertionError(f'Frame transform mismatch at {label}.')

    def set_base(matrix):
        if base.GetParentTransformNode() is not None:
            raise ValueError('Fixture Base must be an unparented locked-world transform.')
        m=vtk.vtkMatrix4x4();m.DeepCopy(np.asarray(matrix).reshape(-1).tolist())
        base.SetMatrixTransformToParent(m)

    capture('baseline')
    parameter.step6CaseJawTargetGapMm=original_gap+4.0
    logic.createOrUpdateStep6CaseJawOpening(parameter)
    if logic.canonicalTrajectoryGeometry(trajectories)!=canonical:
        raise AssertionError('Jaw opening changed canonical trajectory provenance.')
    capture('opening_plus_4_mm')
    parameter.step6CaseJawTargetGapMm=original_gap
    logic.createOrUpdateStep6CaseJawOpening(parameter)
    offset=original_base.copy();offset[:3,3]+=10.0*original_base[:3,0]
    set_base(offset);capture('base_plus_10_mm_u')
    angle=np.deg2rad(5.0);yaw=np.eye(4)
    yaw[:2,:2]=[[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]]
    set_base(offset@yaw);capture('base_yaw_plus_5_deg')
    set_base(original_base)
    other=next(bid for bid in valid if bid!=lower[0])
    logic.activateDentoCasePreparedBranch(parameter,other);capture('branch_switch')
    logic.prepareDentoCaseSchema3ForSave(parameter)
    saved=destination/'known-answers.mrb'
    if not slicer.util.saveScene(str(saved)):raise AssertionError('Fixture save failed.')
    if not slicer.util.loadScene(str(saved),{'clear':True}):raise AssertionError('Fixture reopen failed.')
    logic=logic_factory();parameter=logic.getParameterNode()
    logic.hydrateDentoCaseStateAfterLoad(parameter,str(inspection.manifest['schemaVersion']))
    selected=parse_trajectory_registry(parameter.step6TrajectoryRegistryJson)['selected_branch_id']
    if selected!=other:raise AssertionError('Selected branch changed across save/reopen.')
    capture('save_reopen')
    return results
