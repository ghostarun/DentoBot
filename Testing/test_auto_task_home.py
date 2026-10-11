"""Known-answer geometry and draft-only Auto Task Home coordination (no ROS)."""
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

PY = Path(__file__).resolve().parents[1] / 'DENTOWorkflow/Resources/Python'
sys.path.insert(0, str(PY))
from dentobot_workflow import auto_task_home as module, advisor_home_proposal
from dentobot_workflow.auto_task_home import auto_task_home_geometry, pose_residual, propose_auto_task_home, incisor_biting_edge_midpoint


REAL_SOURCE_ADAPTER = module.incisor_biting_edge_source
REAL_BARRIER_SOURCE_ADAPTER = module.mouth_barrier_task_home_source


@dataclass
class Result:
    success: bool
    code: str
    message: str
    details: dict = field(default_factory=dict)
    payload: object = None


class Matrix:
    def __init__(self):
        self.rows = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]

    def SetElement(self, i, j, value):
        self.rows[i][j] = value


@pytest.fixture(autouse=True)
def source_adapter_for_proposal_fakes(monkeypatch):
    def source(facade, parameter):
        result = facade.defaultTaskSpaceRoi()
        if not result.success:
            raise ValueError(result.message)
        return result.payload
    monkeypatch.setattr(module, "incisor_biting_edge_source", source)
    monkeypatch.setattr(module, "mouth_barrier_task_home_source", source)


def facade():
    state = SimpleNamespace(identity='current', scene=True, ik=True, fk=True, fk_z=0.0,
                            axis=1.0, calls=[], after_fk=None, midpoint=(0., 0., 0.))
    parameter = SimpleNamespace(robotBaseTransform='base')
    from DENTORobotPlacement import joint_positions_si_from_display
    joints = joint_positions_si_from_display(0, 20, 0, 20, 0)
    def fk(q, *, base_transform):
        state.calls.append(('fk', q, base_transform))
        pose = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, state.axis, state.fk_z], [0, 0, 0, 1]]
        if state.after_fk:
            state.after_fk()
        return state.fk, 'FK', pose
    def goal(pose):
        state.calls.append(('goal', pose.rows))
        return Result(True, 'goal', 'goal')
    def solve(**kwargs):
        state.calls.append(('ik', kwargs))
        return state.ik, 'IK unavailable' if not state.ik else 'IK', joints if state.ik else {}, {
            'termination_reason': 'converged' if state.ik else 'collision_check_unavailable'}
    def static(q):
        state.calls.append(('static', q))
        return True, 'static clear', True
    f = SimpleNamespace(
        _require_context=lambda: parameter,
        _manual_jog_current_identity=lambda p, **kw: {'identity':state.identity},
        defaultTaskSpaceRoi=lambda: Result(True, 'roi', 'ROI', payload={
            'centerWorldRasMm':state.midpoint, 'openingRevision':1, 'gapLineNodeId':'line'}),
        _logic=SimpleNamespace(robotDescriptionPaths=lambda: [str(PY.parents[2] / 'dentobot_description/urdf/dentobot.urdf')], step6TrajectorySummary=lambda p: {
            'isValid':True, 'entryRas':(0,0,10), 'targetRas':(0,0,20)}),
        moveItSceneComparison=lambda: {'matches':state.scene},
        _bridge=SimpleNamespace(tool_pose_matrices_world_mm=lambda *a: [Matrix(), Matrix()],
                                compute_moveit_tcp_pose_world_ras_mm=fk,
                                ROS2_JOINT_SI_ORDER=tuple(joints),
                                solve_moveit_tcp_position_axis_goal=solve,
                                check_moveit_static_joint_state=static),
        setTcpGoal=goal, solveIk=solve,
        _manual_task_home_candidate_within_mechanical_limits=lambda q: state.calls.append(('limits', q)),
    )
    for flag in ('_manual_task_home_acceptance_in_progress', '_manual_task_home_acceptance_uncertain',
                 '_manual_task_home_reconciliation_in_progress', '_manual_jog_in_progress',
                 '_manual_jog_reconciliation_required', '_manual_base_acceptance_in_progress',
                 '_manual_base_acceptance_uncertain', '_manual_jog_uncertainty'):
        setattr(f, flag, False)
    return f, state


