"""Exact-text reuse avoids repeated metrics normalization, not geometry checks."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


def test_restore_metrics_digest_reuses_only_identical_text():
    source = Path(__file__).resolve().parents[1] / 'DENTOWorkflow/Resources/Python/dentobot_workflow/logic_case_foundation.py'
    tree = ast.parse(source.read_text())
    method = next(node for cls in tree.body if isinstance(cls, ast.ClassDef)
                  for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'caseFoundationSourceSegmentationFingerprint')
    calls = []
    def canonical(value):
        calls.append(value)
        return json.dumps(value, sort_keys=True)
    class Strings:
        def GetNumberOfValues(self): return 0
    namespace = {'json': json, 'hashlib': hashlib, 'canonical_json': canonical,
        'vtk': SimpleNamespace(vtkStringArray=Strings), 'logging': SimpleNamespace(info=lambda *args: None)}
    exec(compile(ast.Module([method], type_ignores=[]), str(source), 'exec'), namespace)
    segmentation = SimpleNamespace(GetConversionParameter=lambda key: '', GetSegmentIDs=lambda ids: None,
                                   GetMTime=lambda: 1)
    text = ['{"n":1}']
    node = SimpleNamespace(GetSegmentation=lambda: segmentation, GetAttribute=lambda key: text[0],
                           GetID=lambda: 'segmentation')
    keys = []
    logic = SimpleNamespace(_caseBundleMetricsDigestCache={},
                            _cachedCaseFoundationFingerprint=lambda key, build: keys.append(key) or 'digest')
    method = namespace[method.name]
    assert method(logic, node) == method(logic, node) == 'digest'
    assert len(calls) == 1 and keys[0] == keys[1]
    text[0] = '{"n":2}'
    method(logic, node)
    assert len(calls) == 2 and keys[-1] != keys[0]
    logic._caseBundleMetricsDigestCache = None
    method(logic, node)
    method(logic, node)
    assert len(calls) == 6  # before/after input checks outside a transaction
