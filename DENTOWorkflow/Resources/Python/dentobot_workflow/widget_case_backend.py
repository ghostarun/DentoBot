"""Extracted case imaging and backend UI methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

import time
from collections.abc import Mapping

from .runtime import *

from DENTOROS2Bridge import clear_manual_simulation_record_paths
from DENTOStep6State import parse_manual_simulation_record
from .widget_backend_completion import BackendCompletionWidgetMixin


def _restore_saved_case_foundation_landmarks(landmarks, saved_positions) -> bool:
    """Restore exact saved RAS values after package lineage has been audited."""

    if saved_positions is None or (
        isinstance(saved_positions, (list, tuple)) and not saved_positions
    ):
        return False
    if not isinstance(saved_positions, (list, tuple)) or len(saved_positions) != 12:
        raise CaseBundleError(
            "Saved Case Foundation landmarks must contain four finite RAS points."
        )
    try:
        saved = tuple(float(value) for value in saved_positions)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CaseBundleError(
            "Saved Case Foundation landmarks must contain four finite RAS points."
        ) from exc
    if not all(math.isfinite(value) for value in saved):
        raise CaseBundleError(
            "Saved Case Foundation landmarks must contain four finite RAS points."
        )
    if landmarks is None or landmarks.GetNumberOfDefinedControlPoints() != 4:
        raise CaseBundleError(
            "The restored Case Foundation landmark set does not match the package."
        )

    current = []
    for index in range(4):
        point = [0.0, 0.0, 0.0]
        landmarks.GetNthControlPointPositionWorld(index, point)
        current.extend(float(value) for value in point)
    if (
        not all(math.isfinite(value) for value in current)
        or any(
            abs(actual - expected) > 1e-6
            or round(actual, 9) != round(expected, 9)
            for actual, expected in zip(current, saved)
        )
    ):
        raise CaseBundleError(
            "The restored Case Foundation landmarks materially differ from the package."
        )

    for index in range(4):
        landmarks.SetNthControlPointPositionWorld(
            index, *saved[index * 3:index * 3 + 3]
        )
    return True


class CaseBackendWidgetMixin(BackendCompletionWidgetMixin):
    def onOpenCaseLibrary(self, checked=False):
        if self._caseLibraryDialog is not None:
            if self._caseLibraryDialog._case_library_closed:
                self._caseLibraryDialog.dialog.deleteLater()
            elif self._caseLibraryDialog.dialog.visible:
                self._caseLibraryDialog.dialog.raise_()
                return
        from .case_library import show_case_library
        database = Path.home() / ".dentobot" / "DentoCase" / "catalog.sqlite"
        database.parent.mkdir(parents=True, exist_ok=True)
        self._caseLibraryDialog = show_case_library(
            slicer.util.mainWindow(), database_path=str(database),
            on_full_load=self._openLibraryFullCase,
            on_partial_load=self._openLibraryPartialCase,
            on_partial_save=self._saveLibraryPartialCase,
        )

    def _openLibraryFullCase(self, path):
        inspection = self._openCaseBundle(path)
        self._showCaseManualSimulationRecords(inspection)
        self.ui.caseBundleStatusLabel.text = "Loaded case; live freshness requires workflow review."

    def _saveLibraryPartialCase(self, path, target, checkpoint, branch, destination):
        from .case_projection import project_package_offline
        with slicer.util.tryWithErrorDisplay("Could not create the independent partial case."):
            project_package_offline(path, destination, target, checkpoint, branch)
            self.ui.caseBundleStatusLabel.text = "Saved independent partial case; active scene unchanged."

    def _openLibraryPartialCase(self, path, target, checkpoint, branch):
        from .case_projection import project_package_offline
        with slicer.util.tryWithErrorDisplay("Could not load the independent partial case."):
            with tempfile.TemporaryDirectory(prefix="dentocase-partial-load-", dir=slicer.app.temporaryPath) as directory:
                destination = Path(directory) / "independent.dentocase"
                project_package_offline(path, destination, target, checkpoint, branch)
                self._openCaseBundle(destination)
            self._loadedCaseBundlePath = ""
            slicer.mrmlScene.SetURL("")
            slicer.mrmlScene.Modified()
            self.ui.caseBundleStatusLabel.text = "Independent partial case loaded; use Save Case Package (Save As). Live freshness is unverified."

    def _setMetadataPlaceholders(self) -> None:
        for label in (
            self.ui.volumeNameValueLabel,
            self.ui.dimensionsValueLabel,
            self.ui.spacingValueLabel,
            self.ui.scalarTypeValueLabel,
            self.ui.scalarRangeValueLabel,
            self.ui.orientationValueLabel,
            self.ui.geometryStatusValueLabel,
        ):
            label.text = _("--")

    def _showVolumeInSliceViews(self, volumeNode: vtkMRMLScalarVolumeNode) -> None:
        slicer.util.setSliceViewerLayers(background=volumeNode, fit=True)
        self._lastDisplayedVolumeId = volumeNode.GetID()

    def onShowSelectedVolume(self) -> None:
        if not self._parameterNode or not self._parameterNode.inspectedVolume:
            return
        with slicer.util.tryWithErrorDisplay(_("Could not display the selected volume.")):
            self._showVolumeInSliceViews(self._parameterNode.inspectedVolume)

    def onInputVolumeSelectionChanged(self, volumeNode) -> None:
        """Keep the visible selector authoritative and persist its exact node."""

        if not self._parameterNode:
            return
        self.selectInspectionContext(volumeNode)

    def onOpenDicomBrowser(self) -> None:
        if not self.logic:
            return
        self._volumeNodeIdsBeforeDICOM = {
            node.GetID() for node in self.logic.getScalarVolumeNodes()
        }
        self.ui.statusLabel.text = _(
            "Opening Slicer's DICOM browser. Load a series, then return to DENTO Workflow."
        )
        slicer.util.selectModule("DICOM")

    @staticmethod
    def _sceneLocationState() -> dict[str, object]:
        scene = slicer.mrmlScene
        modified = getattr(scene, "GetModifiedSinceRead", lambda: False)()
        return {
            "url": scene.GetURL() or "",
            "rootDirectory": scene.GetRootDirectory() or "",
            "modifiedSinceRead": bool(modified),
        }

    @staticmethod
    def _restoreSceneLocationState(state: dict[str, object]) -> None:
        scene = slicer.mrmlScene
        scene.SetURL(str(state.get("url") or ""))
        scene.SetRootDirectory(str(state.get("rootDirectory") or ""))
        setter = getattr(scene, "SetModifiedSinceRead", None)
        if setter:
            setter(bool(state.get("modifiedSinceRead", False)))

    def _saveSceneSnapshotToMrb(self, scenePath: str | Path) -> None:
        """Save a sanitized MRB without retaining the temporary scene location."""

        locationState = self._sceneLocationState()
        # Stage-exclusive lock/selectability changes are application-local UI
        # policy.  Persist the intrinsic node state and rebuild the temporary
        # restrictions after saving (or after the enclosing restore).
        self._restoreStageExclusiveInteractionLocks()
        mark_slicer_ros2_runtime_nodes_transient()
        resumeRos2ActiveNodeIds = (
            self._suspendRos2MotionActiveAttributesForSave()
        )
        try:
            if not slicer.util.saveScene(str(scenePath)):
                raise CaseBundleError(_("Slicer could not create the MRB snapshot."))
        finally:
            try:
                self._restoreSceneLocationState(locationState)
            finally:
                self._restoreRos2MotionActiveAttributesAfterSave(
                    resumeRos2ActiveNodeIds
                )
                if self._caseBundleRestoreDepth == 0 and self._parameterNode:
                    self._updateStageExclusiveInteractionLocks(
                        int(self.ui.workflowStageComboBox.currentIndex)
                    )

    def _caseManualSimulationRecords(self) -> tuple[dict[str, object], ...]:
        """Capture validated historical Step 6 evidence without live-state reads."""

        facade = getattr(self, "_robotWorkflowFacade", None)
        if facade is None:
            raise CaseBundleError(
                _("Could not save the case because the Step 6 recording façade is unavailable.")
            )
        try:
            completed = facade.manualSimulationCompletedRecords()
            if not isinstance(completed, (tuple, list)):
                raise ValueError(
                    "The façade returned an invalid completed-record collection."
                )
            records = []
            fingerprints = set()
            for record in completed:
                if not isinstance(record, Mapping):
                    raise ValueError(
                        "The façade returned an invalid manual simulation record."
                    )
                parsed = parse_manual_simulation_record(record)
                fingerprint = parsed["record_fingerprint"]
                if fingerprint not in fingerprints:
                    records.append(parsed)
                    fingerprints.add(fingerprint)
            try:
                active = facade.manualSimulationRecord()
            except RuntimeError as exc:
                if not completed and str(exc).startswith(
                    "Manual simulation recording is unavailable: no event-bearing "
                ):
                    return tuple(records)
                raise
            if not isinstance(active, Mapping):
                raise ValueError(
                    "The façade returned an invalid manual simulation record."
                )
            parsed = parse_manual_simulation_record(active)
            if parsed["record_fingerprint"] not in fingerprints:
                records.append(parsed)
            return tuple(records)
        except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError) as exc:
            raise CaseBundleError(
                _("Could not validate manual simulation records for the case: %1").replace(
                    "%1", str(exc)
                )
            ) from exc

    def _showCaseManualSimulationRecords(self, inspection) -> None:
        """Replace prior historical selection only after a case passed its load audit."""

        panel = getattr(self, "_robotSimulationPanel", None)
        if panel:
            panel.clearManualSimulationRecords()
        try:
            clear_manual_simulation_record_paths()
        except Exception as exc:
            message = (
                "The case loaded, but historical manual simulation paths could not "
                "be cleared, so its records were not displayed: " + str(exc)
            )
            if panel:
                panel.setManualRecordImportStatus("error", message)
            slicer.util.errorDisplay(message)
            return
        if not panel:
            return
        records = tuple(inspection.manual_simulation_records)
        if records:
            panel.setManualSimulationRecords(records)
            panel.setManualRecordImportStatus(
                "ok",
                f"Loaded {len(records)} historical/display-only manual simulation "
                "record(s) from this case. Live robot state was not read or changed.",
            )
        else:
            panel.setManualRecordImportStatus(
                "idle",
                "This case contains no historical manual simulation records.",
            )

    def _createCaseBundle(self, destination: str | Path):
        if not self._parameterNode or not self.logic:
            raise CaseBundleError(_("DENTOBOT workflow state is unavailable."))
        if not self._parameterNode.dentoCaseId:
            self._parameterNode.dentoCaseId = str(uuid.uuid4())
        manualSimulationRecords = self._caseManualSimulationRecords()
        cancelledPlacement = (
            self.logic.cancelTransientStep6CaseJawLandmarkPlacement(
                self._parameterNode
            )
        )
        if cancelledPlacement.get("cancelled"):
            logging.warning(
                "Cancelled transient Case Foundation landmark placement before case save; "
                "defined points were retained without silent provenance promotion"
            )
        self._enforceStep6OpenedJawDisplaySeparation()
        self._restoreStageExclusiveInteractionLocks()
        try:
            currentStage = int(self.ui.workflowStageComboBox.currentIndex)
            if currentStage > 0 or int(self._parameterNode.workflowStageIndex) < 0:
                self._parameterNode.workflowStageIndex = currentStage
            self.logic.prepareDentoCaseSchema2ForSave(self._parameterNode)
            # Capture lineage while Markups carry the same intrinsic
            # interaction state that will be serialized into the MRB.
            workflowSummary = self.logic.caseBundleWorkflowSummary(
                self._parameterNode
            )
            from .case_inventory import capture_inventory
            workflowSummary["caseIdentity"] = {"id": self._parameterNode.dentoCaseId}
            with tempfile.TemporaryDirectory(
                prefix="dentobot-case-save-",
                dir=slicer.app.temporaryPath,
            ) as temporaryDirectory:
                scenePath = Path(temporaryDirectory) / "case.mrb"
                self._saveSceneSnapshotToMrb(scenePath)
                # Saving may create persistent storage nodes. Audit the exact
                # scene inventory serialized by that snapshot.
                inventory, ownership = capture_inventory(
                    self._parameterNode, slicer.mrmlScene, workflowSummary
                )
                workflowSummary["checkpointInventory"] = inventory
                workflowSummary["projectionOwnership"] = ownership
                return create_case_bundle(
                    destination,
                    scenePath,
                    case_label=self._parameterNode.caseName,
                    workflow=workflowSummary,
                    robot_profile=self.logic.caseBundleRobotProfile(),
                    manual_simulation_records=manualSimulationRecords,
                    application={
                        "name": "DENTOBOT",
                        "module": "DENTOWorkflow",
                        "slicerVersion": str(
                            getattr(slicer.app, "applicationVersion", "unknown")
                        ),
                    },
                )
        finally:
            if self._caseBundleRestoreDepth == 0 and self._parameterNode:
                self._updateStageExclusiveInteractionLocks(
                    int(self.ui.workflowStageComboBox.currentIndex)
                )

    @staticmethod
    def _caseBundleSuggestedStem(caseName: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", caseName.strip())
        return normalized.strip("._-") or "dentobot-case"

    def onSaveCaseBundle(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        suggested = self._caseBundleSuggestedStem(self._parameterNode.caseName)
        destination = qt.QFileDialog.getSaveFileName(
            slicer.util.mainWindow(),
            _("Save DENTOBOT case package"),
            f"{suggested}{CASE_BUNDLE_EXTENSION}",
            _("DENTOBOT case package (*.dentocase)"),
        )
        if isinstance(destination, tuple):
            destination = destination[0]
        if not destination:
            return
        inspection = None
        with slicer.util.tryWithErrorDisplay(
            _("Could not save the DENTOBOT case package."),
            waitCursor=True,
        ):
            inspection = self._createCaseBundle(destination)
        if inspection is None:
            return
        self._loadedCaseBundlePath = str(inspection.path)
        self._caseBundleRobotProfileCompatible = True
        foundation = self.logic.evaluateCaseFoundationEligibility(
            self._parameterNode
        )
        registry = self.logic.syncDentoCaseTrajectoryRegistry(
            self._parameterNode
        )
        foundationOnly = bool(
            foundation["pose"]["eligible"]
            and foundation["base"]["eligible"]
            and not registry["prepared_branches"]
        )
        packageIssues = self.logic.step6PlanningPackageFreshnessIssues(
            self._parameterNode
        )
        jawIssues = self.logic.step6CaseJawOpeningFreshnessIssues(
            self._parameterNode
        )
        if foundationOnly:
            self.ui.caseBundleStatusLabel.text = _(
                "Saved valid foundation-only case %1 with its reviewed base. "
                "No PreparedBranch or ROS runtime was included."
            ).replace("%1", inspection.path.name)
            self.ui.caseBundleStatusLabel.styleSheet = "color: #207227;"
        elif packageIssues:
            self.ui.caseBundleStatusLabel.text = _(
                "Saved and integrity-checked %1 with ROS excluded. Step 6 is "
                "blocked by upstream package state: %2"
            ).replace("%1", inspection.path.name).replace(
                "%2", " ".join(packageIssues)
            )
            self.ui.caseBundleStatusLabel.styleSheet = "color: #9a6500;"
        elif jawIssues:
            self.ui.caseBundleStatusLabel.text = _(
                "Saved and integrity-checked %1 with ROS excluded. The Steps "
                "Case anatomy restored; complete the Case Foundation before Step 4A: %2"
            ).replace("%1", inspection.path.name).replace(
                "%2", " ".join(jawIssues)
            )
            self.ui.caseBundleStatusLabel.styleSheet = "color: #9a6500;"
        else:
            self.ui.caseBundleStatusLabel.text = _(
                "Saved integrity-checked package: %1. ROS runtime state was excluded."
            ).replace("%1", inspection.path.name)
            self.ui.caseBundleStatusLabel.styleSheet = "color: #207227;"

    def _beginCaseBundleRestore(self) -> int:
        self._restoreStageExclusiveInteractionLocks()
        self._caseBundleRestoreDepth += 1
        self._caseBundleRestoreGeneration += 1
        return self._caseBundleRestoreGeneration

    def _endCaseBundleRestore(self, generation: int) -> None:
        if generation != self._caseBundleRestoreGeneration:
            logging.warning(
                "Ignored an obsolete DENTOBOT case-restore generation %d",
                generation,
            )
            return
        self._caseBundleRestoreDepth = max(
            0,
            self._caseBundleRestoreDepth - 1,
        )
        if self._caseBundleRestoreDepth == 0 and self._parameterNode:
            self._updateStageExclusiveInteractionLocks(
                int(self.ui.workflowStageComboBox.currentIndex)
            )

    def _bindAndValidateRestoredCase(
        self,
        expectedWorkflow: dict[str, object],
        phase=None,
    ) -> None:
        """Validate restored MRML before normal GUI hydration can mutate it."""

        parameterNode = self.logic.getParameterNode()
        identity = expectedWorkflow.get("caseIdentity", {}).get("id", "")
        if identity and parameterNode.dentoCaseId != identity:
            raise CaseBundleError("The restored case identity differs from the package.")
        try:
            self.logic.validateLoadedCaseBundleWorkflow(
                parameterNode,
                expectedWorkflow,
            )
        except CaseBundleError as exc:
            raise CaseBundleError(
                _("Pre-bind package validation failed: %1").replace(
                    "%1", str(exc)
                )
            ) from exc
        if phase:
            phase("Restoring markup and jaw display state", can_cancel=False)
        self._restoreCaseBundleMarkupInteractionState(
            parameterNode,
            expectedWorkflow,
        )
        if str(parameterNode.step6CaseJawPreparationMode) == "CaseFoundationCurrent":
            self.logic.rebuildCaseFoundationDisplayVolumes(parameterNode)
        if phase:
            phase("Checking restored jaw display", can_cancel=False)
        try:
            self.logic.validateLoadedCaseBundleWorkflow(
                parameterNode,
                expectedWorkflow,
            )
        except CaseBundleError as exc:
            raise CaseBundleError(
                _("Post-bind package validation failed: %1").replace(
                    "%1", str(exc)
                )
            ) from exc

    def _validateHydratedCaseBundle(
        self,
        expectedWorkflow: dict[str, object],
    ) -> None:
        """Audit package lineage again after GUI hydration and event delivery."""

        try:
            self.logic.validateLoadedCaseBundleWorkflow(
                self.logic.getParameterNode(),
                expectedWorkflow,
                allowDerivedEnvironmentMismatch=True,
            )
        except CaseBundleError as exc:
            raise CaseBundleError(
                _("Post-hydration package validation failed: %1").replace(
                    "%1", str(exc)
                )
            ) from exc

    @staticmethod
    def _restoreCaseBundleMarkupInteractionState(
        parameterNode,
        expectedWorkflow: dict[str, object],
    ) -> None:
        """Restore intrinsic Markups edit state before stage policy is applied."""

        for record in expectedWorkflow.get("nodes", []):
            if not isinstance(record, dict):
                continue
            fieldName = str(record.get("field") or "")
            node = getattr(parameterNode, fieldName, None)
            if node is None or not node.IsA("vtkMRMLMarkupsNode"):
                continue
            if "locked" in record:
                node.SetLocked(bool(record["locked"]))
            # Schema-V1 packages before this field was introduced contain
            # ordinary selectable workflow Markups. Stage ownership may then
            # temporarily make them non-selectable after validation.
            if "selectable" in record:
                node.SetSelectable(bool(record["selectable"]))
            elif (
                node.GetAttribute("DENTOBOT.MarkupsRole")
                == "TemplateInsertionDirection"
            ):
                # Older schema-V1 lineage omitted selectability, but this
                # generated construction axis is intrinsically read-only.
                node.SetSelectable(False)
            else:
                node.SetSelectable(True)

    def _openCaseBundle(self, bundlePath: str | Path, progress=None):
        if not self.logic:
            raise CaseBundleError(_("DENTOBOT workflow logic is unavailable."))
        started = time.monotonic()
        lastPhase = started

        def phase(message, *, can_cancel=True):
            nonlocal lastPhase
            now = time.monotonic()
            logging.info("DENTOBOT case load phase %.3fs total %.3fs: %s", now - lastPhase, now - started, message)
            print("DENTOBOT_CASE_LOAD_PHASE", f"{now - lastPhase:.3f}", f"{now - started:.3f}", message, flush=True)
            lastPhase = now
            if progress:
                progress.update(message, can_cancel=can_cancel)

        self._caseBundleRobotProfileMigrationMessage = ""
        phase("Checking package integrity")
        from DENTOCaseBundle import PreparedCaseBundle, prepare_case_bundle
        prepared = bundlePath if isinstance(bundlePath, PreparedCaseBundle) else prepare_case_bundle(bundlePath)
        prepared.assert_source_unchanged()
        inspection = prepared.inspection
        profileMigration = {
            "compatible": False,
            "migrated": False,
            "message": "",
        }
        recoveryLocationState = self._sceneLocationState()
        restoreGeneration = self._beginCaseBundleRestore()
        renderPaused = False
        priorMetricsCache = getattr(self.logic, "_caseBundleMetricsDigestCache", None)
        self.logic._caseBundleMetricsDigestCache = {}
        try:
            # Render the completed restore once; queued events and every lineage
            # audit still run on the owning thread under the restore barrier.
            slicer.app.pauseRender()
            renderPaused = True
            with tempfile.TemporaryDirectory(
                prefix="dentobot-case-open-",
                dir=slicer.app.temporaryPath,
            ) as temporaryDirectory:
                temporaryRoot = Path(temporaryDirectory)
                prepared.assert_source_unchanged()
                scenePath = prepared.scene_path
                phase("Saving recovery snapshot", can_cancel=False)
                recoveryPath = temporaryRoot / "recovery.mrb"
                self._saveSceneSnapshotToMrb(recoveryPath)
                try:
                    prepared.assert_source_unchanged()
                    phase("Importing Slicer scene", can_cancel=False)
                    if not slicer.util.loadScene(
                        str(scenePath), {"clear": True}
                    ):
                        raise CaseBundleError(
                            _("Slicer could not replace the scene from the package.")
                        )
                    phase("Validating imported scene", can_cancel=False)
                    self._bindAndValidateRestoredCase(inspection.workflow, phase=phase)
                    phase("Binding restored workflow", can_cancel=False)
                except Exception as loadError:
                    logging.exception(
                        "DENTOBOT case-package load failed; restoring recovery scene"
                    )
                    recoveryError = ""
                    try:
                        if not slicer.util.loadScene(
                            str(recoveryPath), {"clear": True}
                        ):
                            recoveryError = _(" Recovery scene restoration failed.")
                        recoveredParameterNode = self.logic.getParameterNode()
                        if (
                            str(recoveredParameterNode.step6CaseJawPreparationMode)
                            == "CaseFoundationCurrent"
                        ):
                            self.logic.rebuildCaseFoundationDisplayVolumes(
                                recoveredParameterNode
                            )
                        self.setParameterNode(recoveredParameterNode)
                        slicer.app.processEvents()
                        self._restoreSceneLocationState(recoveryLocationState)
                    except Exception as exc:
                        recoveryError = _(
                            " Recovery scene restoration failed: %1"
                        ).replace("%1", str(exc))
                    raise CaseBundleError(
                        f"{loadError}{recoveryError}"
                    ) from loadError
                # Compatibility migrations and Step 6 freshness review are
                # allowed only after package integrity has passed, and the
                # recovery MRB must remain available until that audit passes.
                # Keep the restore barrier through binding, queued UI events,
                # hydration, and post-hydration identity validation.
                try:
                    self.setParameterNode(self.logic.getParameterNode())
                    slicer.app.processEvents()
                    phase("Hydrating saved workflow", can_cancel=False)
                    self.logic.hydrateDentoCaseStateAfterLoad(
                        self._parameterNode,
                        str(self._parameterNode.dentoCaseSchemaVersion or inspection.manifest.get("schemaVersion") or ""),
                    )
                    phase("Updating restored workflow controls", can_cancel=False)
                    wasUpdating = self._updatingFromParameterNode
                    self._updatingFromParameterNode = True
                    try:
                        # _updatePlanning observes the restore barrier and
                        # reports saved ROI bounds without regenerating them.
                        self._updateFromParameterNodeOnce()
                    finally:
                        self._updatingFromParameterNode = wasUpdating
                    phase("Delivering restored scene events", can_cancel=False)
                    slicer.app.processEvents()
                    phase("Validating hydrated case", can_cancel=False)
                    self._validateHydratedCaseBundle(inspection.workflow)
                    profileMigration = (
                        self.logic._migrateLegacyJ2ZeroRobotProfile(
                            self.logic.getParameterNode(),
                            inspection.robot_profile,
                        )
                    )
                    step6Workflow = inspection.workflow.get("step6")
                    environment = (
                        step6Workflow.get("environment")
                        if isinstance(step6Workflow, dict) else None
                    )
                    if isinstance(environment, dict):
                        try:
                            parse_robot_environment_snapshot(environment)
                        except (TypeError, ValueError, OverflowError):
                            logging.warning(
                                "Ignoring invalid saved Step 6 environment after hydration audit"
                            )
                            environment = {}
                        else:
                            self._parameterNode.step6EnvironmentJson = canonical_json(
                                environment
                            )
                    else:
                        environment = {}
                    # Restore validated precise MRML state only after strict
                    # package audits and exact pose-fingerprint agreement.
                    transform = self._parameterNode.step6CaseJawTransform
                    values = environment.get("jaw_transform_matrix", [])
                    if (
                        transform
                        and self._parameterNode.step6CaseJawPreparationMode == "CaseFoundationCurrent"
                        and transform.GetAttribute("DENTOBOT.GeometryState") == "Current"
                        and len(values) == 16
                        and environment.get("planning_pose_fingerprint")
                        == transform.GetAttribute("DENTOBOT.PlanningPoseFingerprint")
                    ):
                        matrix = vtk.vtkMatrix4x4()
                        transform.GetMatrixTransformToParent(matrix)
                        if all(
                            abs(matrix.GetElement(row, col) - float(f"{float(values[row * 4 + col]):.6g}")) < 1e-8
                            for row in range(4) for col in range(4)
                        ):
                            for row in range(4):
                                for col in range(4):
                                    matrix.SetElement(row, col, float(values[row * 4 + col]))
                            transform.SetMatrixTransformToParent(matrix)
                            savedLandmarks = environment.get(
                                "landmark_positions_ras_mm"
                            )
                            if savedLandmarks not in (None, [], ()):
                                landmarks = self._parameterNode.step6CaseJawLandmarks
                                if not self.logic.isStep6CaseJawLandmarksNode(landmarks):
                                    raise CaseBundleError(
                                        _("The restored Case Foundation landmarks do not match the package.")
                                    )
                                _restore_saved_case_foundation_landmarks(
                                    landmarks, savedLandmarks
                                )
                    self._revalidateImportedStep6ContextAfterLoad()
                    phase("Revalidating restored planning context", can_cancel=False)
                    savedStage = int(self._parameterNode.workflowStageIndex)
                    if savedStage < 0 and self._parameterNode.step6MotionDiagnosticJson:
                        # Older packages did not persist navigation; a saved
                        # motion diagnostic proves the operator reached Step 6.
                        savedStage = len(self._workflowStageEntries()) - 1
                    if savedStage >= 0:
                        self._setWorkflowStage(savedStage, ensureVisible=False)
                        phase("Restoring workflow stage", can_cancel=False)
                        if (
                            savedStage in {3, len(self._workflowStageEntries()) - 1}
                            and not self.logic.step6CaseJawOpeningFreshnessIssues(self._parameterNode)
                        ):
                            self._applyWorkflowViewPreset("recommended", updateStatus=False)
                            phase("Restoring recommended view", can_cancel=False)
                    self._enforceStep6OpenedJawDisplaySeparation()
                    prepared.assert_source_unchanged()
                    phase("Finalizing jaw display", can_cancel=False)
                except Exception as hydrationError:
                    logging.exception(
                        "DENTOBOT post-hydration package audit failed; "
                        "restoring recovery scene"
                    )
                    recoveryError = ""
                    try:
                        if not slicer.util.loadScene(
                            str(recoveryPath), {"clear": True}
                        ):
                            recoveryError = _(
                                " Recovery scene restoration failed."
                            )
                        recoveredParameterNode = self.logic.getParameterNode()
                        if (
                            str(recoveredParameterNode.step6CaseJawPreparationMode)
                            == "CaseFoundationCurrent"
                        ):
                            self.logic.rebuildCaseFoundationDisplayVolumes(
                                recoveredParameterNode
                            )
                        self.setParameterNode(recoveredParameterNode)
                        slicer.app.processEvents()
                        self._restoreSceneLocationState(recoveryLocationState)
                    except Exception as exc:
                        recoveryError = _(
                            " Recovery scene restoration failed: %1"
                        ).replace("%1", str(exc))
                    raise CaseBundleError(
                        f"{hydrationError}{recoveryError}"
                    ) from hydrationError
        finally:
            try:
                self.logic._caseBundleMetricsDigestCache = priorMetricsCache
                prepared.close()
                self._endCaseBundleRestore(restoreGeneration)
            finally:
                if renderPaused:
                    slicer.app.resumeRender()

        # The extracted MRB is deleted with the temporary directory. Do not
        # leave it as Slicer's apparent save target, and do not use the outer
        # .dentocase path as an MRML target because Ctrl+S could overwrite it.
        self._restoreSceneLocationState(
            {
                "url": "",
                "rootDirectory": str(inspection.path.parent),
                "modifiedSinceRead": False,
            }
        )

        currentRobotProfile = self.logic.caseBundleRobotProfile()
        self._caseBundleRobotProfileCompatible = (
            currentRobotProfile.get("identitySha256")
            == inspection.robot_profile.get("identitySha256")
            or bool(profileMigration.get("compatible"))
        )
        self._caseBundleRobotProfileMigrationMessage = str(
            profileMigration.get("message") or ""
        )
        self._parameterNode.dentoCaseId = str(
            inspection.workflow.get("caseIdentity", {}).get("id") or uuid.uuid4()
        )
        self._loadedCaseBundlePath = str(inspection.path)
        phase("Case loaded", can_cancel=False)
        return inspection

    def onOpenCaseBundle(self, checked: bool = False) -> None:
        del checked
        bundlePath = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(),
            _("Open DENTOBOT case package"),
            "",
            _("DENTOBOT case package (*.dentocase)"),
        )
        if isinstance(bundlePath, tuple):
            bundlePath = bundlePath[0]
        if not bundlePath:
            return
        if not slicer.util.confirmYesNoDisplay(
            "Replace the current scene with the selected case? Unsaved changes will be lost.",
            windowTitle="Open DentoCase",
        ):
            return
        inspection = None
        from .workflow_progress import WorkflowProgress, WorkflowCancelled

        progress = WorkflowProgress("Opening DENTOBOT case")
        try:
            with slicer.util.tryWithErrorDisplay(
                _("Could not open the selected DENTOBOT case package."),
                waitCursor=True,
            ):
                try:
                    inspection = self._openCaseBundle(bundlePath, progress=progress)
                except WorkflowCancelled:
                    return
        finally:
            progress.close()
        if inspection is None:
            return
        self._showCaseManualSimulationRecords(inspection)
        foundation = self.logic.evaluateCaseFoundationEligibility(
            self._parameterNode
        )
        registry = self.logic.syncDentoCaseTrajectoryRegistry(
            self._parameterNode
        )
        imported = self.logic.importResearchStep6WorkingConfigurations(self._parameterNode)
        if imported:
            logging.info(
                "Adopted research Step 6 working configurations for %s", ", ".join(imported)
            )
        foundationOnly = bool(
            foundation["pose"]["eligible"]
            and foundation["base"]["eligible"]
            and not registry["prepared_branches"]
        )
        packageIssues = self.logic.step6PlanningPackageFreshnessIssues(
            self._parameterNode
        )
        jawIssues = self.logic.step6CaseJawOpeningFreshnessIssues(
            self._parameterNode
        )
        if not self._caseBundleRobotProfileCompatible:
            message = _(
                "Loaded %1, but the installed robot description differs from the "
                "saved fingerprint. Step 6 import is blocked until reconciled."
            ).replace("%1", inspection.path.name)
            color = "#9a6500"
        elif foundationOnly:
            message = _(
                "Loaded valid foundation-only case %1 offline. Case Foundation "
                "and reviewed base are ready; complete Steps 4A–5C before "
                "activating a PreparedBranch."
            ).replace("%1", inspection.path.name)
            color = "#207227"
        elif packageIssues:
            message = _(
                "Loaded and integrity-checked %1 with ROS disconnected. Step 6 "
                "is blocked by upstream package state: %2"
            ).replace("%1", inspection.path.name).replace(
                "%2", " ".join(packageIssues)
            )
            color = "#9a6500"
        elif jawIssues:
            message = _(
                "Loaded and integrity-checked %1 with ROS disconnected. The "
                "Case anatomy is active; complete the Case Foundation before Step 4A: %2"
            ).replace("%1", inspection.path.name).replace(
                "%2", " ".join(jawIssues)
            )
            color = "#9a6500"
        else:
            message = _(
                "Loaded and verified %1. ROS remains disconnected until explicit runtime activation."
            ).replace("%1", inspection.path.name)
            color = "#207227"
        message += _(
            " All Steps 1–6 remain selectable; use the stage/workspace picker "
            "to inspect or continue from any saved checkpoint. Each step's "
            "actions still validate their own prerequisites."
        )
        if self._caseBundleRobotProfileMigrationMessage:
            message += " " + self._caseBundleRobotProfileMigrationMessage
        self.ui.caseBundleStatusLabel.text = message
        self.ui.caseBundleStatusLabel.styleSheet = f"color: {color};"
        self.ui.workflowStageComboBox.enabled = True
        self._updateWorkflowNavigationButtons()
    def _setCaseBundleResumeStatus(self, message: str, *, error: bool) -> None:
        if not hasattr(self, "ui") or not getattr(self.ui, "caseBundleStatusLabel", None):
            return
        self.ui.caseBundleStatusLabel.text = message
        self.ui.caseBundleStatusLabel.styleSheet = (
            "color: #b00020;" if error else "color: #207227;"
        )

    def onOpenScene(self) -> None:
        scenePath = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(),
            _("Open DENTOBOT scene"),
            "",
            _("Slicer scene or bundle (*.mrml *.mrb);;All files (*)"),
        )
        if isinstance(scenePath, tuple):
            scenePath = scenePath[0]
        if not scenePath:
            return

        with slicer.util.tryWithErrorDisplay(_("Could not open the selected DENTOBOT scene."), waitCursor=True):
            if not slicer.util.loadScene(scenePath, {"clear": True}):
                raise RuntimeError(_("Slicer did not replace the active scene."))
        self._loadedCaseBundlePath = ""
        self._caseBundleRobotProfileCompatible = None
        self._caseBundleRobotProfileMigrationMessage = ""
        self.ui.caseBundleStatusLabel.text = _(
            "Loaded a legacy MRML/MRB without DENTOBOT package integrity metadata."
        )
        self.ui.caseBundleStatusLabel.styleSheet = "color: #9a6500;"

    def onNewCase(self) -> None:
        confirmed = slicer.util.confirmYesNoDisplay(
            _(
                "This removes all nodes from the current Slicer scene. "
                "Original DICOM files on disk are not modified. Save the current scene first if needed."
            ),
            windowTitle=_("Start a new DENTOBOT case?"),
        )
        if not confirmed:
            return

        self._pendingFreshCaseReset = True
        slicer.mrmlScene.Clear(0)
        self._loadedCaseBundlePath = ""
        self._caseBundleRobotProfileCompatible = None
        self._caseBundleRobotProfileMigrationMessage = ""
        self.ui.caseBundleStatusLabel.text = _(
            "New empty case. Use Save Case Package for integrity-checked persistence."
        )
        self.ui.caseBundleStatusLabel.styleSheet = ""
        logging.info("Started a new empty DENTOBOT scene")

    def _backendConfiguration(self) -> tuple[str, str, str, str, str]:
        if not self._parameterNode:
            return "", "", "", "", ""
        return self.logic.resolveBackendConfiguration(
            default_execution_mode(os.name),
            self._parameterNode.wslDistribution.strip(),
            self._parameterNode.wslPythonPath.strip(),
            self._parameterNode.stagingRoot.strip(),
            self._parameterNode.inferenceDevice.strip(),
            self._parameterNode.useLauncherBackendConfiguration,
        )

    def onUseLauncherBackendConfigurationToggled(self, enabled: bool) -> None:
        if not self._parameterNode:
            return
        if self._parameterNode.useLauncherBackendConfiguration != bool(enabled):
            self._parameterNode.useLauncherBackendConfiguration = bool(enabled)
        self._updateBackendControls()

    def _backendIsRunning(self) -> bool:
        return self._backendProcess is not None

    def _updateBackendControls(self) -> None:
        if not self._parameterNode:
            return
        executionMode, distribution, pythonPath, stagingRoot, _device = (
            self._backendConfiguration()
        )
        (
            launcherMode,
            launcherDistribution,
            launcherPython,
            launcherArtifactRoot,
            launcherDevice,
        ) = (
            self.logic.launcherBackendConfiguration()
        )
        launcherRequested = bool(
            self._parameterNode.useLauncherBackendConfiguration
        )
        launcherAvailable = self.logic.launcherBackendConfigurationIsComplete(
            launcherMode,
            launcherDistribution,
            launcherPython,
            launcherArtifactRoot,
            launcherDevice,
        )
        launcherActive = launcherRequested and launcherAvailable
        self.ui.wslDistributionLineEdit.enabled = not launcherRequested
        self.ui.wslPythonPathLineEdit.enabled = not launcherRequested
        self.ui.stagingRootLineEdit.enabled = not launcherRequested
        self.ui.wslDistributionLabel.visible = bool(
            os.name == "nt" and not launcherRequested
        )
        self.ui.wslDistributionLineEdit.visible = bool(
            os.name == "nt" and not launcherRequested
        )
        self.ui.wslPythonPathLabel.visible = not launcherRequested
        self.ui.wslPythonPathLineEdit.visible = not launcherRequested
        self.ui.stagingRootLabel.visible = not launcherRequested
        self.ui.stagingRootLineEdit.visible = not launcherRequested
        if launcherActive:
            self.ui.backendConfigurationSummaryLabel.text = _(
                "Managed automatically by the DENTOBOT launcher.\n"
                "Adapter: %1%2\nBackend Python: %3\nRun records: %4\nDevice: %5"
            ).replace("%1", launcherMode).replace(
                "%2",
                f" ({launcherDistribution})" if launcherDistribution else "",
            ).replace("%3", launcherPython).replace(
                "%4", launcherArtifactRoot
            ).replace("%5", launcherDevice)
            self.ui.backendConfigurationSummaryLabel.styleSheet = (
                "color: #207227;"
            )
        elif launcherRequested:
            self.ui.backendConfigurationSummaryLabel.text = _(
                "A complete launcher configuration was not found. Start "
                "Slicer with launch-dentoworkflow.bash on Linux or "
                "launch-dentoworkflow.ps1 on Windows, or disable automatic "
                "configuration and enter the advanced overrides below."
            )
            self.ui.backendConfigurationSummaryLabel.styleSheet = (
                "color: #b00020;"
            )
        else:
            self.ui.backendConfigurationSummaryLabel.text = _(
                "Advanced manual override is active. These machine-specific "
                "paths are stored with the scene."
            )
            self.ui.backendConfigurationSummaryLabel.styleSheet = (
                "color: #b36b00;"
            )
        configured = bool(
            not (launcherRequested and not launcherAvailable)
            and pythonPath
            and (executionMode == "local" or distribution)
        )
        running = self._backendIsRunning()
        self.ui.checkBackendButton.enabled = configured and not running
        self.ui.roundTripButton.enabled = bool(
            configured
            and stagingRoot
            and self._parameterNode.inspectedVolume
            and not running
        )
        self.ui.segmentTeethButton.enabled = bool(
            configured
            and stagingRoot
            and self._parameterNode.inspectedVolume
            and not running
        )
        self.ui.segmentTeethButton.text = (
            _("Run Teeth Segmentation (%1)").replace(
                "%1",
                _device.upper() if _device else _("device unavailable"),
            )
        )
        self.ui.cancelBackendButton.enabled = running

        inputVolume = self.ui.inputVolumeSelector.currentNode()
        self.ui.bridgeInputValueLabel.text = (
            inputVolume.GetName() if inputVolume else _("--")
        )
        roundTripVolume = self._parameterNode.roundTripVolume
        self.ui.roundTripOutputValueLabel.text = (
            roundTripVolume.GetName() if roundTripVolume else _("--")
        )
        teethSegmentation = self._parameterNode.inspectedSegmentation
        self.ui.teethSegmentationValueLabel.text = (
            teethSegmentation.GetName() if teethSegmentation else _("--")
        )
        self.ui.teethMetricsValueLabel.text = self._teethMetricsText(
            teethSegmentation
        )

    @staticmethod
    def _teethMetricsText(segmentationNode) -> str:
        if not segmentationNode:
            return _("--")
        segmentCount = segmentationNode.GetAttribute("DENTOBOT.SegmentCount")
        runtimeSeconds = segmentationNode.GetAttribute("DENTOBOT.RuntimeSeconds")
        foregroundVolumeMm3 = segmentationNode.GetAttribute(
            "DENTOBOT.ForegroundVolumeMm3"
        )
        peakAllocatedBytes = segmentationNode.GetAttribute(
            "DENTOBOT.PeakAllocatedBytes"
        )
        if not all((segmentCount, runtimeSeconds, foregroundVolumeMm3)):
            return _("Metrics unavailable")
        device = segmentationNode.GetAttribute("DENTOBOT.ActualDevice") or _("unknown")
        memoryText = ""
        if peakAllocatedBytes and peakAllocatedBytes.lower() not in ("none", "null"):
            memoryText = (
                f"; {float(peakAllocatedBytes) / (1024.0 ** 3):.2f} GiB peak GPU"
            )
        return (
            _("%1 segments; %2 s; %3 cm^3 foreground; %4%5")
            .replace("%1", segmentCount)
            .replace("%2", f"{float(runtimeSeconds):.1f}")
            .replace("%3", f"{float(foregroundVolumeMm3) / 1000.0:.2f}")
            .replace("%4", device)
            .replace("%5", memoryText)
        )

    def _setBackendStatus(self, message: str, state: str = "neutral") -> None:
        colors = {
            "neutral": "#555555",
            "working": "#1f5f99",
            "success": "#207227",
            "warning": "#b36b00",
            "error": "#b00020",
        }
        self.ui.backendStatusLabel.text = message
        self.ui.backendStatusLabel.styleSheet = f"color: {colors[state]};"

    def _appendBackendLog(self, line: str) -> None:
        cleanedLine = line.rstrip()
        if not cleanedLine:
            return
        self._backendOutputLines.append(cleanedLine)
        if len(self._backendOutputLines) > 2000:
            del self._backendOutputLines[:-2000]
        self.ui.backendLogTextEdit.appendPlainText(cleanedLine)
        try:
            progressEvent = json.loads(cleanedLine)
        except json.JSONDecodeError:
            progressEvent = None
        if (
            isinstance(progressEvent, dict)
            and progressEvent.get("event") == "progress"
            and progressEvent.get("message")
        ):
            self._setBackendStatus(str(progressEvent["message"]), "working")

    def _validateBackendConfiguration(
        self,
        requireStagingRoot: bool,
    ) -> tuple[str, str, str, str, str]:
        executionMode, distribution, pythonPath, stagingRoot, device = (
            self._backendConfiguration()
        )
        (
            launcherMode,
            launcherDistribution,
            launcherPython,
            launcherArtifactRoot,
            launcherDevice,
        ) = (
            self.logic.launcherBackendConfiguration()
        )
        if (
            self._parameterNode
            and self._parameterNode.useLauncherBackendConfiguration
            and not self.logic.launcherBackendConfigurationIsComplete(
                launcherMode,
                launcherDistribution,
                launcherPython,
                launcherArtifactRoot,
                launcherDevice,
            )
        ):
            raise ValueError(
                _(
                    "DENTOBOT launcher configuration is unavailable. Start "
                    "Slicer with the platform launcher or disable automatic "
                    "configuration and enter manual overrides."
                )
            )
        if executionMode == "wsl" and not distribution:
            raise ValueError(_("Enter the exact WSL distribution name."))
        if not pythonPath.startswith("/"):
            raise ValueError(
                _("Enter an absolute Linux path to the DENTOBOT Conda environment's Python.")
            )
        if requireStagingRoot:
            self.logic.validateStagingRoot(stagingRoot, executionMode)
        if device not in SUPPORTED_BACKEND_DEVICES:
            raise ValueError(_("Inference device must be cpu or cuda:0."))
        return executionMode, distribution, pythonPath, stagingRoot, device

    def _startBackendProcess(
        self,
        arguments: list[str],
        operation: str,
        runId: str,
        runContext: dict | None = None,
    ) -> None:
        if self._backendIsRunning():
            raise RuntimeError(_("Another DENTOBOT backend process is already running."))

        self._backendOutputLines = []
        self._backendOutputBuffer = ""
        self.ui.backendLogTextEdit.clear()
        self._backendCancellationRequested = False
        self._activeBackendRun = {
            "operation": operation,
            "runId": runId,
            **(runContext or {}),
        }
        self._setBackendStatus(_("Starting inference backend..."), "working")

        def logCallback(line: str) -> None:
            if self._activeBackendRun and self._activeBackendRun["runId"] == runId:
                self._appendBackendLog(line)

        def completedCallback(returnCode: int) -> None:
            self._onBackendCompleted(runId, int(returnCode))

        try:
            try:
                self._backendProcess = slicer.util.launchConsoleProcess(
                    arguments,
                    useStartupEnvironment=True,
                    blocking=False,
                    logCallback=logCallback,
                    completedCallback=completedCallback,
                )
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                # Parent the fallback process to the module widget and break
                # its signal/closure references when it finishes.  A
                # parentless QProcess whose Python callbacks retain the
                # process can keep PythonQt/Slicer alive after the child has
                # already exited.
                process = qt.QProcess(self.parent)
                process.setProcessChannelMode(qt.QProcess.MergedChannels)
                processEnvironment = qt.QProcessEnvironment()
                for environmentName, environmentValue in (
                    slicer.util.startupEnvironment().items()
                ):
                    processEnvironment.insert(
                        str(environmentName),
                        str(environmentValue),
                    )
                process.setProcessEnvironment(processEnvironment)

                def drainOutput() -> None:
                    rawOutput = process.readAllStandardOutput().data()
                    if isinstance(rawOutput, str):
                        chunk = rawOutput
                    else:
                        chunk = rawOutput.decode("utf-8", errors="replace")
                    self._backendOutputBuffer += chunk
                    completeLines = self._backendOutputBuffer.splitlines(
                        keepends=True
                    )
                    self._backendOutputBuffer = ""
                    for outputLine in completeLines:
                        if outputLine.endswith(("\n", "\r")):
                            logCallback(outputLine.rstrip("\r\n"))
                        else:
                            self._backendOutputBuffer = outputLine

                def releaseProcess() -> None:
                    for signal, callback in (
                        ("readyReadStandardOutput()", drainOutput),
                        ("finished(int,QProcess::ExitStatus)", processFinished),
                    ):
                        try:
                            process.disconnect(signal, callback)
                        except Exception:
                            logging.debug(
                                "DENTOBOT backend QProcess signal was already disconnected",
                                exc_info=True,
                            )
                    process.close()
                    process.deleteLater()

                def processFinished(
                    returnCode: int,
                    _exitStatus,
                ) -> None:
                    drainOutput()
                    if self._backendOutputBuffer:
                        logCallback(self._backendOutputBuffer)
                        self._backendOutputBuffer = ""
                    releaseProcess()
                    completedCallback(returnCode)

                process.connect(
                    "readyReadStandardOutput()",
                    drainOutput,
                )
                process.connect(
                    "finished(int,QProcess::ExitStatus)",
                    processFinished,
                )
                process.start(arguments[0], arguments[1:])
                if not process.waitForStarted(5000):
                    releaseProcess()
                    raise RuntimeError(
                        _("The inference backend process could not be started.")
                    )
                self._backendProcess = process
        except Exception:
            self._activeBackendRun = None
            self._backendCancellationRequested = False
            self._backendProcess = None
            self._updateBackendControls()
            raise
        self._updateBackendControls()

    def onCheckBackend(self) -> None:
        if not self.logic:
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not start the DENTOBOT backend health check.")
        ):
            executionMode, distribution, pythonPath, _stagingRoot, device = self._validateBackendConfiguration(
                requireStagingRoot=False
            )
            runId = uuid.uuid4().hex
            arguments = self.logic.buildHealthCommand(
                distribution=distribution,
                pythonPath=pythonPath,
                executionMode=executionMode,
                device=device,
            )
            self._startBackendProcess(
                arguments,
                "health",
                runId,
                {"device": device},
            )

    def onRunRoundTrip(self) -> None:
        if not self.logic or not self._parameterNode:
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not start the DENTOBOT NIfTI round trip."),
            waitCursor=True,
        ):
            volumeNode = self.ui.inputVolumeSelector.currentNode()
            if not volumeNode or not volumeNode.IsA("vtkMRMLScalarVolumeNode"):
                raise ValueError(_("Select a scalar CBCT volume first."))
            if (
                not self._parameterNode.inspectedVolume
                or self._parameterNode.inspectedVolume.GetID() != volumeNode.GetID()
            ):
                self.selectInspectionContext(volumeNode)
            if volumeNode.GetParentTransformNode():
                raise ValueError(
                    _(
                        "The selected volume has a parent transform. "
                        "Handle or harden that transform explicitly before this bridge test."
                    )
                )

            executionMode, distribution, pythonPath, stagingRoot, _device = self._validateBackendConfiguration(
                requireStagingRoot=True
            )
            self._setBackendStatus(
                _("Preparing the explicitly selected volume: %1")
                .replace("%1", volumeNode.GetName() or _("Unnamed volume")),
                "working",
            )
            runId = uuid.uuid4().hex
            runPaths = self.logic.createRoundTripRunPaths(
                stagingRoot,
                runId,
                executionMode=executionMode,
            )
            exported = slicer.util.exportNode(volumeNode, str(runPaths["input"]))
            if not exported or not runPaths["input"].is_file():
                raise RuntimeError(_("Slicer could not export the selected volume as NIfTI."))

            arguments = self.logic.buildRoundTripCommand(
                distribution=distribution,
                pythonPath=pythonPath,
                inputPath=runPaths["input"],
                outputPath=runPaths["output"],
                resultJsonPath=runPaths["result"],
                runId=runId,
                executionMode=executionMode,
            )
            self._startBackendProcess(
                arguments,
                "roundtrip",
                runId,
                {
                    "paths": runPaths,
                    "sourceVolumeId": volumeNode.GetID(),
                },
            )

    def onRunTeethSegmentation(self) -> None:
        if not self.logic or not self._parameterNode:
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not start DENTOBOT teeth segmentation."),
            waitCursor=True,
        ):
            volumeNode = self.ui.inputVolumeSelector.currentNode()
            if not volumeNode or not volumeNode.IsA("vtkMRMLScalarVolumeNode"):
                raise ValueError(_("Select a scalar CBCT volume first."))
            if (
                not self._parameterNode.inspectedVolume
                or self._parameterNode.inspectedVolume.GetID() != volumeNode.GetID()
            ):
                self.selectInspectionContext(volumeNode)
            if volumeNode.GetParentTransformNode():
                raise ValueError(
                    _(
                        "The selected volume has a parent transform. "
                        "Handle or harden that transform before segmentation."
                    )
                )

            executionMode, distribution, pythonPath, stagingRoot, device = self._validateBackendConfiguration(
                requireStagingRoot=True
            )
            self._setBackendStatus(
                _("Exporting %1 for teeth segmentation on %2...")
                .replace("%1", volumeNode.GetName() or _("Unnamed volume"))
                .replace("%2", device),
                "working",
            )
            runId = uuid.uuid4().hex
            runPaths = self.logic.createTeethSegmentationRunPaths(
                stagingRoot,
                runId,
                executionMode=executionMode,
            )
            exported = slicer.util.exportNode(volumeNode, str(runPaths["input"]))
            if not exported or not runPaths["input"].is_file():
                raise RuntimeError(
                    _("Slicer could not export the selected CBCT as NIfTI.")
                )

            arguments = self.logic.buildTeethSegmentationCommand(
                distribution=distribution,
                pythonPath=pythonPath,
                inputPath=runPaths["input"],
                outputPath=runPaths["output"],
                resultJsonPath=runPaths["result"],
                runId=runId,
                executionMode=executionMode,
                device=device,
            )
            self._startBackendProcess(
                arguments,
                "segment-teeth",
                runId,
                {
                    "paths": runPaths,
                    "sourceVolumeId": volumeNode.GetID(),
                    "device": device,
                },
            )

    def onCancelBackend(self) -> None:
        self._cancelBackendProcess(
            updateStatus=True,
            message=_("Cancellation requested. Waiting for the backend process to stop..."),
        )

    def _cancelBackendProcess(
        self,
        updateStatus: bool,
        message: str = "",
    ) -> None:
        if not self._backendProcess:
            return
        self._backendCancellationRequested = True
        if updateStatus:
            self._setBackendStatus(message or _("Cancellation requested."), "warning")
        try:
            self._backendProcess.terminate()
        except Exception:
            logging.exception("Failed to terminate DENTOBOT backend process")