POLICY = SimpleNamespace(CARTESIAN_START_POSITION_TOLERANCE_MM=.25,
                         CARTESIAN_START_ORIENTATION_TOLERANCE_DEG=.5)


def test_midpoint_depth_and_direction_are_independent_for_upper_lower():
    # Current opened central biting edges at z=10 and z=-30 give z=-10.
    midpoint = (5, 2, -10)
    upper = auto_task_home_geometry(midpoint, (5, 12, -10), (5, 12, 0))
    lower = auto_task_home_geometry(midpoint, (5, 12, -10), (5, 12, -20), depth_mm=3)
    assert upper.position_world_ras_mm == midpoint
    assert upper.drill_axis_world_ras_unit == (0, 0, 1)
    assert lower.position_world_ras_mm == (5, 5, -10)
    assert lower.drill_axis_world_ras_unit == (0, 0, -1)
    assert auto_task_home_geometry(midpoint, (5,12,-10), (5,12,0), depth_mm=-3).position_world_ras_mm == (5,-1,-10)


@pytest.mark.parametrize('midpoint,entry,target,depth', [
    ((0,0), (0,0,1), (0,0,2), 0),
    ((float('nan'),0,0), (0,0,1), (0,0,2), 0),
    ((0,0,0), (0,0,1), (0,0,1), 0),
    ((0,0,0), (0,0,0), (0,0,1), 1),
    ((0,0,0), (0,0,1), (0,0,2), float('inf')),
])
def test_invalid_geometry_refuses(midpoint, entry, target, depth):
    with pytest.raises(ValueError):
        auto_task_home_geometry(midpoint, entry, target, depth_mm=depth)


def test_zero_depth_does_not_need_midpoint_to_entry_direction():
    assert auto_task_home_geometry((0,0,0), (0,0,0), (0,0,1)).position_world_ras_mm == (0,0,0)


def test_fk_checks_directed_axis_but_not_axial_roll():
    geometry = auto_task_home_geometry((0,0,0), (0,0,1), (0,0,2))
    assert pose_residual(geometry, [[0,-1,0,0],[1,0,0,0],[0,0,1,0]]) == (0,0)
    assert pose_residual(geometry, [[1,0,0,0],[0,1,0,0],[0,0,-1,0]]) == (0,180)


def test_proposal_calls_existing_ik_and_fk_and_returns_only_draft():
    f, state = facade()
    result = propose_auto_task_home(f, Result, POLICY)
    assert result.success
    assert result.details['draftOnly'] is True
    assert [c[0] for c in state.calls] == ['goal', 'ik', 'static', 'limits', 'fk']
    assert result.details['source']['gapLineNodeId'] == 'line'
    assert result.details['taskHomeReviewIdentity'] == {'identity': 'current'}
    assert result.details['trajectoryWorldRasMm'] == {'entry': (0., 0., 10.), 'target': (0., 0., 20.)}
    state.identity = 'later'
    assert result.details['taskHomeReviewIdentity'] == {'identity': 'current'}
    assert 'No motion' in result.message


@pytest.mark.parametrize('change', ['scene', 'ik', 'fk', 'residual', 'axis', 'identity', 'midpoint', 'scene_after'])
def test_guard_and_stale_results_never_return_a_stagable_candidate(change):
    f, state = facade()
    if change in ('scene','ik','fk'):
        setattr(state, change, False)
    elif change == 'residual':
        state.fk_z = .251
    elif change == 'axis':
        state.axis = -1
    else:
        name, value = {'identity':('identity','stale'), 'midpoint':('midpoint',(1,0,0)),
                       'scene_after':('scene',False)}[change]
        state.after_fk = lambda: setattr(state,name,value)
    result = propose_auto_task_home(f, Result, POLICY)
    assert not result.success
    assert result.payload is None
    if change == 'scene':
        assert state.calls == []


def test_source_failure_and_home_busy_precede_goal_mutation():
    for case in ('source','busy','identity'):
        f, state = facade()
        if case == 'source':
            f.defaultTaskSpaceRoi = lambda: Result(False,'missing','incisor line missing')
        elif case == 'busy':
            f._manual_task_home_acceptance_in_progress = True
        else:
            def blocked(*a, **kw):
                raise ValueError('reviewed Base stale')
            f._manual_jog_current_identity = blocked
        result = propose_auto_task_home(f, Result, POLICY)
        assert not result.success and not state.calls


