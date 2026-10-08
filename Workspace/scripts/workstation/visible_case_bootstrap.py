# Slicer-side script for `visible-case` runs. The supervisor prepends `PLAN = {...}`.
# Only slicer, qt and the standard library are used. Modal dialogs are never left open:
# framing probes the planning target first, records (instead of showing) any message the
# production action reports, and falls back to the 3D camera reset.
import hashlib,json,sys,time,traceback
from pathlib import Path
import qt,slicer
T0=time.monotonic()
ROOT=Path(PLAN["repo"]); OUT=Path(PLAN["evidence"]); SHOTS=OUT/"screenshots"; SHOTS.mkdir(exist_ok=True)
LOG=[]; KEPT={}; WIDGET=[None]; FINISHED=[False]
MODALS=("errorDisplay","infoDisplay","warningDisplay")  # production framing reports through these; never leave one open
STATE={"code":1,"case_loaded":False,"screenshots":[],"dropped_duplicates":[],"framing":None}
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def note(msg):
    LOG.append({"t_s":round(time.monotonic()-T0,2),"msg":msg}); print("DENTOBOT_VISIBLE",msg,flush=True)
    (OUT/"session-log.json").write_text(json.dumps(LOG,indent=2)+"\n")
def shot(name):
    slicer.app.processEvents(); slicer.util.forceRenderAllViews(); slicer.app.processEvents()
    path=SHOTS/f"{name}.png"
    if not slicer.util.mainWindow().grab().save(str(path)): raise RuntimeError("screenshot failed: "+name)
    actual=digest(path)
    if actual in KEPT.values():
        path.unlink(); STATE["dropped_duplicates"].append(name); note("dropped duplicate "+name); return False
    KEPT[path.name]=actual; STATE["screenshots"].append(path.name); note("screenshot "+path.name); return True
def reset_3d_views():
    lm=slicer.app.layoutManager()
    for i in range(lm.threeDViewCount):
        view=lm.threeDWidget(i).threeDView(); view.resetFocalPoint(); view.resetCamera()
def reason_of(exc):
    lines=str(exc).splitlines()
    return (lines[0] if lines else type(exc).__name__)[:200]
def frame_target(widget):
    """Frame the planning target with the production action. status: production | fallback | unavailable.
    Only status "production" counts as framed; anything else is recorded and reported, never claimed."""
    try:
        bounds=widget._planningTargetBoundsWorld()
    except Exception as exc:
        reset_3d_views(); return {"method":"reset_3d_camera","status":"unavailable","reason":reason_of(exc)}
    if bounds is None:
        reset_3d_views(); return {"method":"reset_3d_camera","status":"unavailable","reason":"planning target bounds are empty"}
    shown=[]; saved={name:getattr(slicer.util,name,None) for name in MODALS}
    for name in MODALS: setattr(slicer.util,name,lambda text="",*a,**k:shown.append(str(text)))
    try:
        widget.onFramePlanningTarget()
    except Exception as exc:
        reset_3d_views(); return {"method":"reset_3d_camera","status":"fallback","reason":"production framing failed: "+reason_of(exc)}
    finally:
        for name,original in saved.items(): setattr(slicer.util,name,original)
    if shown:
        reset_3d_views(); return {"method":"reset_3d_camera","status":"fallback","reason":"production framing reported: "+shown[0][:150]}
    return {"method":"onFramePlanningTarget","status":"production","reason":"planning target bounds available"}
def finish(error=None):
    if FINISHED[0]: return
    FINISHED[0]=True
    try:
        if error is None: shot("05-before-exit")
    except Exception: error=traceback.format_exc()
    if error: STATE["error"]=error; note("ERROR "+error.splitlines()[-1])
    STATE["code"]=0 if (error is None and STATE["case_loaded"]) else 1
    for name in ("startup.png","final.png"):
        src=SHOTS/("01-startup.png" if name=="startup.png" else (STATE["screenshots"][-1] if STATE["screenshots"] else ""))
        if src.is_file(): (OUT/name).write_bytes(src.read_bytes())
    STATE["elapsed_s"]=round(time.monotonic()-T0,1)
    (OUT/"case-result.json").write_text(json.dumps(STATE,indent=2)+"\n")
    (OUT/"reload-result.json").write_text(json.dumps({"requested_exit_code":STATE["code"],"scope":"visible case open + screenshots; no reload test"})+"\n")
    if STATE["code"]==0: print("DENTOBOT_VISIBLE_CASE_PASS",flush=True)
    slicer.util.exit(STATE["code"])
def hold_shot():
    try:
        lm=slicer.app.layoutManager(); lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
        STATE["framing_3d_only"]=frame_target(WIDGET[0]); note("one-up framing: "+STATE["framing_3d_only"]["status"])
        shot("04-3d-only-target-framed")
    except Exception:
        finish(traceback.format_exc())
def open_case():
    try:
        widget=slicer.modules.dentoworkflow.widgetRepresentation().self()
        WIDGET[0]=widget
        note("opening case via production widget._openCaseBundle: "+PLAN["case"])
        widget._openCaseBundle(PLAN["case"])
        STATE["case_loaded"]=True; note("case opened")
        shot("02-case-loaded")
        lm=slicer.app.layoutManager()
        lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
        STATE["framing"]=frame_target(widget); note("framing: "+STATE["framing"]["status"]+" via "+STATE["framing"]["method"])
        shot("03-four-up-target-framed")
        note(f"holding window visible for {PLAN['hold_s']} s")
        qt.QTimer.singleShot(int(PLAN["hold_s"]*500),hold_shot)
        qt.QTimer.singleShot(int(PLAN["hold_s"]*1000),finish)
    except Exception:
        finish(traceback.format_exc())
def start():
    try:
        mw=slicer.util.mainWindow(); mw.showMaximized(); mw.raise_(); mw.activateWindow()
        slicer.util.selectModule("DENTOWorkflow")
        files={rel:{"path":str(ROOT/rel),"sha256":digest(ROOT/rel),"expected_sha256":PLAN["hashes"][rel]} for rel in PLAN["common_files"]}
        for rel,item in files.items():
            mod=[m for m in sys.modules.values() if getattr(m,"__file__",None) and Path(m.__file__).resolve()==(ROOT/rel).resolve()]
            item["matched"]=bool(mod) and item["sha256"]==item["expected_sha256"]
        (OUT/"loaded-code.json").write_text(json.dumps({"matched":all(i["matched"] for i in files.values()),"files":files},indent=2)+"\n")
        if not all(i["matched"] for i in files.values()): raise RuntimeError("loaded code path/hash mismatch")
        print("DENTOBOT_B_LOADED_CODE_PASS",flush=True); note("Slicer up; pinned code loaded")
        shot("01-startup")
        qt.QTimer.singleShot(1000,open_case)
    except Exception:
        finish(traceback.format_exc())
qt.QTimer.singleShot(3000,start)
qt.QTimer.singleShot(900000,lambda:slicer.util.exit(3))
