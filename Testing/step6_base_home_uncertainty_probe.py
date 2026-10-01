"""Fail-closed headed probe for uncertain Base and Task Home acknowledgements."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

try:
    import step6_full_chain_probe as _full_chain
except ImportError:
    from Testing import step6_full_chain_probe as _full_chain


class BaseHomeUncertaintyProbeError(RuntimeError):
    def __init__(self, message, evidence):
        self.evidence = evidence
        super().__init__(message)


_MISSING = object()
_BASE_ACK_LOST = "headed test: Base commit acknowledgement lost"
_HOME_ACK_LOST = "headed test: Home save acknowledgement lost"


def _matrix(value):
    try:
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError):
        return None
    return values if len(values) == 16 and all(isfinite(item) for item in values) else None


def _result(result):
    details = getattr(result, "details", None)
    return {
        "success": getattr(result, "success", None),
        "code": str(getattr(result, "code", "") or ""),
        "message": str(getattr(result, "message", "") or ""),
        "details": _full_chain._jsonable(details if isinstance(details, Mapping) else {}),
    }


def run_base_home_uncertainty_probe(
    widget,
    panel,
    facade,
    *,
    process_events,
    capture_callback,
    joint_names,
    expected_error_dialog_callback,
):
    """Drive current-case Base and Home uncertainty flows through production GUI owners.

    ``expected_error_dialog_callback(button, expected_text, capture_stage)`` must
    click the supplied button, capture and dismiss its modal, and return positive
    click/capture/dismiss flags, the dialog text, and a capture reference.
    """
    names = tuple(joint_names)
    evidence = {
        "status": "running",
        "scope": "current-case simulation-only GUI workflow",
        "joint_names": list(names),
        "captures": [],
        "joint_snapshots": {},
        "base": {},
        "home": {},
        "calls": {
            "lockBase": 0,
            "saveTaskHome": 0,
            "baselineSaveTaskHome": 0,
            "reconcileManualBaseAcceptance": 0,
            "reconcileManualTaskHomeAcceptance": 0,
            "guardManualRobotJog": 0,
        },
        "restored_methods": [],
    }
    patches = []
    failure = None

    def abort(message, status="blocked"):
        evidence["status"] = status
        raise BaseHomeUncertaintyProbeError(message, evidence)

    def capture(stage):
        reference = capture_callback(stage)
        if reference is None or reference == "":
            abort(f"Screenshot capture returned no reference at {stage}.")
        evidence["captures"].append(
            {"stage": str(stage), "reference": _full_chain._jsonable(reference)}
        )
        return _full_chain._jsonable(reference)

    def snapshot(stage):
        try:
            result = _full_chain._snapshot(facade, facade._bridge, names)["joints_si"]
        except Exception as exc:
            abort(f"J1–J5 state evidence is unavailable at {stage}: {exc}")
        evidence["joint_snapshots"][stage] = result
        return result

    def unchanged(before, stage):
        after = snapshot(stage)
        if any(before[key] != after[key] for key in ("accepted", "monitored", "displayed")):
            abort(f"{stage} changed accepted, monitored, or displayed J1–J5 state.")

    def patch(owner, name, replacement):
        namespace = getattr(owner, "__dict__", None)
        if namespace is None:
            abort(f"Cannot safely restore patched façade method {name}.")
        prior = namespace.get(name, _MISSING)
        setattr(owner, name, replacement)

        def restore():
            if prior is _MISSING:
                delattr(owner, name)
            else:
                setattr(owner, name, prior)
            evidence["restored_methods"].append(name)

        patches.append(restore)
        return restore

    def restore_patch(restore):
        try:
            restore()
        except Exception as exc:
            evidence.setdefault("restoration_errors", []).append(str(exc))
            raise
        if restore in patches:
            patches.remove(restore)

    def click(button, name):
        if not bool(getattr(button, "enabled", False)):
            abort(f"Production GUI control is disabled: {name}.")
        button.click()
        process_events(0.1)

    def modal(button, expected_text, owner_evidence):
        start = len(evidence["captures"])
        capture_stage = (
            "base-unknown-modal"
            if owner_evidence is evidence["base"]
            else "home-unknown-modal"
        )
        try:
            observed = expected_error_dialog_callback(button, expected_text, capture_stage)
        except Exception as exc:
            abort(f"Expected error dialog was not captured and dismissed: {exc}")
        if not isinstance(observed, Mapping) or any(
            observed.get(key) is not True
            for key in ("button_clicked", "dialog_captured", "dialog_dismissed")
        ):
            abort("Error-dialog callback lacks positive click/capture/dismiss evidence.")
        text = str(observed.get("dialog_text") or "")
        capture_reference = observed.get("capture_reference")
        if expected_text not in text or not capture_reference:
            abort("Captured error dialog omitted its expected text or screenshot reference.")
        evidence["captures"].append({
            "stage": capture_stage,
            "reference": _full_chain._jsonable(capture_reference),
        })
        owner_evidence["dialog"] = _full_chain._jsonable(observed)
        owner_evidence["dialog_capture_stages"] = evidence["captures"][start:]
        process_events(0.1)
        return observed

    def set_substep(index):
        configure = getattr(widget, "_configureRobotSimulationShellSubstep", None)
        update = getattr(widget, "_updateStep6PlanningUi", None)
        if not callable(configure) or not callable(update):
            abort("Production Step 6 navigation/update APIs are unavailable.")
        configure(index)
        update()
        process_events(0.1)

    def base_review():
        result = facade.manualBaseReview()
        details = result.details if isinstance(getattr(result, "details", None), Mapping) else {}
        return result, details

    def home_review():
        result = facade.manualTaskHomeReview()
        details = result.details if isinstance(getattr(result, "details", None), Mapping) else {}
        return result, details

    def reaccept_home_after_base_invalidation(home_before_details):
        baseline = {
            "status": "running",
            "runtime_validated_before_base": home_runtime_before_base,
            "runtime_validated_after_base": home_runtime_after_base,
            "identity_status_before": home_before_details.get("identityStatus"),
            "captures": {},
        }
        evidence["home"]["baseline_revalidation"] = baseline
        try:
            before = snapshot("before_home_runtime_revalidation")
            accepted = before["accepted"]
            if any(
                not _full_chain._same_vector(accepted, before[key], tolerance=1.0e-12)
                for key in ("monitored", "displayed")
            ):
                abort("Accepted, monitored, and displayed J1–J5 differ before Home revalidation.", "pending_home_prerequisite")
            saved_before = logic.taskHomeRecord(parameter_node)
            revision_before = getattr(saved_before, "revision", None)
            if saved_before is None or isinstance(revision_before, bool) or not isinstance(revision_before, int) or revision_before < 0:
                abort("Saved Task Home revision is unavailable before revalidation.", "pending_home_prerequisite")
            baseline.update(
                saved_revision_before=revision_before,
                expected_saved_revision=revision_before + 1,
                joints_before=_full_chain._jsonable(before),
            )
            baseline["captures"]["before"] = capture("home-runtime-revalidation-before")

            set_substep(3)
            click(panel.resetManualJogDraftButton, "Reset Draft to Accepted J1-J5")
            draft = panel.manualJogJointPositionsSi()
            baseline["draft_joint_positions_si"] = _full_chain._jsonable(draft)
            baseline["captures"]["draft"] = capture("home-runtime-revalidation-draft")
            if not _full_chain._same_vector(accepted, draft, tolerance=1.0e-12):
                abort("GUI draft reset did not preserve the exact accepted J1–J5 pose.", "pending_home_prerequisite")
            unchanged(before, "after_home_runtime_revalidation_draft_reset")

            set_substep(2)
            click(panel.reviewTaskHomeButton, "Review Draft as Task Home")
            staged, staged_details = home_review()
            candidate = staged_details.get("candidateJointPositionsSi")
            baseline["identity_status_staged"] = staged_details.get("identityStatus")
            baseline["candidate_joint_positions_si"] = _full_chain._jsonable(candidate)
            baseline["staged_review"] = _result(staged)
            baseline["captures"]["staged"] = capture("home-runtime-revalidation-staged")
            if (
                getattr(staged, "success", False) is not True
                or staged_details.get("identityStatus") != "current"
                or staged_details.get("staged") is not True
                or staged_details.get("acceptanceStatus") != "review"
                or not isinstance(candidate, Mapping)
                or set(candidate) != set(names)
                or not _full_chain._same_vector(accepted, candidate, tolerance=1.0e-12)
            ):
                abort("GUI Task Home review did not stage the exact current accepted pose.", "pending_home_prerequisite")
            unchanged(before, "after_home_runtime_revalidation_review")

            save_state = {"results": []}
            original_save = facade.saveTaskHome

            def tracked_baseline_save(*args, **kwargs):
                evidence["calls"]["baselineSaveTaskHome"] += 1
                try:
                    result = original_save(*args, **kwargs)
                except Exception as exc:
                    save_state["results"].append({"raised": str(exc)})
                    raise
                save_state["results"].append(_result(result))
                return result

            save_restore = patch(facade, "saveTaskHome", tracked_baseline_save)
            try:
                click(panel.acceptTaskHomeButton, "Accept Task Home")
            finally:
                restore_patch(save_restore)

            baseline["normal_save_result"] = save_state["results"][-1] if save_state["results"] else None
            saved_after = logic.taskHomeRecord(parameter_node)
            revision_after = getattr(saved_after, "revision", None)
            runtime_after = bool(facade.taskHomeRuntimeValidated(parameter_node))
            accepted_home, accepted_details = home_review()
            after = snapshot("after_home_runtime_revalidation")
            baseline.update(
                saved_revision_after=revision_after,
                runtime_validated_after_reaccept=runtime_after,
                accepted_review=_result(accepted_home),
                joints_after=_full_chain._jsonable(after),
            )
            baseline["identity_status_after"] = accepted_details.get("identityStatus")
            baseline["captures"]["accepted"] = capture("home-runtime-revalidation-accepted")
            if (
                evidence["calls"]["baselineSaveTaskHome"] != 1
                or not isinstance(baseline["normal_save_result"], Mapping)
                or baseline["normal_save_result"].get("success") is not True
                or baseline["normal_save_result"].get("code") != "task_home_saved"
                or baseline["normal_save_result"].get("details", {}).get("runtimeValidated") is not True
                or isinstance(revision_after, bool)
                or not isinstance(revision_after, int)
                or revision_after != revision_before + 1
                or runtime_after is not True
                or getattr(accepted_home, "success", False) is not True
                or accepted_details.get("identityStatus") != "current"
                or accepted_details.get("staged") is not False
                or accepted_details.get("acceptanceStatus") != "accepted"
                or not _full_chain._same_vector(accepted, accepted_details.get("acceptedJointPositionsSi"), tolerance=1.0e-12)
                or any(before[key] != after[key] for key in ("accepted", "monitored", "displayed"))
            ):
                abort("GUI Task Home baseline reacceptance did not prove a new validated revision and unchanged current pose.", "pending_home_prerequisite")
            baseline["status"] = "complete"
            evidence["home"].pop("pending_prerequisite", None)
        except BaseHomeUncertaintyProbeError as exc:
            baseline["status"] = "failed"
            evidence["home"]["pending_prerequisite"] = str(exc)
            evidence["status"] = "pending_home_prerequisite"
            raise BaseHomeUncertaintyProbeError(str(exc), evidence) from exc
        except Exception as exc:
            baseline["status"] = "failed"
            reason = f"Task Home GUI revalidation could not be proven: {type(exc).__name__}: {exc}"
            evidence["home"]["pending_prerequisite"] = reason
            abort(reason, "pending_home_prerequisite")

    try:
        if len(names) != 5 or len(set(names)) != 5 or names != tuple(sorted(names)):
            abort("joint_names must contain the five unique canonical joints in order.")
        if getattr(widget, "_robotSimulationPanel", None) is not panel:
            abort("Provided panel is not the widget's production simulation panel.")
        if getattr(widget, "_robotWorkflowFacade", None) is not facade:
            abort("Provided façade is not the widget's production workflow façade.")
        capabilities = facade.capabilities()
        if getattr(capabilities, "simulation_only", None) is not True:
            abort("The active robot capability is not simulation-only.")
        if getattr(capabilities, "connected", None) is not True:
            abort("The simulation-only ROS/MoveIt session is not connected.")
        if str(getattr(facade.currentRobotState(), "scene_kind", "")) != "case":
            abort("A current case scene is required.")
        parameter_node = getattr(widget, "_parameterNode", None)
        logic = getattr(widget, "logic", None)
        if parameter_node is None or logic is None or getattr(facade, "_bridge", None) is None:
            abort("Current Step 6 parameter node, logic, or native bridge is unavailable.")
        required = (
            "lockBase", "manualBaseReview", "acceptManualBaseReview",
            "reconcileManualBaseAcceptance", "saveTaskHome",
            "manualTaskHomeReview", "acceptManualTaskHomeReview",
            "reconcileManualTaskHomeAcceptance", "guardManualRobotJog",
        )
        if any(not callable(getattr(facade, name, None)) for name in required):
            abort("A required production façade signature is unavailable.")

        joints_before = snapshot("before_base")
        home_runtime_before_base = bool(facade.taskHomeRuntimeValidated(parameter_node))
        initial_base, initial_details = base_review()
        base_matrix = _matrix(initial_details.get("acceptedMatrixWorldRasMm"))
        if (
            getattr(initial_base, "success", False) is not True
            or initial_details.get("staged") is True
            or initial_details.get("identityStatus") != "current"
            or initial_details.get("acceptanceStatus") == "unknown"
            or initial_details.get("acceptanceUncertainty")
            or base_matrix is None
        ):
            abort("A current accepted Base without a staged candidate or uncertainty is required.")
        base_locked = bool(getattr(facade.currentRobotState(), "base_locked", False))
        evidence["base"].update(
            accepted_matrix_world_ras_mm=list(base_matrix),
            initially_locked=base_locked,
            simulation_only=True,
        )
        capture("base-before-review")
        set_substep(1)
        if base_locked:
            click(widget.ui.unlockRobotBaseMountButton, "Unlock Accepted Base")
            unlock_review, unlock_details = base_review()
            if (
                bool(getattr(facade.currentRobotState(), "base_locked", True))
                or _matrix(unlock_details.get("acceptedMatrixWorldRasMm")) != base_matrix
                or getattr(unlock_review, "success", False) is not True
            ):
                abort("GUI Base unlock did not preserve the exact accepted matrix.")
            evidence["base"]["gui_unlock_preserved_matrix"] = True
            capture("base-unlocked-same-matrix")

        click(panel.beginManualBaseReviewButton, "Review Current Base")
        staged_base, staged_details = base_review()
        candidate = _matrix(staged_details.get("candidateMatrixWorldRasMm"))
        if (
            getattr(staged_base, "success", False) is not True
            or staged_details.get("staged") is not True
            or staged_details.get("identityStatus") != "current"
            or candidate != base_matrix
            or _matrix(staged_details.get("acceptedMatrixWorldRasMm")) != base_matrix
        ):
            abort("GUI Base review did not stage the unchanged accepted matrix.")
        evidence["base"]["candidate_matrix_world_ras_mm"] = list(candidate)
        unchanged(joints_before, "after_base_stage")
        capture("base-zero-displacement-staged")

        original_lock = facade.lockBase
        lock_state = {"inject": True, "results": []}

        def tracked_lock(*args, **kwargs):
            evidence["calls"]["lockBase"] += 1
            try:
                result = original_lock(*args, **kwargs)
            except Exception as exc:
                lock_state["results"].append({"raised": str(exc)})
                raise
            lock_state["results"].append(_result(result))
            if lock_state["inject"] and getattr(result, "success", False) is True:
                lock_state["inject"] = False
                raise RuntimeError(_BASE_ACK_LOST)
            return result

        patch(facade, "lockBase", tracked_lock)
        base_dialog = modal(widget.ui.lockRobotBaseMountButton, "Base", evidence["base"])
        if evidence["calls"]["lockBase"] != 1:
            abort("GUI Base accept did not call lockBase exactly once.")
        evidence["base"]["underlying_lock_result"] = lock_state["results"][-1]
        if not lock_state["results"][-1].get("success") is True:
            abort("Underlying lockBase failed; no acknowledgement-loss exception was injected.", "original_failure")
        if _BASE_ACK_LOST not in str(base_dialog.get("dialog_text") or ""):
            abort("Base dialog did not report the injected lost acknowledgement.")
        unknown_base, unknown_details = base_review()
        if (
            getattr(unknown_base, "success", False) is not True
            or unknown_details.get("staged") is not True
            or unknown_details.get("identityStatus") != "current"
            or unknown_details.get("acceptanceStatus") != "unknown"
            or not unknown_details.get("acceptanceUncertainty")
            or unknown_details.get("failureEvidence") is None
            or _matrix(unknown_details.get("candidateMatrixWorldRasMm")) != candidate
        ):
            abort("Lost Base acknowledgement did not retain the unknown latch, candidate, and failure evidence.")
        evidence["base"]["unknown_review"] = _result(unknown_base)
        unchanged(joints_before, "after_base_lost_ack")
        widget._updateStep6PlanningUi()
        if bool(getattr(panel.cancelManualBaseReviewButton, "enabled", True)):
            abort("GUI Base cancellation remained enabled during unknown acceptance.")
        reconcile_owner = widget.ui.lockRobotBaseMountButton
        evidence["base"]["retry_owner_text"] = str(getattr(reconcile_owner, "text", ""))
        if "Reconcile" not in evidence["base"]["retry_owner_text"]:
            abort("Base acceptance owner did not switch to reconciliation while unknown.")
        panel.cancelManualBaseReviewButton.click()
        process_events(0.1)
        retained_base, retained_details = base_review()
        if (
            retained_details.get("acceptanceStatus") != "unknown"
            or _matrix(retained_details.get("candidateMatrixWorldRasMm")) != candidate
            or evidence["calls"]["lockBase"] != 1
        ):
            abort("Blocked Base cancellation changed the candidate or retried lockBase.")
        capture("base-unknown-retained")

        original_base_reconcile = facade.reconcileManualBaseAcceptance
        base_reconcile_results = []

        def tracked_base_reconcile(*args, **kwargs):
            evidence["calls"]["reconcileManualBaseAcceptance"] += 1
            result = original_base_reconcile(*args, **kwargs)
            base_reconcile_results.append(result)
            return result

        patch(facade, "reconcileManualBaseAcceptance", tracked_base_reconcile)
        click(panel.reconcileManualBaseStateButton, "Reconcile Base State")
        base_reconcile = base_reconcile_results[-1]
        base_reconcile_details = base_reconcile.details
        if (
            evidence["calls"]["reconcileManualBaseAcceptance"] != 1
            or getattr(base_reconcile, "success", False) is not True
            or base_reconcile_details.get("reconciliationStatus") != "acknowledged"
            or base_reconcile_details.get("staged") is not True
            or _matrix(base_reconcile_details.get("candidateMatrixWorldRasMm")) != candidate
        ):
            abort("GUI Base reconcile did not acknowledge the scene while retaining an unaccepted candidate.")
        checked_base, checked_details = base_review()
        audit = logic.collisionSceneAuditRecord(parameter_node)
        ack = getattr(audit, "runtime_acknowledgement", None)
        ids = tuple(
            str(record.get("outgoing_collision_object_id") or "")
            for record in (getattr(audit, "object_records", ()) or ())
            if isinstance(record, Mapping)
        )
        ack_ids = tuple(base_reconcile_details.get("acknowledgedObjectIds") or ())
        if (
            getattr(checked_base, "success", False) is not True
            or checked_details.get("identityStatus") != "current"
            or checked_details.get("acceptanceStatus") == "unknown"
            or checked_details.get("staged") is not True
            or _matrix(checked_details.get("candidateMatrixWorldRasMm")) != candidate
            or _matrix(checked_details.get("acceptedMatrixWorldRasMm")) != base_matrix
            or getattr(facade, "_planning_scene_synchronized", None) is not True
            or getattr(audit, "status", "") != "Acknowledged"
            or not isinstance(ack, Mapping)
            or ack.get("status") != "Acknowledged"
            or not ack_ids
            or set(ack_ids) != set(ids)
        ):
            abort("Base reconciliation did not prove current identity/scene acknowledgement with an unaccepted candidate.")
        evidence["base"]["reconciliation"] = _result(base_reconcile)
        evidence["base"]["scene"] = {
            "audit_fingerprint": str(getattr(audit, "audit_fingerprint", "") or ""),
            "acknowledged_object_ids": list(ack_ids),
            "object_count": int(getattr(facade, "_planning_scene_object_count", 0)),
        }
        unchanged(joints_before, "after_base_reconcile")
        capture("base-reconciled-candidate-retained")

        lock_state["inject"] = False
        click(reconcile_owner, "Accept Base")
        accepted_base, accepted_details = base_review()
        if (
            getattr(accepted_base, "success", False) is not True
            or accepted_details.get("staged") is not False
            or accepted_details.get("acceptanceStatus") not in (None, "accepted")
            or accepted_details.get("candidateMatrixWorldRasMm") is not None
            or _matrix(accepted_details.get("acceptedMatrixWorldRasMm")) != base_matrix
            or not bool(getattr(facade.currentRobotState(), "base_locked", False))
            or evidence["calls"]["lockBase"] != 2
        ):
            abort("Normal GUI Base acceptance did not accept the unchanged matrix after reconciliation.")
        evidence["base"]["accepted_baseline"] = _result(accepted_base)
        evidence["base"]["lockBase_calls_through_baseline"] = evidence["calls"]["lockBase"]
        unchanged(joints_before, "after_base_baseline_accept")
        capture("base-baseline-accepted")

        home_runtime_after_base = bool(facade.taskHomeRuntimeValidated(parameter_node))
        home_before, home_before_details = home_review()
        evidence["home"].update(
            runtime_validated_before_base=home_runtime_before_base,
            runtime_validated_after_base=home_runtime_after_base,
            review_after_base=_result(home_before),
        )
        if (
            getattr(home_before, "success", False) is not True
            or home_before_details.get("identityStatus") != "current"
            or home_before_details.get("staged") is True
            or home_before_details.get("acceptanceStatus") != "accepted"
            or home_before_details.get("acceptanceUncertainty")
        ):
            evidence["home"]["pending_prerequisite"] = "Current Task Home review identity is unavailable after Base acceptance."
            abort(evidence["home"]["pending_prerequisite"], "pending_home_prerequisite")
        if home_runtime_before_base and not home_runtime_after_base:
            reaccept_home_after_base_invalidation(home_before_details)

        home_start = snapshot("before_home_review")
        accepted_home = home_start["accepted"]
        if any(
            not _full_chain._same_vector(accepted_home, home_start[field], tolerance=1.0e-12)
            for field in ("monitored", "displayed")
        ):
            abort("Accepted, monitored, and displayed J1–J5 differ before Home review.")
        saved_before = logic.taskHomeRecord(parameter_node)
        revision_before = getattr(saved_before, "revision", 0) if saved_before is not None else 0
        if isinstance(revision_before, bool) or not isinstance(revision_before, int) or revision_before < 0:
            abort("Saved Task Home revision is invalid before review.")
        expected_revision = revision_before + 1
        evidence["home"].update(
            accepted_joint_positions_si=accepted_home,
            saved_revision_before=revision_before,
            expected_saved_revision=expected_revision,
        )
        set_substep(3)
        click(panel.resetManualJogDraftButton, "Reset Draft to Accepted J1-J5")
        draft = panel.manualJogJointPositionsSi()
        if not _full_chain._same_vector(accepted_home, draft, tolerance=1.0e-12):
            abort("GUI draft reset did not preserve the exact current accepted J1–J5 pose.")
        evidence["home"]["draft_joint_positions_si"] = _full_chain._jsonable(draft)
        unchanged(home_start, "after_home_draft_reset")
        capture("home-current-pose-draft")
        set_substep(2)
        click(panel.reviewTaskHomeButton, "Review Draft as Task Home")
        staged_home, staged_home_details = home_review()
        candidate_home = staged_home_details.get("candidateJointPositionsSi")
        if (
            getattr(staged_home, "success", False) is not True
            or staged_home_details.get("identityStatus") != "current"
            or staged_home_details.get("staged") is not True
            or staged_home_details.get("acceptanceStatus") != "review"
            or not isinstance(candidate_home, Mapping)
            or not _full_chain._same_vector(accepted_home, candidate_home, tolerance=1.0e-12)
        ):
            abort("GUI Task Home review did not stage the current accepted J1–J5 pose.")
        evidence["home"]["staged_review"] = _result(staged_home)
        unchanged(home_start, "after_home_review_stage")
        capture("home-current-pose-staged")

        original_save = facade.saveTaskHome
        save_state = {"inject": True, "results": []}

        def tracked_save(*args, **kwargs):
            evidence["calls"]["saveTaskHome"] += 1
            try:
                result = original_save(*args, **kwargs)
            except Exception as exc:
                save_state["results"].append({"raised": str(exc)})
                raise
            save_state["results"].append(_result(result))
            if save_state["inject"] and getattr(result, "success", False) is True:
                save_state["inject"] = False
                raise RuntimeError(_HOME_ACK_LOST)
            return result

        patch(facade, "saveTaskHome", tracked_save)
        home_dialog = modal(panel.acceptTaskHomeButton, "Task Home", evidence["home"])
        if evidence["calls"]["saveTaskHome"] != 1:
            abort("GUI Task Home acceptance did not call saveTaskHome exactly once.")
        evidence["home"]["underlying_save_result"] = save_state["results"][-1]
        if save_state["results"][-1].get("success") is not True:
            abort("Underlying saveTaskHome failed; no acknowledgement-loss exception was injected.", "original_failure")
        home_unknown, unknown_home_details = home_review()
        failure_evidence = unknown_home_details.get("failureEvidence")
        freeze = failure_evidence.get("reconciliationFreeze") if isinstance(failure_evidence, Mapping) else None
        saved_after = logic.taskHomeRecord(parameter_node)
        saved_revision_after_lost_ack = getattr(saved_after, "revision", None)
        evidence["home"]["unknown_review"] = _result(home_unknown)
        evidence["home"]["failure_evidence"] = _full_chain._jsonable(failure_evidence)
        evidence["home"]["saved_revision_after_lost_ack"] = saved_revision_after_lost_ack
        if (
            unknown_home_details.get("acceptanceStatus") != "unknown"
            or not unknown_home_details.get("acceptanceUncertainty")
            or unknown_home_details.get("staged") is not True
            or not isinstance(unknown_home_details.get("candidateJointPositionsSi"), Mapping)
            or not _full_chain._same_vector(accepted_home, unknown_home_details["candidateJointPositionsSi"], tolerance=1.0e-12)
            or not isinstance(freeze, Mapping)
            or freeze.get("expectedRevision") != expected_revision
            or saved_revision_after_lost_ack != expected_revision
            or not isinstance(failure_evidence, Mapping)
            or _HOME_ACK_LOST not in str(failure_evidence.get("message") or "")
            or "Task Home" not in str(home_dialog.get("dialog_text") or "")
        ):
            abort("Lost Home acknowledgement did not retain unknown state, candidate, failure, and expected saved revision.")
        unchanged(home_start, "after_home_lost_ack")
        widget._updateStep6PlanningUi()
        if panel.acceptTaskHomeButton.enabled or panel.cancelTaskHomeReviewButton.enabled:
            abort("GUI Task Home repeat/cancel remained enabled while save acknowledgement was unknown.")

        original_jog = facade.guardManualRobotJog

        def count_jog(*args, **kwargs):
            evidence["calls"]["guardManualRobotJog"] += 1
            return original_jog(*args, **kwargs)

        patch(facade, "guardManualRobotJog", count_jog)
        raw_home_after_save = str(getattr(parameter_node, "step6TaskHomeJson", "") or "")
        panel.acceptTaskHomeButton.click()
        panel.cancelTaskHomeReviewButton.click()
        process_events(0.1)
        if evidence["calls"]["saveTaskHome"] != 1 or evidence["calls"]["guardManualRobotJog"] != 0:
            abort("Blocked Home repeat/cancel invoked another save or jog.")
        unchanged(home_start, "after_blocked_home_repeat_cancel")
        capture("home-unknown-retained")

        original_home_reconcile = facade.reconcileManualTaskHomeAcceptance
        home_reconcile_results = []

        def tracked_home_reconcile(*args, **kwargs):
            evidence["calls"]["reconcileManualTaskHomeAcceptance"] += 1
            result = original_home_reconcile(*args, **kwargs)
            home_reconcile_results.append(result)
            return result

        patch(facade, "reconcileManualTaskHomeAcceptance", tracked_home_reconcile)
        click(panel.reconcileTaskHomeButton, "Reconcile Task Home State")
        home_reconcile = home_reconcile_results[-1]
        home_reconcile_details = home_reconcile.details
        native = home_reconcile_details.get("nativeGuardEvidence")
        if (
            evidence["calls"]["reconcileManualTaskHomeAcceptance"] != 1
            or getattr(home_reconcile, "success", False) is not True
            or getattr(home_reconcile, "code", "") != "manual_task_home_reconciled"
            or not home_reconcile_details.get("requestId")
            or not home_reconcile_details.get("sessionId")
            or not isinstance(native, Mapping)
            or native.get("operation") != "state_query"
            or native.get("queryOnly") is not True
            or native.get("requestId") != home_reconcile_details.get("requestId")
            or native.get("sessionId") != home_reconcile_details.get("sessionId")
            or not _full_chain._same_vector(accepted_home, native.get("acceptedPositionsSi"), tolerance=1.0e-12)
            or not _full_chain._same_vector(accepted_home, home_reconcile_details.get("monitoredJointPositionsSi"), tolerance=1.0e-12)
            or home_reconcile_details.get("homeRevision") != expected_revision
            or str(getattr(parameter_node, "step6TaskHomeJson", "") or "") != raw_home_after_save
            or evidence["calls"]["saveTaskHome"] != 1
            or evidence["calls"]["guardManualRobotJog"] != 0
        ):
            abort("GUI Home reconciliation lacks correlated read-only native/monitored/revision evidence or changed saved Home.")
        reconciled_home, reconciled_details = home_review()
        saved_reconciled = logic.taskHomeRecord(parameter_node)
        if (
            getattr(reconciled_home, "success", False) is not True
            or reconciled_details.get("staged") is not False
            or reconciled_details.get("acceptanceStatus") == "unknown"
            or getattr(saved_reconciled, "revision", None) != expected_revision
        ):
            abort("Home reconciliation did not clear uncertainty without a second save.")
        evidence["home"]["reconciliation"] = _result(home_reconcile)
        evidence["home"]["reconciled_saved_revision"] = getattr(saved_reconciled, "revision", None)
        unchanged(home_start, "after_home_reconciliation")
        capture("home-reconciled")
        evidence["home"]["status"] = "reconciled"
        evidence["status"] = "probe_complete"
    except BaseHomeUncertaintyProbeError as exc:
        failure = exc
    except Exception as exc:
        evidence["status"] = "error"
        failure = BaseHomeUncertaintyProbeError(str(exc), evidence)
    finally:
        for restore in reversed(patches):
            try:
                restore()
            except Exception as exc:
                evidence.setdefault("restoration_errors", []).append(str(exc))
        if evidence.get("restoration_errors"):
            evidence["status"] = "restoration_failed"
            if failure is None:
                failure = BaseHomeUncertaintyProbeError(
                    "One or more façade monkeypatches could not be restored.", evidence
                )

    if failure is not None:
        raise BaseHomeUncertaintyProbeError(str(failure), _full_chain._jsonable(evidence)) from failure
    return _full_chain._jsonable(evidence)