def test_nonzero_depth_is_passed_to_goal_without_affecting_drill_axis():
    f, state = facade()
    state.fk_z = 2
    result = propose_auto_task_home(f, Result, POLICY, depth_mm=2)
    assert result.success
    assert state.calls[0][1][2][3] == 2
    assert result.details['drillAxisWorldRasUnit'] == (0,0,1)


def method(path, owner, name):
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name == owner)
    node = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name == name)
    scope = {"advisor_home_proposal": advisor_home_proposal}
    exec(compile(ast.Module(body=[node],type_ignores=[]), str(path),'exec'),scope)
    return scope[name]


@pytest.mark.parametrize('success,stage_success', [(True,True),(False,True),(True,False)])
def test_widget_only_stages_success_and_reports_inline(success, stage_success):
    callback = method(PY/'dentobot_workflow/widget_robot_manual.py', 'RobotManualWidgetMixin', '_onStep6AutoTaskHome')
    calls=[]
    label=SimpleNamespace(text='',setProperty=lambda *a: calls.append(('label',a)))
    panel=SimpleNamespace(taskHomeReviewStatusLabel=label,
        stageTcpIkSolution=lambda p: calls.append(('stage',p)) or stage_success,
        setManualJogDraftDisplayResult=lambda *a: calls.append(('display',a)),
        setManualJogStatus=lambda *a: calls.append(('status',a)))
    obj=SimpleNamespace(_robotSimulationPanel=panel,
        _robotWorkflowFacade=SimpleNamespace(proposeAutoTaskHome=lambda: Result(success,'draft','result',payload={'j1':1})))
    callback(obj)
    assert sum(c[0]=='stage' for c in calls) == int(success)
    assert calls[-1][1][0] == ('draft' if success and stage_success else 'blocked')


def test_action_is_owned_by_home_substep_and_wired_through_shell():
    panel=(PY/'DENTORobotSimulationPanel.py').read_text()
    shell=(PY/'dentobot_workflow/widget_robot_shell.py').read_text()
    assert '"auto_task_home": 2' in panel
    assert 'self._invoke("auto_task_home")' in panel
    assert '"auto_task_home": self._onStep6AutoTaskHome' in shell


def test_biting_edges_use_surface_extremes_and_opened_lower_not_centroids():
    # Distinct edge/centroid z values, opened lower at -20 rather than closed -2.
    clouds = {
        "11": [(-2,0,10),(-2,0,2)], "21": [(2,0,10),(2,0,2)],
        "31": [(-2,0,-30),(-2,0,-20)], "41": [(2,0,-30),(2,0,-20)],
    }
    result = incisor_biting_edge_midpoint(clouds)
    assert result["upperEdgeWorldRasMm"] == (0,0,2)
    assert result["lowerEdgeWorldRasMm"] == (0,0,-20)
    assert result["centerWorldRasMm"] == (0,0,-9)
    assert result["centerWorldRasMm"] != (0,0,-9.5)  # Mean tooth centroids.


@pytest.mark.parametrize("cloud", [[], [[0,0]], [[float('nan'),0,0]]])
def test_biting_edge_surface_validation(cloud):
    clouds = {fdi:[[0,0,1 if fdi in ("11","21") else -1]] for fdi in ("11","21","31","41")}
    clouds["11"] = cloud
    with pytest.raises(ValueError):
        incisor_biting_edge_midpoint(clouds)


def test_biting_edge_requires_all_four_central_incisors():
    with pytest.raises(KeyError):
        incisor_biting_edge_midpoint({"11":[[0,0,1]]})


