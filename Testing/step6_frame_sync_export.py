"""Slicer-side read-only source export for independent all-object frame checks.

Call export_scene(namespace, NEW_DIRECTORY) in an approved Slicer session, then
run moveit_scene_dump.py in the same unchanged scene and analyse_scene offline.
Artifacts use base_link millimetres; MoveIt's dump remains metres. No publish,
scene sync, Base/Home acceptance or motion occurs here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

import step6_frame_audit as audit_tools
from dentobot_workflow.frame_sync import model_world_polydata, segment_world_polydata
from dentobot_workflow.jaw_frame import rigid_inverse


def matrix_world(node):
    import vtk
    if node is None:
        raise ValueError("A current transform node is required.")
    matrix = vtk.vtkMatrix4x4()
    node.GetMatrixTransformToWorld(matrix)
    result = np.array([[matrix.GetElement(i,j) for j in range(4)] for i in range(4)])
    if not np.isfinite(result).all():
        raise ValueError("World transform contains nonfinite values.")
    return result


def apply_matrix(matrix, vertices):
    points = np.asarray(vertices, dtype=float)
    return (np.asarray(matrix) @ np.c_[points, np.ones(len(points))].T).T[:, :3]


def source_world_mesh(namespace, record):
    """Resolve audit source identity independently of the outgoing collision copy."""
    logic, node = namespace['logic'], namespace['parameter_node']
    scene = namespace.get('scene')
    if scene is None:
        import slicer
        scene = slicer.mrmlScene
    source = str(record.get('source_id') or '')
    if source.startswith('vtkMRMLModelNode'):
        poly = model_world_polydata(scene.GetNodeByID(source))
    elif ':anatomy:' in source or ':target:' in source:
        segmentation_id, _, segment_id = source.split(':', 2)
        segmentation = scene.GetNodeByID(segmentation_id)
        if 'reviewed-session-proxy' in str(record.get('classification') or ''):
            review = logic.step6AnatomyReviewState(node)
            if not review.get('effectiveActive') or str(review.get('sourceSegmentId')) != segment_id:
                raise ValueError('The audited anatomy proxy is no longer current.')
            segmentation = review.get('proxyNode')
            segment_id = str(review.get('proxySegmentId') or segment_id)
        poly = segment_world_polydata(segmentation, segment_id)
        count = int(record.get('jaw_transform_application_count') or 0)
        if count not in (0, 1):
            raise ValueError('Audit expects an invalid number of jaw-opening applications.')
        if count:
            # Source segmentation is closed/head-fixed; apply opening once. Already
            # jaw-parented models above use only the full world accessor.
            poly = logic._step6CaseJawPolydataWorld(node, poly)
    elif ':mouth-barrier:' in source:
        name = source.split(':mouth-barrier:',1)[1]
        barrier = logic.step6MouthBarrier(node)
        part = next((p for p in (barrier.parts if barrier else ()) if p.name == name), None)
        if part is None:
            raise ValueError(f'Current mouth barrier part {name} is missing.')
        return np.asarray(part.points_mm,float), np.asarray(part.triangles,int)
    else:
        raise ValueError(f'Unsupported independent scene source {source!r}.')
    return audit_tools.polydata_mesh(poly)


def export_scene(namespace, out_dir):
    """Export every audited source, rejecting unmapped/empty/incoherent evidence."""
    logic, node = namespace['logic'], namespace['parameter_node']
    audit = logic.collisionSceneAuditRecord(node)
    if audit is None or not audit.object_records:
        raise ValueError('A current collision scene audit with object mappings is required.')
    base = matrix_world(node.robotBaseTransform)
    world_to_base = rigid_inverse(base)
    records = tuple(dict(record) for record in audit.object_records)
    ids = [str(r.get('outgoing_collision_object_id') or '') for r in records]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError('Scene audit object IDs are missing or duplicated.')
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=False)  # Never overwrite a prior capture.
    manifest = {'schema_version':'1.0', 'coordinate_frame':'base_link', 'units':'mm',
                'base_world_mm':base.tolist(), 'objects':[], 'status':'PASS'}
    for index, record in enumerate(records):
        item = {'id':ids[index], 'source_id':str(record.get('source_id') or ''),
                'jaw_transform_application_count':record.get('jaw_transform_application_count',0)}
        try:
            vertices, triangles = source_world_mesh(namespace,record)
            vertices = apply_matrix(world_to_base, vertices)
            if len(vertices) == 0 or len(triangles) == 0 or not np.isfinite(vertices).all():
                raise ValueError('Source mesh is empty or nonfinite.')
            filename = f'object-{index:03d}.npz'
            np.savez_compressed(destination/filename, vertices=vertices, triangles=triangles)
            item.update(file=filename, sha256=hashlib.sha256((destination/filename).read_bytes()).hexdigest(),
                        vertices=len(vertices), triangles=len(triangles), status='PASS')
        except Exception as exc:
            item.update(status='FAIL',error=str(exc))
            manifest['status']='FAIL'
        manifest['objects'].append(item)
    if not np.array_equal(matrix_world(node.robotBaseTransform),base):
        manifest.update(status='FAIL',error='Base changed during source export.')
    current = logic.collisionSceneAuditRecord(node)
    if current is None or tuple(dict(r) for r in current.object_records) != records:
        manifest.update(status='FAIL',error='Collision audit identity changed during source export.')
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest
