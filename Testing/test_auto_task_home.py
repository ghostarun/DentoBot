"""Known-answer geometry and draft-only Auto Task Home coordination (no ROS)."""
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

PY = Path(__file__).resolve().parents[1] / 'DENTOWorkflow/Resources/Python'
sys.path.insert(0, str(PY))
from dentobot_workflow import auto_task_home as module
from dentobot_workflow.auto_task_home import auto_task_home_geometry, pose_residual, propose_auto_task_home, incisor_biting_edge_midpoint


REAL_SOURCE_ADAPTER = module.incisor_biting_edge_source


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


def facade():
    state = SimpleNamespace(identity='current', scene=True, ik=True, fk=True, fk_z=0.0,
                            axis=1.0, calls=[], after_fk=None, midpoint=(0., 0., 0.))
    parameter = SimpleNamespace(robotBaseTransform='base')
    joints = {f'j{i}': i / 10 for i in range(1, 6)}
    def fk(q, *, base_transform):
        state.calls.append(('fk', q, base_transform))
        pose = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, state.axis, state.fk_z], [0, 0, 0, 1]]
        if state.after_fk:
            state.after_fk()
        return state.fk, 'FK', pose
    def goal(pose):
        state.calls.append(('goal', pose.rows))
        return Result(True, 'goal', 'goal')
    def solve():
        state.calls.append(('ik',))
        return Result(state.ik, 'ik', 'IK unavailable' if not state.ik else 'IK',
                      {'authoritativeStaticValidity': state.ik}, joints if state.ik else None)
    f = SimpleNamespace(
        _require_context=lambda: parameter,
        _manual_jog_current_identity=lambda p, **kw: {'identity':state.identity},
        defaultTaskSpaceRoi=lambda: Result(True, 'roi', 'ROI', payload={
            'centerWorldRasMm':state.midpoint, 'openingRevision':1, 'gapLineNodeId':'line'}),
        _logic=SimpleNamespace(step6TrajectorySummary=lambda p: {
            'isValid':True, 'entryRas':(0,0,10), 'targetRas':(0,0,20)}),
        moveItSceneComparison=lambda: {'matches':state.scene},
        _bridge=SimpleNamespace(tool_pose_matrices_world_mm=lambda *a: [Matrix(), Matrix()],
                                compute_moveit_tcp_pose_world_ras_mm=fk),
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
    assert [c[0] for c in state.calls] == ['goal', 'ik', 'limits', 'fk']
    assert result.details['source']['gapLineNodeId'] == 'line'
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
    scope = {}
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