def test_world_adapter_opens_only_lower_central_incisors_once():
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk
    import numpy as np
    calls = []
    def surface(segmentation, ids):
        fdi = next(iter(ids))
        calls.append(("surface", fdi))
        cloud = np.array([[0.,0.,10.],[0.,0.,2.]]) if fdi in ("11","21") else np.array([[0.,0.,-10.],[0.,0.,0.]])
        points = vtk.vtkPoints(); points.SetData(numpy_to_vtk(cloud))
        poly = vtk.vtkPolyData(); poly.SetPoints(points)
        return poly
    def opening(parameter, poly):
        calls.append(("opening",))
        transform = vtk.vtkTransform(); transform.Translate(0,0,-20)
        f = vtk.vtkTransformPolyDataFilter(); f.SetInputData(poly); f.SetTransform(transform); f.Update()
        result = vtk.vtkPolyData(); result.DeepCopy(f.GetOutput())
        return result
    parameter = SimpleNamespace(teethSegmentation="reviewed")
    f = SimpleNamespace(defaultTaskSpaceRoi=lambda: Result(True,"roi","ROI",payload={
        "centerWorldRasMm":(999,999,999), "openingRevision":4, "gapLineNodeId":"gap"}),
        _logic=SimpleNamespace(_step6ToothSegmentIdsByFdi=lambda s:{fdi:fdi for fdi in ("11","21","31","41")},
            _segmentationSegmentsSurfaceWorld=surface, _step6CaseJawPolydataWorld=opening))
    result = REAL_SOURCE_ADAPTER(f, parameter)
    assert result["centerWorldRasMm"] == (0,0,-9)
    assert result["openingRevision"] == 4
    assert calls == [("surface","11"),("surface","21"),("surface","31"),("opening",),
                     ("surface","41"),("opening",)]


@pytest.mark.parametrize("substep,connected,ik,expected", [(2,True,True,True), (2,False,True,False),
    (2,True,False,False), (3,True,True,False)])
def test_auto_button_capability_gate_has_a_reason(substep, connected, ik, expected):
    update = method(PY/"DENTORobotSimulationPanel.py", "DENTORobotSimulationPanel", "_updateTcpCartesianControlState")
    control = lambda: SimpleNamespace(enabled=False,toolTip="")
    p = SimpleNamespace(_activeSubstep=substep, _taskHomeSetupMode="connected" if connected else "offline",
        _tcpIkAvailable=ik, _tcpCartesianControlsAllowed=lambda:False,
        tcpDragEnabledCheckBox=control(), tcpKeyboardEnabledCheckBox=SimpleNamespace(enabled=False,checked=False),
        solveIkButton=control(), autoTaskHomeButton=control(), tcpCartesianNudgeButtons={},
        tcpTranslationStepMm=control(),tcpRotationStepDeg=control(), _tcpKeyboardShortcuts=[])
    update(p)
    assert p.autoTaskHomeButton.enabled is expected
    assert p.autoTaskHomeButton.toolTip


def test_same_pose_branch_search_preserves_geometry_and_records_all_attempts():
    f, state = facade()
    original = f._bridge.solve_moveit_tcp_position_axis_goal
    def branches(**kwargs):
        if kwargs['seed_joint_positions_si'] is None:
            state.calls.append(('ik', kwargs))
            return False, 'colliding', {}, {'termination_reason': 'colliding'}
        return original(**kwargs)
    f._bridge.solve_moveit_tcp_position_axis_goal = branches
    result = propose_auto_task_home(f, Result, POLICY)
    assert result.success and result.details['selectedIkSeedIndex'] == 1
    assert len(result.details['ikAttempts']) == 2
    assert sum(c[0] == 'goal' for c in state.calls) == 1
    assert all(c[1]['avoid_collisions'] is True for c in state.calls if c[0] == 'ik')
    assert result.details['positionWorldRasMm'] == (0, 0, 0)


def test_seed_budget_exhaustion_is_refusal_not_infeasibility():
    f, state = facade()
    calls = []
    f._bridge.solve_moveit_tcp_position_axis_goal = lambda **kw: (
        calls.append(kw) or False, 'colliding', {}, {'termination_reason': 'colliding'})
    result = propose_auto_task_home(f, Result, POLICY)
    assert not result.success and result.payload is None
    assert len(calls) == result.details['ikSeedBudget'] == 17
    assert 'does not prove infeasibility' in result.message


def test_unknown_static_authority_stops_before_next_seed():
    f, state = facade()
    f._bridge.check_moveit_static_joint_state = lambda q: (False, 'unavailable', False)
    result = propose_auto_task_home(f, Result, POLICY)
    assert not result.success and len(result.details['ikAttempts']) == 1
    assert result.details['authoritativeStaticValidity'] is False


