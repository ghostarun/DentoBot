"""Extracted view composition methods; public APIs remain on ViewerWidgetMixin."""

from __future__ import annotations

from .runtime import *


class ViewCompositionWidgetMixin:
    def _applyJawTeethView(
        self,
        jaw: str,
        dimension: str,
        *,
        updateStatus: bool = True,
    ) -> None:
        """Isolate upper/lower tooth masks and independently select 2D/3D."""

        jaw = str(jaw).lower()
        dimension = str(dimension).lower()
        if jaw not in {"upper", "lower", "all"}:
            raise ValueError(_("Jaw view must be upper, lower, or all."))
        if dimension not in {"2d", "3d", "both"}:
            raise ValueError(_("Jaw view dimension must be 2D, 3D, or both."))
        if not self._parameterNode or not self.logic:
            return

        stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
        entries = self._workflowViewEntries(stageIndex)
        self._workflowViewEntriesByKey = {
            entry["key"]: entry for entry in entries
        }
        wantedCategories = (
            {"upper_teeth", "lower_teeth"}
            if jaw == "all"
            else {f"{jaw}_teeth"}
        )
        visibleKeys = {
            entry["key"]
            for entry in entries
            if entry["category"] in wantedCategories
        }
        segmentSelections = [
            entry
            for entry in entries
            if entry["key"] in visibleKeys and entry["kind"] == "segments"
        ]
        if not segmentSelections:
            self.ui.workflowViewStatusLabel.text = _(
                "No %1 permanent-tooth masks with valid FDI labels are available."
            ).replace("%1", jaw)
            self.ui.workflowViewStatusLabel.styleSheet = "color: #b36b00;"
            return

        activePresetKey = f"teeth_{jaw}_{dimension}"
        self._applyWorkflowViewKeys(
            visibleKeys,
            activePresetKey=activePresetKey,
            updateStatus=False,
        )
        selectedByNode = {}
        for entry in segmentSelections:
            segmentationNode = (
                entry.get("segmentationNode")
                or self._parameterNode.teethSegmentation
            )
            if segmentationNode:
                selectedByNode.setdefault(segmentationNode, set()).update(
                    entry["segmentIds"]
                )
        for segmentationNode, segmentIds in selectedByNode.items():
            displayNode = segmentationNode.GetDisplayNode()
            if not displayNode or not segmentIds:
                continue
            wasModifying = displayNode.StartModify()
            try:
                displayNode.SetVisibility(True)
                displayNode.SetVisibility2D(dimension in {"2d", "both"})
                displayNode.SetVisibility3D(dimension in {"3d", "both"})
            finally:
                displayNode.EndModify(wasModifying)
        self._enforceStep6OpenedJawDisplaySeparation()

        self._workflowViewActivePresetKey = activePresetKey
        self._workflowViewVisibleKeys = set(visibleKeys)
        self._updateWorkflowViewControls()
        if updateStatus:
            self.onFrameWorkflowView()
            jawLabel = {
                "upper": _("Upper-jaw"),
                "lower": _("Lower-jaw"),
                "all": _("All"),
            }[jaw]
            dimensionLabel = {
                "2d": _("2D slices only"),
                "3d": _("3D view only"),
                "both": _("2D slices and 3D view"),
            }[dimension]
            maskCount = sum(
                len(segmentIds) for segmentIds in selectedByNode.values()
            )
            self.ui.workflowViewStatusLabel.text = _(
                "%1 tooth masks: %2 mask(s), shown in %3. Other workflow "
                "objects are hidden; mask geometry is unchanged."
            ).replace("%1", jawLabel).replace("%2", str(maskCount)).replace(
                "%3", dimensionLabel
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"

    @staticmethod
    def _comboBoxData(comboBox) -> str:
        if not comboBox or int(comboBox.currentIndex) < 0:
            return ""
        return str(comboBox.itemData(int(comboBox.currentIndex)) or "")

    @staticmethod
    def _setComboBoxData(comboBox, value: str) -> None:
        if not comboBox:
            return
        for index in range(int(comboBox.count)):
            if str(comboBox.itemData(index) or "") == str(value):
                comboBox.currentIndex = index
                return

    def _recommendedWorkflowViewComposition(
        self,
        stageIndex: int,
    ) -> ViewComposition:
        composition = recommended_view_composition(stageIndex)
        if not self._parameterNode or not self.logic:
            return composition
        if stageIndex == 6:
            record = self._targetToothRecordsById.get(
                self._parameterNode.targetToothSegmentId,
                {},
            )
            jaw = dental_jaw_from_fdi(record.get("fdiNumber"))
            if jaw:
                composition = composition.updated(
                    anatomy_scope=f"{jaw}_jaw_anatomy"
                )
        elif stageIndex == 9 and not self._parameterNode.finalPrintableTemplateModel:
            composition = composition.updated(
                overlay_groups=frozenset({"docks", "shell_components"})
            )
        elif stageIndex == 10:
            sceneKind = self._step6SceneKind()
            if sceneKind == "phantom":
                composition = ViewComposition(
                    anatomy_scope="none",
                    anatomy_dimension="3d",
                    cbct_mode="off",
                    overlay_groups=frozenset({"phantom", "robot"}),
                    anatomy_opacity=0.35,
                )
            elif (
                sceneKind == "case"
                and str(self._parameterNode.step6CaseJawPreparationMode)
                == "TargetJawFallback"
                and not self.logic.step6TargetJawFallbackFreshnessIssues(
                    self._parameterNode
                )
            ):
                # The placement-only fallback is already a complete derived
                # jaw-and-teeth segmentation.  Selecting source "full anatomy"
                # here duplicates the closed jaw and leaves pulp/root-canal
                # groups floating inside the fallback teeth.
                composition = ViewComposition(
                    anatomy_scope="none",
                    anatomy_dimension="3d",
                    cbct_mode="slices",
                    overlay_groups=frozenset(
                        {"trajectories", "jaw_opening", "robot"}
                    ),
                    anatomy_opacity=0.35,
                )
            elif (
                sceneKind == "case"
                and not self.logic.step6CaseJawOpeningFreshnessIssues(
                    self._parameterNode
                )
            ):
                # Current opened anatomy is represented by the derived fixed
                # upper and transformed lower jaw-and-teeth segmentations.
                # Re-enabling source full-anatomy groups here leaves pulp and
                # other closed-pose internals floating inside that proxy.
                composition = ViewComposition(
                    anatomy_scope="none",
                    anatomy_dimension="3d",
                    cbct_mode="slices",
                    overlay_groups=frozenset(
                        {
                            "target_bounds",
                            "trajectories",
                            "docks",
                            "final_template",
                            "jaw_opening",
                            "robot",
                        }
                    ),
                    anatomy_opacity=0.35,
                )
            elif sceneKind == "none":
                composition = ViewComposition()
        return composition

    def _workflowViewCompositionFromControls(self) -> ViewComposition:
        overlays = frozenset(
            key
            for key, action in self._workflowOverlayActions.items()
            if bool(action.checked)
        )
        previousOpacity = (
            self._workflowViewComposition.anatomy_opacity
            if self._workflowViewComposition
            else self._recommendedWorkflowViewComposition(
                int(self.ui.workflowStageComboBox.currentIndex)
            ).anatomy_opacity
        )
        return ViewComposition(
            anatomy_scope=self._comboBoxData(self._workflowAnatomyComboBox)
            or "none",
            anatomy_dimension=self._comboBoxData(
                self._workflowDimensionComboBox
            )
            or "both",
            cbct_mode=self._comboBoxData(self._workflowCbctComboBox) or "off",
            overlay_groups=overlays,
            anatomy_opacity=previousOpacity,
        )

    def _updateWorkflowViewCompositionControls(self, stageIndex: int) -> None:
        if not self._workflowAnatomyComboBox:
            return
        composition = self._workflowViewComposition
        if composition is None:
            composition = self._recommendedWorkflowViewComposition(stageIndex)
        self._setComboBoxData(
            self._workflowAnatomyComboBox,
            composition.anatomy_scope,
        )
        self._setComboBoxData(
            self._workflowDimensionComboBox,
            composition.anatomy_dimension,
        )
        self._setComboBoxData(self._workflowCbctComboBox, composition.cbct_mode)
        for key, action in self._workflowOverlayActions.items():
            action.checked = key in composition.overlay_groups
        overlayCount = len(composition.overlay_groups)
        self._workflowOverlayButton.text = (
            _("No overlays")
            if overlayCount == 0
            else _("%1 overlay group(s)").replace("%1", str(overlayCount))
        )
        if self._workflowAutoRecommendCheckBox:
            self._workflowAutoRecommendCheckBox.checked = bool(
                self.ui.autoWorkflowViewCheckBox.checked
            )

    def _onWorkflowAutoRecommendToggled(self, checked: bool) -> None:
        if self._updatingWorkflowViewUI:
            return
        self.ui.autoWorkflowViewCheckBox.checked = bool(checked)

    def onWorkflowViewCompositionChanged(self, index: int = -1) -> None:
        del index
        if self._updatingWorkflowViewUI or not self._parameterNode:
            return
        composition = self._workflowViewCompositionFromControls()
        self._applyWorkflowViewComposition(
            composition,
            recommended=False,
            allowRendererCreation=True,
        )

    def _onWorkflowOverlayToggled(self, overlayKey: str, checked: bool) -> None:
        del overlayKey, checked
        if self._updatingWorkflowViewUI or not self._parameterNode:
            return
        composition = self._workflowViewCompositionFromControls()
        self._applyWorkflowViewComposition(
            composition,
            recommended=False,
            allowRendererCreation=True,
        )

    def _workflowViewKeysForComposition(
        self,
        composition: ViewComposition,
        entries: list[dict],
        stageIndex: int,
    ) -> set[str]:
        overlayCategories = set().union(
            *(
                OVERLAY_CATEGORY_MAP[key]
                for key in composition.overlay_groups
            ),
        ) if composition.overlay_groups else set()
        visibleKeys: set[str] = set()
        for entry in entries:
            category = entry["category"]
            anatomyVisible = False
            if composition.anatomy_scope == "target_tooth":
                anatomyVisible = category == "target_mask"
            elif composition.anatomy_scope == "target_support":
                anatomyVisible = category in {"target_mask", "support_mask"}
            elif composition.anatomy_scope != "none":
                anatomyVisible = composition.anatomy_scope in entry.get(
                    "anatomyScopes",
                    (),
                )
            cbctVisible = (
                category == "case_volume"
                and composition.cbct_mode in {"slices", "both"}
            ) or (
                category == "case_volume_3d"
                and composition.cbct_mode in {"intensity_3d", "both"}
            )
            if anatomyVisible or cbctVisible or category in overlayCategories:
                visibleKeys.add(entry["key"])

        if stageIndex == 4 and "trajectories" in composition.overlay_groups:
            selected = self._parameterNode.trajectoryLine
            visibleKeys = {
                key
                for key in visibleKeys
                if not key.startswith("trajectory:")
                or (
                    selected is not None
                    and key == f"trajectory:{selected.GetID()}"
                )
            }
        if stageIndex == 10:
            sceneKind = self._step6SceneKind()
            rosActive = self.logic.isRos2MotionControlActive(
                self._parameterNode.robotBaseTransform
            )
            for entry in entries:
                category = entry["category"]
                if sceneKind == "phantom" and (
                    entry.get("anatomyScopes")
                    or category in {
                        "case_volume",
                        "case_volume_3d",
                        "case_jaw_opening",
                        "target_mask",
                        "bounds",
                        "trajectory",
                        "target_docking",
                        "final",
                    }
                ):
                    visibleKeys.discard(entry["key"])
                if sceneKind == "case" and category in {
                    "phantom",
                    "phantom_landmarks",
                }:
                    visibleKeys.discard(entry["key"])
                if rosActive and category == "robot_mrml":
                    visibleKeys.discard(entry["key"])
                if not rosActive and category in {"robot_ros", "robot_goal"}:
                    visibleKeys.discard(entry["key"])
        return visibleKeys

    def _setWorkflowCbctSlices(self, enabled: bool) -> None:
        volume = self._parameterNode.inputVolume if self._parameterNode else None
        volumeId = volume.GetID() if volume else None
        for composite in slicer.util.getNodesByClass(
            "vtkMRMLSliceCompositeNode"
        ):
            if enabled and volumeId:
                composite.SetBackgroundVolumeID(volumeId)
            elif volumeId and composite.GetBackgroundVolumeID() == volumeId:
                composite.SetBackgroundVolumeID(None)

    def _ensureExplicitWorkflowCbctRenderer(self):
        volume = self._parameterNode.inputVolume if self._parameterNode else None
        if not volume or not hasattr(slicer.modules, "volumerendering"):
            return None
        logic = slicer.modules.volumerendering.logic()
        display = logic.GetFirstVolumeRenderingDisplayNode(volume)
        if display:
            return display
        priorDisplayIds = {
            node.GetID()
            for node in slicer.util.getNodesByClass(
                "vtkMRMLVolumeRenderingDisplayNode"
            )
        }
        priorPropertyIds = {
            node.GetID()
            for node in slicer.util.getNodesByClass("vtkMRMLVolumePropertyNode")
        }
        display = logic.CreateDefaultVolumeRenderingNodes(volume)
        if display and display.GetID() not in priorDisplayIds:
            self._workflowViewCreatedRendererNodeIds.add(display.GetID())
        self._workflowViewCreatedPropertyNodeIds.update(
            node.GetID()
            for node in slicer.util.getNodesByClass("vtkMRMLVolumePropertyNode")
            if node.GetID() not in priorPropertyIds
        )
        return display

    def _applyWorkflowCbctMode(
        self,
        composition: ViewComposition,
        *,
        allowRendererCreation: bool,
    ) -> None:
        self._setWorkflowCbctSlices(composition.cbct_mode in {"slices", "both"})
        wantsRenderer = composition.cbct_mode in {"intensity_3d", "both"}
        display = None
        volume = self._parameterNode.inputVolume if self._parameterNode else None
        if volume and hasattr(slicer.modules, "volumerendering"):
            display = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(
                volume
            )
        if wantsRenderer and display is None and allowRendererCreation:
            display = self._ensureExplicitWorkflowCbctRenderer()
        if display:
            display.SetVisibility(bool(wantsRenderer))

    def _applyWorkflowAnatomyAppearance(
        self,
        composition: ViewComposition,
        visibleKeys: set[str],
    ) -> None:
        selectedByNode: dict[object, set[str]] = {}
        for entry in self._workflowViewEntriesByKey.values():
            if entry["key"] not in visibleKeys or entry["kind"] != "segments":
                continue
            segmentationNode = (
                entry.get("segmentationNode")
                or self._parameterNode.teethSegmentation
            )
            if segmentationNode:
                selectedByNode.setdefault(segmentationNode, set()).update(
                    entry["segmentIds"]
                )
        show2d = composition.anatomy_dimension in {"2d", "both"}
        show3d = composition.anatomy_dimension in {"3d", "both"}
        for segmentationNode, segmentIds in selectedByNode.items():
            display = segmentationNode.GetDisplayNode()
            if not display:
                continue
            wasModifying = display.StartModify()
            try:
                display.SetVisibility(bool(segmentIds))
                display.SetVisibility2D(show2d and bool(segmentIds))
                display.SetVisibility3D(show3d and bool(segmentIds))
                for segmentId in segmentIds:
                    display.SetSegmentVisibility3D(segmentId, show3d)
                    if hasattr(display, "SetSegmentVisibility2DFill"):
                        display.SetSegmentVisibility2DFill(segmentId, show2d)
                    if hasattr(display, "SetSegmentVisibility2DOutline"):
                        display.SetSegmentVisibility2DOutline(segmentId, show2d)
                    display.SetSegmentOpacity3D(
                        segmentId,
                        composition.anatomy_opacity,
                    )
            finally:
                display.EndModify(wasModifying)
        for entry in self._workflowViewEntriesByKey.values():
            if entry["key"] not in visibleKeys or entry["kind"] not in {"node", "nodes"}:
                continue
            if entry["category"] == "robot_goal":
                opacity = 0.3
            else:
                opacity = 1.0
            nodes = [entry["node"]] if entry["kind"] == "node" else entry["nodes"]
            for node in nodes:
                display = node.GetDisplayNode() if node else None
                if display and hasattr(display, "SetOpacity"):
                    display.SetOpacity(opacity)

    def _applyWorkflowViewComposition(
        self,
        composition: ViewComposition,
        *,
        recommended: bool,
        allowRendererCreation: bool,
        updateStatus: bool = True,
    ) -> None:
        if not self._parameterNode or not self.logic:
            return
        stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
        if stageIndex == 10 and self._step6SceneKind() == "conflict":
            self.ui.workflowViewStatusLabel.text = _(
                "Step 6 has both case and phantom scene sources. Resolve the scene conflict before composing the robot workspace view."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #b00020;"
            return
        entries = self._workflowViewEntries(stageIndex)
        self._workflowViewEntriesByKey = {entry["key"]: entry for entry in entries}
        self._ensureWorkflowViewSnapshot()
        self._applyWorkflowCbctMode(
            composition,
            allowRendererCreation=allowRendererCreation,
        )
        entries = self._workflowViewEntries(stageIndex)
        self._workflowViewEntriesByKey = {entry["key"]: entry for entry in entries}
        visibleKeys = self._workflowViewKeysForComposition(
            composition,
            entries,
            stageIndex,
        )
        self._workflowViewComposition = composition
        activeKey = "recommended" if recommended else "composition"
        self._applyWorkflowViewKeys(
            visibleKeys,
            activePresetKey=activeKey,
            updateStatus=False,
        )
        self._applyWorkflowAnatomyAppearance(composition, visibleKeys)
        self._enforceStep6OpenedJawDisplaySeparation()
        self._updateWorkflowViewControls()
        if updateStatus:
            self.ui.workflowViewStatusLabel.text = _(
                "Applied one composable display view. Anatomy, slices, renderers, and overlays changed presentation only."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"
