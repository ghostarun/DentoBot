"""Read-only same-state collision agreement, not motion or clearance acceptance.

namespace requires logic, parameter_node and the current acm / scene_snapshot
from moveit_scene_dump. Bodies map exact MoveIt IDs to vertices_world_mm,
triangles and role. source_bodies resolves those IDs through the L1 accessor.
The existing exact triangle helper reports unsigned surface separation, not
penetration depth or enclosed-volume overlap. Keep these evidence boundaries.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np

import step6_frame_audit as audit
from step6_frame_sync_export import apply_matrix, matrix_world, source_world_mesh
from moveit_scene_dump import acm_lookup
from dentobot_workflow.feasibility_advisor import pairs_from_text

ROBOT_LINKS = ('pneumatic_spindle-Copy', 'burr', 'link-5')
_MESH_CACHE = {}


def source_bodies(namespace):
    """Every audit object, independent current world geometry and exact identity."""
    record = namespace['logic'].collisionSceneAuditRecord(namespace['parameter_node'])
    if record is None or not record.object_records:
        raise ValueError('Current collision audit mappings are required.')
    bodies = {}
    for item in record.object_records:
        identifier = str(item.get('outgoing_collision_object_id') or '')
        if not identifier or identifier in bodies:
            raise ValueError('Missing or duplicate collision object ID.')
        vertices, triangles = source_world_mesh(namespace, item)
        bodies[identifier] = dict(vertices_world_mm=vertices, triangles=triangles,
                                  role=item.get('source_role'), source_id=item.get('source_id'))
    return bodies


def classify_pair(exact, *, valid, named, authoritative, allowed, intended):
    """Agreement classes; PASS can mean a consistently detected collision."""
    if not authoritative:
        return 'validity_unavailable', 'FAIL'
    if allowed:
        return ('acm_contact_reported', 'FAIL') if named else ('allowed_by_acm', 'PASS')
    if intended:
        return 'intended_terminal_contact', 'PASS'
    if named:
        return ('consistent_collision', 'PASS') if exact['intersecting'] and not valid else ('contact_not_reproduced', 'FAIL')
    if exact['intersecting']:
        return ('checker_misses_intersection' if valid else 'contact_not_reported'), 'FAIL'
    return 'consistent_clear', 'PASS'


def _mesh_arrays(vertices, triangles):
    vertices = np.asarray(vertices, float)
    raw = np.asarray(triangles)
    if (vertices.ndim != 2 or vertices.shape[1:] != (3,) or not len(vertices)
            or not np.isfinite(vertices).all() or raw.ndim != 2 or raw.shape[1:] != (3,)
            or not len(raw) or not np.issubdtype(raw.dtype, np.integer)
            or raw.min() < 0 or raw.max() >= len(vertices)):
        raise ValueError('Invalid or empty triangle mesh.')
    if np.any(np.linalg.norm(np.cross(vertices[raw[:,1]]-vertices[raw[:,0]],
                                     vertices[raw[:,2]]-vertices[raw[:,0]]),axis=1) <= 1e-15):
        raise ValueError('Degenerate collision triangle.')
    return vertices, raw.astype(int)


def _robot_meshes(namespace, joints):
    urdf, package = namespace['logic'].robotDescriptionPaths()
    text = Path(urdf).read_text(encoding='utf-8')
    digest = hashlib.sha256(text.encode()).hexdigest()
    fk = audit.UrdfFk(text)
    base = matrix_world(namespace['parameter_node'].robotBaseTransform)
    meshes = {}
    for link in ROBOT_LINKS:
        if link not in fk.links or len(fk.links[link].findall('collision')) != 1:
            raise ValueError(f'{link} must have exactly one URDF collision mesh.')
        origin, filename, scale = fk.collision(link)
        prefix = 'package://dentobot_description/'
        if not filename.startswith(prefix):
            raise ValueError(f'Unsupported collision mesh URI: {filename}')
        path = (Path(package) / filename[len(prefix):]).resolve()
        if not path.is_relative_to(Path(package).resolve()):
            raise ValueError('Collision mesh path escapes package.')
        mesh_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        key = (digest, link, str(path), mesh_digest)
        if key not in _MESH_CACHE:
            vertices, faces = audit.read_binary_stl_mesh(path)
            _MESH_CACHE[key] = _mesh_arrays(vertices * np.asarray(scale) * 1000.0, faces)
        vertices, faces = _MESH_CACHE[key]
        pose = audit.to_ras_mm(base, fk.link_pose_m(link,joints) @ origin)
        meshes[link] = (apply_matrix(pose,vertices),faces)
    return meshes, digest


def collision_agreement(namespace, joints, bodies):
    """Compare three posed robot links against bodies; no launch, apply or motion.

    Intended contact requires explicit terminal phase AND selected-target role;
    it is labelled only, never a new policy permission. Snapshot padding/scale
    must confirm the handoff's zero/one premise for each audited link.
    """
    result = dict(status='FAIL', joints_si=dict(joints), rows=[], issues=[])
    try:
        snapshot, acm = namespace['scene_snapshot'], namespace['acm']
        base_before = matrix_world(namespace['parameter_node'].robotBaseTransform)
        result['base_world_mm'] = base_before.tolist()
        result['scene_captured_utc'] = snapshot.get('captured_utc')
        for link in ROBOT_LINKS:
            if (snapshot['link_padding'].get(link) != 0.0
                    or snapshot['link_scale'].get(link) != 1.0):
                raise ValueError(f'Zero padding / unit scale not confirmed for {link}.')
        robot, digest = _robot_meshes(namespace, joints)
        result['urdf_sha256'] = digest
        native_digest = (snapshot.get('robot_description') or {}).get('sha256')
        if native_digest != digest:
            raise ValueError('Dump robot_description identity does not match independent URDF.')
        bridge = namespace.get('bridge')
        if bridge is None:
            import DENTOROS2Bridge as bridge
        valid, reason, authoritative = bridge.check_moveit_static_joint_state(joints)
        pairs = [tuple(p) for p in pairs_from_text(reason)]
        result.update(moveit_valid=bool(valid), moveit_authoritative=bool(authoritative),
                      moveit_reason=str(reason), moveit_pairs=[list(p) for p in pairs])
        if authoritative is not True or valid not in (True, False):
            result['issues'].append('Authoritative static validity unavailable.')
        if re.search(r'\(and [1-9]\d* more\)',str(reason)):
            result['issues'].append('Native contact list is truncated; cannot establish complete agreement.')
        if valid is False and not pairs:
            result['issues'].append('Invalid state has no parseable contact pairs; cannot establish agreement.')
        if not bodies:
            raise ValueError('No bodies supplied for collision agreement.')
        examined = set()
        for identifier, body in bodies.items():
            if not str(identifier):
                raise ValueError('Empty collision object ID.')
            bv, bt = _mesh_arrays(body['vertices_world_mm'],body['triangles'])
            for link, (rv, rt) in robot.items():
                pair = tuple(sorted((link,str(identifier))))
                examined.add(pair)
                exact = audit.exact_mesh_separation(rv,rt,bv,bt,search_mm=3.0)
                acm_row = acm_lookup(acm,link,str(identifier))
                intended = (link == 'burr' and body.get('role') == 'selected-target-tooth'
                            and namespace.get('phase') == 'drilling_end')
                classification, status = classify_pair(exact,valid=valid,named=pair in pairs,
                    authoritative=authoritative is True,allowed=acm_row['allowed'],intended=intended)
                result['rows'].append(dict(link=link,body=str(identifier),role=body.get('role'),
                    source_id=body.get('source_id'),exact=exact,acm=acm_row,
                    moveit_named=pair in pairs,intended_terminal_contact=intended,
                    classification=classification,status=status))
        result['unexamined_contacts'] = [list(p) for p in pairs if p not in examined]
        if result['unexamined_contacts']:
            result['issues'].append('Native contacts outside audited link/body set remain unexamined.')
        if not np.array_equal(matrix_world(namespace['parameter_node'].robotBaseTransform),base_before):
            result['issues'].append('Base changed during collision agreement capture.')
        if result['rows'] and not result['issues'] and all(r['status']=='PASS' for r in result['rows']):
            result['status']='PASS'
    except Exception as exc:
        result['issues'].append(str(exc))
    return result