def test_identity_change_between_seeds_stops_search():
    f, state = facade()
    def changed(**kw):
        state.identity = 'changed'
        return False, 'colliding', {}, {'termination_reason': 'colliding'}
    f._bridge.solve_moveit_tcp_position_axis_goal = changed
    result = propose_auto_task_home(f, Result, POLICY)
    assert not result.success and len(result.details['ikAttempts']) == 1
    assert 'changed between' in result.message


def test_seed_hints_stay_inside_actual_mechanical_limits():
    f, state = facade()
    seeds = module.auto_task_home_ik_seeds(f)
    assert seeds[0] is None and len(seeds) == 17
    from DENTOStep6Planning import default_task_joint_limits_from_urdf
    from math import degrees
    limits = default_task_joint_limits_from_urdf(f._logic.robotDescriptionPaths()[0])
    for seed in seeds[1:]:
        for index, value in enumerate(seed.values()):
            limit = getattr(limits, f'joint_{index + 1}')
            display = degrees(value) if limit.unit == 'deg' else value * 1000
            assert limit.minimum <= display <= limit.maximum


def test_native_collision_authority_unavailable_stops_after_one_attempt():
    f, state = facade()
    state.ik = False
    result = propose_auto_task_home(f, Result, POLICY)
    assert not result.success and len(result.details['ikAttempts']) == 1
    assert result.details['ikAttempts'][0]['ikDiagnostic']['termination_reason'] == 'collision_check_unavailable'


def test_authoritative_collision_rejection_can_try_next_seed():
    f, state = facade()
    calls = []
    def static(q):
        calls.append(q)
        return len(calls) > 1, 'collision' if len(calls) == 1 else 'clear', True
    f._bridge.check_moveit_static_joint_state = static
    result = propose_auto_task_home(f, Result, POLICY)
    assert result.success and len(calls) == 2
    assert result.details['ikAttempts'][0]['authoritativeStaticValidity'] is True
    assert result.details['ikAttempts'][0]['collisionAwareValidated'] is False


def test_outward_hint_uses_measured_bounds_and_direction():
    assert module.outward_separation_hint_mm([0, 10, 0, 10, 0, 10],
        [5, 15, 5, 15, 5, 15], [1, 0, 0]) == 16
    assert module.outward_separation_hint_mm([0, 10, 0, 10, 0, 10],
        [5, 15, 5, 15, 5, 15], [-1, 0, 0]) == 6
    with pytest.raises(ValueError):
        module.outward_separation_hint_mm([10, 0, 0, 10, 0, 10], [5,15,5,15,5,15], [1,0,0])


def test_one_outward_hint_can_produce_draft_after_midpoint_branch_exhaustion(monkeypatch):
    f, state = facade()
    original = f._bridge.solve_moveit_tcp_position_axis_goal
    def solve(**kw):
        if state.fk_z == 0:
            return False, 'colliding', {}, {'termination_reason': 'colliding'}
        return original(**kw)
    def hint(*args):
        state.fk_z = -3
        return -3, {'clearanceAuthority': False}
    monkeypatch.setattr(module, '_outward_home_depth_hint', hint)
    f._bridge.solve_moveit_tcp_position_axis_goal = solve
    result = propose_auto_task_home(f, Result, POLICY)
    assert result.success and result.details['depthMm'] == -3
    assert len(result.details['anchorAttempt']['ikAttempts']) == 17
    assert len(result.details['ikAttempts']) == 1
    assert result.details['outwardHint']['clearanceAuthority'] is False
    assert sum(c[0] == 'goal' for c in state.calls) == 2


def test_outward_hint_identity_change_refuses_before_new_goal(monkeypatch):
    f, state = facade()
    f._bridge.solve_moveit_tcp_position_axis_goal = lambda **kw: (
        False, 'colliding', {}, {'termination_reason': 'colliding'})
    def hint(*args):
        state.identity = 'changed'
        return -3, {}
    monkeypatch.setattr(module, '_outward_home_depth_hint', hint)
    result = propose_auto_task_home(f, Result, POLICY)
    assert not result.success and sum(c[0] == 'goal' for c in state.calls) == 1
    assert 'changed during' in result.details['outwardHintRefused']


