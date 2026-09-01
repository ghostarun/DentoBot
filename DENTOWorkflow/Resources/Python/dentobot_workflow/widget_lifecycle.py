"""Extracted MRML and module lifecycle methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


class LifecycleWidgetMixin:
    def cleanup(self) -> None:
        self._isCleaningUp = True
        self._workflowViewRefreshScheduled = False
        self._step6ExpertDiagnosticHandoffActive = False
        if self._step6ExpertReturnToolbar:
            self._step6ExpertReturnToolbar.hide()
            self._step6ExpertReturnToolbar.deleteLater()
            self._step6ExpertReturnToolbar = None
        if self._robotWorkflowFacade:
            self._robotWorkflowFacade.clearTransientState()
        if self._applicationShell:
            self._applicationShell.cleanup()
        self._setRobotTransformInteractionVisible(False)
        self._disableRobotKeyboardShortcuts()
        self._hideViewControlsPalette(preservePreference=True)
        self._cancelBackendProcess(updateStatus=False)
        self._restoreTrajectoryVerificationViewState(updateUi=False)
        self._restoreCrossViewNavigation(updateUi=False)
        self._restoreTemplateFinalizationViewState(updateUi=False)
        self._restoreTemplateSupportBoundaryFocus(updateUi=False)
        self._restoreWorkflowViewState(updateUi=False)
        self._restoreStageExclusiveInteractionLocks()
        self.setParameterNode(None)
        self.removeObservers()
        self._sceneObserversActive = False
        release_default_ros2_node_singleton()
        if self._viewControlsPalette:
            self._viewControlsPalette.deleteLater()
            self._viewControlsPalette = None
            self._viewControlsTabWidget = None

    def enter(self) -> None:
        self._addSceneObservers()
        self.initializeParameterNode()
        if self._applicationShell:
            self._applyDENTOBOTGuiMode(
                DENTOApplicationShell.storedGuiMode(),
                persist=False,
            )
        self._updateRobotKeyboardShortcutState()
        qt.QTimer.singleShot(0, self._restoreViewControlsPaletteOnEnter)

    def exit(self) -> None:
        if self._step6ExpertDiagnosticHandoffActive:
            self._setRobotTransformInteractionVisible(False)
            self._disableRobotKeyboardShortcuts()
            return
        if self._applicationShell:
            self._applicationShell.deactivate()
        self._setRobotTransformInteractionVisible(False)
        self._disableRobotKeyboardShortcuts()
        self._hideViewControlsPalette(preservePreference=True)
        self._restoreTrajectoryVerificationViewState(updateUi=False)
        self._restoreCrossViewNavigation(updateUi=False)
        self._restoreAssistedTrajectoryFocus(updateUi=False)
        self._restoreTemplateFinalizationViewState(updateUi=False)
        self._restoreTemplateSupportBoundaryFocus(updateUi=False)
        self._restoreWorkflowViewState(updateUi=False)
        self._restoreStageExclusiveInteractionLocks()
        self.setParameterNode(None)
        self._removeSceneObservers()

    def _addSceneObservers(self) -> None:
        if self._sceneObserversActive:
            return
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndImportEvent, self.onSceneEndImport)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartSaveEvent, self.onSceneStartSave)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndSaveEvent, self.onSceneEndSave)
        self._sceneObserversActive = True

    def _removeSceneObservers(self) -> None:
        if not self._sceneObserversActive:
            return
        self.removeObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.removeObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self.removeObserver(slicer.mrmlScene, slicer.mrmlScene.EndImportEvent, self.onSceneEndImport)
        self.removeObserver(slicer.mrmlScene, slicer.mrmlScene.StartSaveEvent, self.onSceneStartSave)
        self.removeObserver(slicer.mrmlScene, slicer.mrmlScene.EndSaveEvent, self.onSceneEndSave)
        self._sceneObserversActive = False

    def onSceneStartClose(self, caller=None, event=None) -> None:
        del caller, event
        self._loadedCaseBundlePath = ""
        self._caseBundleRobotProfileCompatible = None
        self._caseBundleRobotProfileMigrationMessage = ""
        self._workflowNavigationInitializedFromScene = False
        self._resumeTrajectoryVerificationAfterSave = False
        self._trajectoryVerificationResumeStateAfterSave = None
        self._resumeTemplateSupportBoundaryFocusAfterSave = False
        self._resumeAssistedTrajectoryFocusAfterSave = False
        self._resumeCrossViewNavigationAfterSave = False
        self._resumeWorkflowViewPresetAfterSave = ""
        self._resumeWorkflowViewPriorStateAfterSave = None
        self._resumeWorkflowViewVisibleKeysAfterSave.clear()
        self._resumeWorkflowViewCompositionAfterSave = None
        self._restoreTrajectoryVerificationViewState(updateUi=False)
        self._restoreCrossViewNavigation(updateUi=False)
        self._restoreAssistedTrajectoryFocus(updateUi=False)
        self._restoreTemplateFinalizationViewState(updateUi=False)
        self._restoreTemplateSupportBoundaryFocus(updateUi=False)
        self._restoreWorkflowViewState(updateUi=False)
        self._restoreStageExclusiveInteractionLocks()
        self._cancelBackendProcess(
            updateStatus=True,
            message=_("Backend process cancelled because the scene is closing."),
        )
        if self._robotWorkflowFacade:
            self._robotWorkflowFacade.clearTransientState()
        if self._step6MotionPreviewTimer is not None:
            self._step6MotionPreviewTimer.stop()
            self._step6MotionPreviewTimer = None
        self._step6MotionPreviewIndex = 0
        self._step6MotionPlan = None
        mrmlRobotModels = self.logic.robotModelNodes() if self.logic else []
        self.setParameterNode(None)
        try:
            if find_ros2_robot_by_name(ROS2_ROBOT_NAME) is not None:
                disconnected, message = disconnect_dentobot_motion_control(
                    mrmlRobotModels,
                )
                if not disconnected:
                    logging.warning(
                        "Could not fully disconnect DENTOBOT ROS motion control "
                        "before scene close: %s",
                        message,
                    )
        except Exception:
            logging.exception(
                "Could not disconnect DENTOBOT ROS motion control before scene close"
            )
        finally:
            # These MRML publishers/subscribers are Python-owned adapter state.
            # Release them before Slicer removes the ROS scene nodes so no stale
            # callback or wrapped VTK object survives into the replacement scene.
            shutdown_slicer_adapter()
        self._lastDisplayedVolumeId = None
        self._loadedVolumeDisplaySettingsByNodeId.clear()

    def onSceneEndClose(self, caller=None, event=None) -> None:
        del caller, event
        if self._isCleaningUp:
            return
        ensure_default_ros2_node_in_scene()
        qt.QTimer.singleShot(0, self._initializeAfterSceneClose)

    def _initializeAfterSceneClose(self) -> None:
        if self._isCleaningUp or self._caseBundleRestoreDepth > 0:
            return
        try:
            is_entered = bool(self.parent and self.parent.isEntered)
        except (RuntimeError, ValueError):
            return
        if is_entered and self._parameterNode is None:
            self.initializeParameterNode()

    def onSceneEndImport(self, caller=None, event=None) -> None:
        """Rebind the persisted workflow node after every MRML scene import."""

        del caller, event
        marked = mark_slicer_ros2_runtime_nodes_transient()
        cleared = clear_legacy_dentobot_moveit_source_attributes()
        clearedActive = clear_stale_ros2_motion_active_attributes()
        if marked:
            logging.warning(
                "Excluded %d imported SlicerROS2 runtime node(s) from future "
                "DENTOBOT scene saves",
                marked,
            )
        if cleared:
            logging.warning(
                "Cleared legacy MoveIt persistence tags from %d DENTOBOT "
                "source model(s)",
                cleared,
            )
        if self._caseBundleRestoreDepth > 0:
            # The package loader owns parameter discovery, pre-bind
            # validation, GUI hydration, and post-bind validation.  Ordinary
            # EndImport refresh would otherwise mutate the scene before its
            # integrity snapshot is checked.
            return
        if self.parent.isEntered:
            self.initializeParameterNode()
            if clearedActive:
                logging.warning(
                    "Cleared %d stale persisted ROS-active flag(s); no live "
                    "SlicerROS2 robot was restored",
                    clearedActive,
                )
            self._revalidateImportedStep6ContextAfterLoad()

    def _revalidateImportedStep6ContextAfterLoad(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        cancelledPlacement = (
            self.logic.cancelTransientStep6CaseJawLandmarkPlacement(
                self._parameterNode
            )
        )
        if cancelledPlacement.get("cancelled"):
            logging.warning(
                "Cancelled restored transient Step 6A placement state at index "
                "%s; %d defined point(s) were retained for explicit review",
                cancelledPlacement.get("pendingLandmarkIndex") or "unknown",
                int(cancelledPlacement.get("definedPointCount") or 0),
            )
        removedRobotNodes = self.logic.deleteTransientRobotRuntimeNodes()
        if removedRobotNodes:
            logging.warning(
                "Removed %d reconstructible local Step 6 robot node(s) from "
                "the restored scene before deterministic post-validation rehydration",
                len(removedRobotNodes),
            )
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
        if (
            self._parameterNode.robotBaseMountLocked
            and normalize_base_status(self._parameterNode.step6BasePlacementStatus)
            is BasePlacementStatus.UNLOCKED
        ):
            self._parameterNode.step6BasePlacementStatus = (
                BasePlacementStatus.PROVISIONAL_LOCKED.value
            )
            self._parameterNode.step6BasePlacementSource = "legacy-scene/unreviewed"
            self._parameterNode.step6BasePlacementRevision = max(
                1, int(self._parameterNode.step6BasePlacementRevision)
            )
            self._parameterNode.step6ConfirmedTaskJson = ""
            logging.warning(
                "Restored a legacy Boolean base lock as provisional/unreviewed; "
                "task confirmation is required before planning"
            )
        quarantineMessage = self.logic.quarantineLegacyRobotBasePlacement(
            self._parameterNode
        )
        if quarantineMessage:
            logging.warning(quarantineMessage)
        if not self._parameterNode.step6PlanningContextImported:
            return
        packageIssues = self.logic.step6PlanningPackageFreshnessIssues(
            self._parameterNode
        )
        if packageIssues:
            self.logic.invalidateStep6TaskConfirmation(
                self._parameterNode,
                _("The restored Steps 0–5 planning package is stale."),
                makeBaseStale=True,
            )
            self._parameterNode.step6PlanningContextImported = False
            message = _(
                "Saved Step 6 context is stale and was deactivated: %1 Return to "
                "the indicated upstream step, regenerate, verify, and import again."
            ).replace("%1", " ".join(packageIssues))
            logging.error(message)
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus()
            self._updateStep6PlanningUi(message, error=True)
            return

        jawIssues = self.logic.step6CaseJawOpeningFreshnessIssues(
            self._parameterNode
        )
        if not jawIssues:
            try:
                self._rehydrateStep6LocalRobotAfterRestore()
            except (RuntimeError, ValueError, OSError) as exc:
                message = _(
                    "The case package restored successfully, but the local "
                    "seven-link robot could not be rebuilt: %1 Use Load / "
                    "Refresh Robot; the reviewed base remains unchanged."
                ).replace("%1", str(exc))
                logging.exception(message)
                self._updateStep6PlanningUi(message, error=True)
            return
        hadReviewedBase = bool(
            self._parameterNode.robotBaseMountLocked
            or normalize_base_status(self._parameterNode.step6BasePlacementStatus)
            in {
                BasePlacementStatus.PROVISIONAL_LOCKED,
                BasePlacementStatus.REGISTERED_LOCKED,
                BasePlacementStatus.STALE,
            }
        )
        self.logic.invalidateStep6TaskConfirmation(
            self._parameterNode,
            _("The restored case mouth-opening context requires review."),
            makeBaseStale=True,
        )
        message = _(
            "Steps 0–5 package restored and remains active. Complete 6.0A: %1"
        ).replace("%1", " ".join(jawIssues))
        if hadReviewedBase:
            message += _(
                " The saved base pose was retained as Stale and unlocked; "
                "review and provisionally lock it again after opening the jaw."
            )
        logging.warning(message)
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi(message)

    def _rehydrateStep6LocalRobotAfterRestore(self) -> bool:
        """Rebuild excluded local robot links without restoring ROS runtime."""

        if not self._parameterNode or not self.logic:
            return False
        if not bool(self._parameterNode.step6PlanningContextImported):
            return False
        if self.logic.step6CaseJawOpeningFreshnessIssues(self._parameterNode):
            return False
        if self.logic.step6BasePlacementFreshnessIssues(self._parameterNode):
            return False
        if self.logic.taskHomeFreshnessIssues(self._parameterNode):
            return False
        if not self.logic.isRobotBaseTransformNode(
            self._parameterNode.robotBaseTransform
        ):
            return False
        jointPositionsSi = joint_positions_si_from_display(
            self._parameterNode.robotJoint1Deg,
            self._parameterNode.robotJoint2Mm,
            self._parameterNode.robotJoint3Deg,
            self._parameterNode.robotJoint4Mm,
            self._parameterNode.robotJoint5Deg,
            self._parameterNode.robotJoint6Deg,
        )
        base, models = self.logic.createOrUpdateRobotPlacement(
            self._parameterNode.robotBaseTransform,
            jointPositionsSi,
        )
        self._parameterNode.robotBaseTransform = base
        if len(models) != 7:
            self.logic.deleteTransientRobotRuntimeNodes()
            raise RuntimeError(
                _(
                    "Restored Step 6 state is current, but the local robot "
                    "could not be reconstructed as seven links."
                )
            )
        if self._robotWorkflowFacade:
            self._robotWorkflowFacade.clearTransientState()
        self._updateRobotPlacement()
        self._updateStep6PlanningUi(
            _(
                "Restored the reviewed Step 6 base and deterministically rebuilt "
                "the seven local robot links; ROS remains disconnected."
            )
        )
        logging.info(
            "Rehydrated %d local Step 6 robot links at the saved base/joint state",
            len(models),
        )
        return True

    @staticmethod
    def _suspendRos2MotionActiveAttributesForSave() -> list[str]:
        """Remove process-only active flags and return nodes to resume afterward."""

        resumeNodeIds = []
        for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode"):
            if node.GetAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE) != "true":
                continue
            resumeNodeIds.append(node.GetID())
            node.RemoveAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE)
        return resumeNodeIds

    @staticmethod
    def _restoreRos2MotionActiveAttributesAfterSave(nodeIds: list[str]) -> None:
        for nodeId in nodeIds:
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            if node is not None:
                node.SetAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE, "true")

    def onSceneStartSave(self, caller=None, event=None) -> None:
        """Keep transient verification presentation out of saved MRB state."""

        del caller, event
        mark_slicer_ros2_runtime_nodes_transient()
        self._resumeRos2MotionActiveBaseIdsAfterSave = (
            self._suspendRos2MotionActiveAttributesForSave()
        )
        self._resumeTrajectoryVerificationAfterSave = bool(
            self._trajectoryVerificationEnabled
        )
        if self._resumeTrajectoryVerificationAfterSave:
            priorState = self._trajectoryVerificationPriorSliceState or {}
            sliceNodeId = priorState.get("sliceNodeId")
            sliceNode = (
                slicer.mrmlScene.GetNodeByID(sliceNodeId)
                if sliceNodeId
                else None
            )
            trajectoryNode = (
                self._parameterNode.trajectoryLine if self._parameterNode else None
            )
            self._trajectoryVerificationResumeStateAfterSave = (
                {
                    "trajectoryNodeId": trajectoryNode.GetID(),
                    "sliceNodeId": sliceNode.GetID(),
                    "sliceToRas": self._captureSliceToRasElements(sliceNode),
                    "angleDeg": self._trajectoryVerificationAngleDeg,
                }
                if trajectoryNode and sliceNode
                else None
            )
            self._restoreTrajectoryVerificationViewState(updateUi=False)
        self._resumeTemplateSupportBoundaryFocusAfterSave = bool(
            self._templateSupportBoundaryFocusState
        )
        if self._resumeTemplateSupportBoundaryFocusAfterSave:
            self._restoreTemplateSupportBoundaryFocus(updateUi=False)
        self._resumeAssistedTrajectoryFocusAfterSave = bool(
            self._assistedTrajectoryFocusState
        )
        if self._resumeAssistedTrajectoryFocusAfterSave:
            self._restoreAssistedTrajectoryFocus(updateUi=False)
        self._resumeCrossViewNavigationAfterSave = bool(
            self._crossViewNavigationPriorState
        )
        if self._resumeCrossViewNavigationAfterSave:
            self._restoreCrossViewNavigation(updateUi=False)
        self._resumeWorkflowViewPresetAfterSave = (
            self._workflowViewActivePresetKey
            if self._workflowViewPriorState
            else ""
        )
        self._resumeWorkflowViewCompositionAfterSave = (
            self._workflowViewComposition
            if self._workflowViewPriorState
            else None
        )
        self._resumeWorkflowViewPriorStateAfterSave = (
            self._workflowViewPriorState
        )
        self._resumeWorkflowViewVisibleKeysAfterSave = set(
            self._workflowViewVisibleKeys
        )
        if self._resumeWorkflowViewPriorStateAfterSave:
            self._restoreWorkflowViewState(updateUi=False)

    def onSceneEndSave(self, caller=None, event=None) -> None:
        del caller, event
        self._restoreRos2MotionActiveAttributesAfterSave(
            self._resumeRos2MotionActiveBaseIdsAfterSave
        )
        self._resumeRos2MotionActiveBaseIdsAfterSave = []
        workflowViewPreset = self._resumeWorkflowViewPresetAfterSave
        workflowViewComposition = self._resumeWorkflowViewCompositionAfterSave
        workflowViewState = self._resumeWorkflowViewPriorStateAfterSave
        workflowViewVisibleKeys = set(
            self._resumeWorkflowViewVisibleKeysAfterSave
        )
        self._resumeWorkflowViewPresetAfterSave = ""
        self._resumeWorkflowViewCompositionAfterSave = None
        self._resumeWorkflowViewPriorStateAfterSave = None
        self._resumeWorkflowViewVisibleKeysAfterSave.clear()
        if workflowViewState and self._parameterNode:
            self._workflowViewPriorState = workflowViewState
            self._workflowViewVisibleKeys = workflowViewVisibleKeys
            self._workflowViewComposition = workflowViewComposition
            self._updateWorkflowViewControls()
            if workflowViewPreset == "composition" and workflowViewComposition:
                self._applyWorkflowViewComposition(
                    workflowViewComposition,
                    recommended=False,
                    allowRendererCreation=True,
                    updateStatus=False,
                )
            elif workflowViewPreset == "custom":
                self._applyWorkflowViewKeys(
                    workflowViewVisibleKeys,
                    activePresetKey="custom",
                    updateStatus=False,
                )
            elif workflowViewPreset:
                self._applyWorkflowViewPreset(
                    workflowViewPreset,
                    updateStatus=False,
                )
        if self._resumeTrajectoryVerificationAfterSave:
            self._resumeTrajectoryVerificationAfterSave = False
            resumeState = self._trajectoryVerificationResumeStateAfterSave
            self._trajectoryVerificationResumeStateAfterSave = None
            try:
                self._enableTrajectoryVerificationView()
                trajectoryNode = (
                    self._parameterNode.trajectoryLine if self._parameterNode else None
                )
                sliceNode = (
                    slicer.mrmlScene.GetNodeByID(resumeState["sliceNodeId"])
                    if resumeState
                    else None
                )
                if (
                    resumeState
                    and trajectoryNode
                    and trajectoryNode.GetID() == resumeState["trajectoryNodeId"]
                    and sliceNode
                ):
                    matrix = self._matrixFromElements(resumeState["sliceToRas"])
                    sliceNode.GetSliceToRAS().DeepCopy(matrix)
                    sliceNode.UpdateMatrices()
                    self._trajectoryVerificationAngleDeg = float(
                        resumeState["angleDeg"]
                    )
                    self._trajectoryVerificationAppliedTrajectoryNodeId = (
                        trajectoryNode.GetID()
                    )
                    self._trajectoryVerificationLastAppliedAngleDeg = (
                        self._trajectoryVerificationAngleDeg
                    )
                    self._updateTrajectoryVerificationControls()
            except (RuntimeError, ValueError) as exc:
                self._setTrajectoryVerificationEnabledUi(False)
                self._setTrajectoryVerificationStatus(str(exc), error=True)

        resumeTemplateFocus = self._resumeTemplateSupportBoundaryFocusAfterSave
        self._resumeTemplateSupportBoundaryFocusAfterSave = False
        if resumeTemplateFocus:
            try:
                self._startTemplateSupportBoundaryFocus()
                self._updateTemplateModeling()
            except (RuntimeError, ValueError) as exc:
                self._templateStatusWarning = str(exc)
                self._updateTemplateModeling()
        resumeAssistedFocus = self._resumeAssistedTrajectoryFocusAfterSave
        self._resumeAssistedTrajectoryFocusAfterSave = False
        if resumeAssistedFocus:
            try:
                self._startAssistedTrajectoryFocus()
            except (RuntimeError, ValueError):
                self._updateAssistedTrajectoryControls()
        resumeCrossViewNavigation = self._resumeCrossViewNavigationAfterSave
        self._resumeCrossViewNavigationAfterSave = False
        if resumeCrossViewNavigation:
            try:
                self._enableCrossViewNavigation()
            except RuntimeError:
                self._setCrossViewNavigationChecked(False)

    def initializeParameterNode(self) -> None:
        if not self.logic:
            return

        self.setParameterNode(self.logic.getParameterNode())
        if os.name != "nt":
            if self._parameterNode.inferenceDevice == "cuda:0":
                self._parameterNode.inferenceDevice = "cpu"

        newlyLoadedVolume = self._newlyLoadedDicomVolume()
        if newlyLoadedVolume:
            self._parameterNode.inputVolume = newlyLoadedVolume
        elif not self._parameterNode.inputVolume:
            latestVolume = self.logic.getLatestScalarVolumeNode()
            if latestVolume:
                self._parameterNode.inputVolume = latestVolume
        if not self._parameterNode.teethSegmentation:
            latestSegmentation = self.logic.getLatestTeethSegmentationNode()
            if latestSegmentation:
                self._parameterNode.teethSegmentation = latestSegmentation

        self._reconcileAuthoritativeSegmentationSourceVolume()

        self._updateFromParameterNode()

    def _reconcileAuthoritativeSegmentationSourceVolume(self) -> None:
        """Keep planning views on the selected segmentation's referenced CBCT."""

        if not self._parameterNode or not self.logic:
            return
        segmentationNode = self._parameterNode.teethSegmentation
        if not segmentationNode:
            return
        try:
            sourceVolume = self.logic.getSegmentationSourceVolume(
                segmentationNode
            )
        except ValueError:
            return
        if self._parameterNode.inputVolume is not sourceVolume:
            previousVolume = self._parameterNode.inputVolume
            logging.warning(
                "Reconciled workflow CBCT %s to authoritative segmentation source %s",
                previousVolume.GetID() if previousVolume else "none",
                sourceVolume.GetID(),
            )
            self._parameterNode.inputVolume = sourceVolume
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if selectionNode.GetActiveVolumeID() != sourceVolume.GetID():
            self._showVolumeInSliceViews(sourceVolume)

    def setParameterNode(self, parameterNode: DENTOWorkflowParameterNode | None) -> None:
        if self._workflowViewPriorState:
            self._restoreWorkflowViewState(updateUi=False)
        self._restoreAssistedTrajectoryFocus(updateUi=False)
        self._restoreTemplateSupportBoundaryFocus(updateUi=False)
        if self._parameterNode:
            if self._parameterNodeGuiTag is not None:
                self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._updateFromParameterNode)

        self._parameterNode = parameterNode
        self._parameterNodeGuiTag = None

        if self._parameterNode:
            wasUpdating = self._updatingFromParameterNode
            self._updatingFromParameterNode = True
            try:
                self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            finally:
                self._updatingFromParameterNode = wasUpdating
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._updateFromParameterNode)
            self._updateFromParameterNode()
        else:
            self._bindSegmentationReviewNode(None)
            self._clearSegmentationReview()
            self._bindPlanningTrajectoryNode(None)
            self._bindAssistedTrajectoryEntryNode(None)
            self._clearPlanning()
            self._bindTemplateSupportBoundaryNode(None)
            self._bindTemplateInsertionDirectionNode(None)
            self._bindSelectedGuideTrajectoryNodes([])
            self._clearTemplateModeling()
            self._clearTemplateGuide()
            self._clearTemplateFinalization()
            self._clearRobotPlacement()

    def _newlyLoadedDicomVolume(self) -> vtkMRMLScalarVolumeNode | None:
        if self._volumeNodeIdsBeforeDICOM is None or not self.logic:
            return None

        previousNodeIds = self._volumeNodeIdsBeforeDICOM
        self._volumeNodeIdsBeforeDICOM = None
        newVolumes = [
            node for node in self.logic.getScalarVolumeNodes()
            if node.GetID() not in previousNodeIds
        ]
        return newVolumes[-1] if newVolumes else None

    def _updateFromParameterNode(self, caller=None, event=None) -> None:
        del caller, event
        if (
            self._updatingFromParameterNode
            or self._restoringTrajectoryAssociation
            or not self._parameterNode
            or not self.logic
        ):
            return
        self._updatingFromParameterNode = True
        try:
            self._updateFromParameterNodeOnce()
        finally:
            self._updatingFromParameterNode = False

    def _updateFromParameterNodeOnce(self) -> None:
        """Perform one non-reentrant parameter-to-widget synchronization."""

        volumeNode = self._parameterNode.inputVolume
        self.ui.showVolumeButton.enabled = volumeNode is not None
        self._updateBackendControls()
        self._bindSegmentationReviewNode(self._parameterNode.teethSegmentation)
        self._updateSegmentationReview()
        self._bindPlanningTrajectoryNode(self._parameterNode.trajectoryLine)
        self._bindAssistedTrajectoryEntryNode(
            self._parameterNode.assistedTrajectoryEntries
        )
        self._updatePlanning()
        self._updateTargetDocking()
        self._bindTemplateSupportBoundaryNode(
            self._parameterNode.templateSupportBoundaryCurve
        )
        self._bindTemplateInsertionDirectionNode(
            self._parameterNode.templateInsertionDirection
        )
        self._updateTemplateModeling()
        self._updateTemplateGuide()
        self._updateTemplateFinalization()
        self._bindDraftJawLandmarksNode(self._parameterNode.draftJawLandmarks)
        self._bindStep6CaseJawLandmarksNode(
            self._parameterNode.step6CaseJawLandmarks
        )
        self._updateRobotPlacement()
        self._updateStageExclusiveInteractionLocks(
            int(self.ui.workflowStageComboBox.currentIndex)
        )
        self._updateWorkflowNavigationRecommendation()
        self._refreshWorkflowViewAfterStateChange()
        if self._applicationShell and self._applicationShell.active:
            self._applicationShell.updateCaseAndRuntime(
                self._parameterNode.caseName,
            )

        if not volumeNode:
            self._setMetadataPlaceholders()
            self.ui.statusLabel.text = _("No CBCT volume selected.")
            self.ui.statusLabel.styleSheet = "color: #b36b00;"
            self._lastDisplayedVolumeId = None
            return

        try:
            metadata = self.logic.getVolumeMetadata(volumeNode)
        except ValueError as exc:
            self._setMetadataPlaceholders()
            self.ui.statusLabel.text = str(exc)
            self.ui.statusLabel.styleSheet = "color: #b00020;"
            return

        self.ui.volumeNameValueLabel.text = metadata["name"]
        self.ui.dimensionsValueLabel.text = metadata["dimensions"]
        self.ui.spacingValueLabel.text = metadata["spacing"]
        self.ui.scalarTypeValueLabel.text = metadata["scalarType"]
        self.ui.scalarRangeValueLabel.text = metadata["scalarRange"]
        self.ui.orientationValueLabel.text = metadata["orientation"]
        self.ui.geometryStatusValueLabel.text = metadata["geometryStatus"]
        self.ui.statusLabel.text = _("Ready. The selected volume is available for inspection.")
        self.ui.statusLabel.styleSheet = "color: #207227;"

        if volumeNode.GetID() != self._lastDisplayedVolumeId:
            self._showVolumeInSliceViews(volumeNode)