def test_outward_hint_refusal_does_not_replace_original_failure(monkeypatch):
    f, state = facade()
    f._bridge.solve_moveit_tcp_position_axis_goal = lambda **kw: (
        False, 'colliding', {}, {'termination_reason': 'colliding'})
    def refuse(*args):
        raise ValueError('Measured hint exceeds bounded range')
    monkeypatch.setattr(module, '_outward_home_depth_hint', refuse)
    result = propose_auto_task_home(f, Result, POLICY)
    assert not result.success and len(result.details['ikAttempts']) == 17
    assert 'bounded range' in result.details['outwardHintRefused']
    assert sum(c[0] == 'goal' for c in state.calls) == 1


def test_production_outward_adapter_uses_audit_mesh_and_rotated_base(monkeypatch):
    import struct
    import numpy as np
    from types import ModuleType
    from DENTORobotPlacement import robot_link_mesh_poses_mm, joint_positions_si_from_display
    f, state = facade()
    package = PY.parents[2] / 'dentobot_description'
    paths = (package / 'urdf/dentobot.urdf', package)
    f._logic.robotDescriptionPaths = lambda: paths
    q = joint_positions_si_from_display(0, 20, 0, 20, 0)
    mesh = next(p for p in robot_link_mesh_poses_mm(*paths, q)
                if p.link_name == 'pneumatic_spindle-Copy')
    raw = mesh.mesh_path.read_bytes()
    count = struct.unpack_from('<I', raw, 80)[0]
    assert len(raw) == 84 + 50 * count
    vertices = np.frombuffer(raw, offset=84, count=count, dtype=np.dtype([
        ('normal', '<f4', (3,)), ('vertices', '<f4', (3, 3)), ('attr', '<u2')
    ]))['vertices'].reshape(-1, 3).astype(float)
    matrix = np.asarray(mesh.matrix_base_from_mesh_mm)
    points = vertices @ matrix[:3, :3].T + matrix[:3, 3]
    # Base rotated90deg: world outward -Y becomes base -X.
    bounds = np.column_stack((points.min(0) - 100, points.max(0) + 100))
    bounds[0, 0] = points.max(0)[0] - 5
    record = {'outgoing_collision_object_id': 'jaw',
              'outgoing_bounds_base_link_mm': bounds.reshape(-1).tolist()}
    f._logic.collisionSceneAuditRecord = lambda p: SimpleNamespace(object_records=[record])
    class BaseMatrix:
        def GetElement(self, i, j):
            return ((0, -1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))[i][j]
    class Reader:
        def SetFileName(self, path):
            assert Path(path) == mesh.mesh_path
        def Update(self):
            pass
        def GetOutput(self):
            return SimpleNamespace(GetNumberOfPoints=lambda: len(vertices),
                GetPoints=lambda: SimpleNamespace(GetData=lambda: vertices))
    vtk = ModuleType('vtk'); vtk.vtkSTLReader = Reader; vtk.vtkMatrix4x4 = BaseMatrix
    util = ModuleType('vtk.util'); numpy_support = ModuleType('vtk.util.numpy_support')
    numpy_support.vtk_to_numpy = lambda data: data
    for name, mod in [('vtk', vtk), ('vtk.util', util), ('vtk.util.numpy_support', numpy_support)]:
        monkeypatch.setitem(sys.modules, name, mod)
    parameter = SimpleNamespace(robotBaseTransform=SimpleNamespace(GetMatrixTransformToWorld=lambda m: None))
    f._require_context = lambda: parameter
    details = {'anchorWorldRasMm': (0, 0, 0),
        'trajectoryWorldRasMm': {'entry': (0, 10, 0), 'target': (0, 10, 10)},
        'ikAttempts': [{'ikDiagnostic': {'termination_reason': 'colliding',
            'collision_pairs': [('jaw', 'pneumatic_spindle-Copy')], 'best_joint_positions_si': q}}]}
    f._logic.step6MouthBarrier = lambda p: SimpleNamespace(opening=SimpleNamespace(
        origin_mm=(0, 1000, 0), normal_outward=(0, -1, 0)), summary={'lip_thickness_mm': 8})
    depth, hint = module._outward_home_depth_hint(f, details, POLICY)
    assert depth == pytest.approx(-6)
    assert hint['perObjectDistanceMm']['jaw'] == pytest.approx(6)
    assert hint['perObjectDistanceMm']['mouth_barrier_front_plane'] == 0
    assert hint['clearanceAuthority'] is False
    # Same adapter refuses missing current audit objects before another candidate.
    f._logic.collisionSceneAuditRecord = lambda p: SimpleNamespace(object_records=[])
    with pytest.raises(ValueError, match='absent from the current audit'):
        module._outward_home_depth_hint(f, details, POLICY)
    # Verify collision geometry parity is mandatory, independently of visual loading.
    from xml.etree import ElementTree
    tree = ElementTree.parse(paths[0])
    tree.find("./link[@name='pneumatic_spindle-Copy']/collision/origin").set('xyz', '0 0 0')
    monkeypatch.setattr(ElementTree, 'parse', lambda *args: tree)
    with pytest.raises(ValueError, match='visual/collision geometry differs'):
        module._outward_home_depth_hint(f, details, POLICY)


def test_lip_plane_hint_accounts_for_entire_spindle_and_oblique_retreat():
    assert module.outward_plane_hint_mm([[0, 0, -5], [0, 0, 2]], [0,0,0],
                                       [0,0,1], [0,0,1], 8) == 14
    assert module.outward_plane_hint_mm([[0, 0, -5], [0, 0, 2]], [0,0,0],
                                       [0,0,1], [0,3,4], 8) == pytest.approx(17.5)
    with pytest.raises(ValueError, match='does not retreat'):
        module.outward_plane_hint_mm([[0,0,-5]], [0,0,0], [0,0,1], [0,1,0], 8)
    with pytest.raises(ValueError):
        module.outward_plane_hint_mm([[0,0,float('nan')]], [0,0,0], [0,0,1], [0,0,1], 8)


def barrier(vertices=None, thickness=8, normal=(0, 0, 1)):
    return SimpleNamespace(opening=SimpleNamespace(
        vertices_mm=vertices or [(-10,-5,0),(10,-5,0),(10,5,0),(-10,5,0)],
        normal_outward=normal), summary={'lip_thickness_mm': thickness})


def test_barrier_anchor_follows_opening_geometry_and_slab_adjustments():
    assert module.mouth_barrier_opening_center(barrier()) == (0, 0, 4)
    shifted = [(x+20, y-3, z+2) for x,y,z in barrier().opening.vertices_mm]
    assert module.mouth_barrier_opening_center(barrier(shifted, thickness=4)) == (20,-3,4)
    assert module.mouth_barrier_opening_center(barrier(normal=(0,1,0))) == (0,4,0)


@pytest.mark.parametrize('value', [None, barrier(thickness=0), barrier(thickness=float('nan')),
    barrier(vertices=[(0,0,0)]), barrier(normal=(0,0,0))])
def test_invalid_or_missing_current_barrier_cannot_define_home(value):
    with pytest.raises(ValueError):
        module.mouth_barrier_opening_center(value)


def test_barrier_source_retains_incisor_reference_and_tracks_current_barrier():
    f, state = facade()
    state.midpoint = (100,200,300)
    b = barrier()
    f._logic.step6MouthBarrier = lambda p: b
    source = REAL_BARRIER_SOURCE_ADAPTER(f, f._require_context())
    assert source['centerWorldRasMm'] == (0,0,4)
    assert source['incisorMidpointWorldRasMm'] == (100,200,300)
    assert source['anchorKind'] == 'mouth_barrier_opening_center'
    b.summary['lip_thickness_mm'] = 4
    assert REAL_BARRIER_SOURCE_ADAPTER(f, f._require_context())['centerWorldRasMm'] == (0,0,2)


def test_actual_barrier_adapter_drives_goal_and_rejects_changed_slab(monkeypatch):
    f, state = facade()
    b = barrier()
    f._logic.step6MouthBarrier = lambda p: b
    monkeypatch.setattr(module, 'mouth_barrier_task_home_source', REAL_BARRIER_SOURCE_ADAPTER)
    state.fk_z = 4
    result = propose_auto_task_home(f, Result, POLICY)
    assert result.success and result.details['anchorWorldRasMm'] == (0,0,4)
    assert state.calls[0][1][2][3] == 4
    state.calls.clear()
    state.after_fk = lambda: b.summary.update(lip_thickness_mm=6)
    result = propose_auto_task_home(f, Result, POLICY)
    assert not result.success and result.payload is None
    assert 'inputs changed' in result.message
