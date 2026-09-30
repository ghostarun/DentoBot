"""Extracted segmentation and CBCT display preset methods."""

from __future__ import annotations

from .runtime import *


class DisplayPresetsWidgetMixin:

    def _currentSceneDisplayPreset(self) -> dict:
        """Capture a node-independent display parameter set for this MRB."""

        if not self._parameterNode or not self.logic:
            raise ValueError(_("DENTOWorkflow is not ready."))
        segmentationNode = self._reviewSegmentationNode
        segmentationDisplay = (
            segmentationNode.GetDisplayNode() if segmentationNode else None
        )
        baselineDisplay = {}
        if (
            segmentationNode
            and self._workflowViewPriorState
            and self._workflowViewPriorState.get("segmentationNodeId")
            == segmentationNode.GetID()
        ):
            baselineDisplay = self._workflowViewPriorState.get(
                "segmentationDisplay", {}
            )
        if segmentationDisplay:
            segmentation2DVisible = bool(
                baselineDisplay.get(
                    "visibility2D",
                    segmentationDisplay.GetVisibility2D(),
                )
            )
            segmentation3DVisible = bool(
                baselineDisplay.get(
                    "visibility3D",
                    segmentationDisplay.GetVisibility3D(),
                )
            )
            segmentation2DOpacity = float(
                baselineDisplay.get(
                    "opacity2DFill",
                    segmentationDisplay.GetOpacity2DFill(),
                )
            )
            segmentation3DOpacity = float(
                baselineDisplay.get(
                    "opacity3D",
                    segmentationDisplay.GetOpacity3D(),
                )
            )
            renderingMode = self.logic.getSegmentation2DRenderingMode(
                segmentationNode
            )
        else:
            segmentation2DVisible = bool(
                self.ui.segmentation2DCheckBox.checked
            )
            segmentation3DVisible = bool(
                self.ui.segmentation3DCheckBox.checked
            )
            segmentation2DOpacity = float(
                self.ui.segmentation2DOpacitySlider.value
            ) / 100.0
            segmentation3DOpacity = float(
                self.ui.segmentation3DOpacitySlider.value
            ) / 100.0
            renderingMode = (
                self.logic.SEGMENTATION_2D_RENDERING_MODE_SMOOTH
                if int(self.ui.segmentation2DRenderingModeComboBox.currentIndex)
                == 0
                else self.logic.SEGMENTATION_2D_RENDERING_MODE_NATIVE
            )

        sourceVolume = None
        if segmentationNode:
            try:
                sourceVolume = self.logic.getSegmentationSourceVolume(
                    segmentationNode
                )
            except ValueError:
                pass
        volumeDisplay = (
            self.logic.getScalarVolumeDisplaySettings(sourceVolume)
            if sourceVolume
            else {
                "autoWindowLevel": bool(
                    self.ui.cbctAutoWindowLevelCheckBox.checked
                ),
                "window": float(self._cbctWindowSlider.value)
                / self._displaySliderScale,
                "level": float(self._cbctLevelSlider.value)
                / self._displaySliderScale,
                "invertedGrayscale": bool(
                    self.ui.cbctInvertGrayscaleCheckBox.checked
                ),
            }
        )
        return {
            "version": 2,
            "scope": "DENTOWorkflowSceneDisplayParameters",
            "segmentation2DVisible": segmentation2DVisible,
            "segmentation3DVisible": segmentation3DVisible,
            "segmentation2DOpacity": segmentation2DOpacity,
            "segmentation3DOpacity": segmentation3DOpacity,
            "segmentation2DRenderingMode": renderingMode,
            "autoWindowLevel": bool(volumeDisplay["autoWindowLevel"]),
            "window": float(volumeDisplay["window"]),
            "level": float(volumeDisplay["level"]),
            "invertedGrayscale": bool(volumeDisplay["invertedGrayscale"]),
            "interpolate": bool(
                self.logic.getScalarVolumeInterpolation(sourceVolume)
                if sourceVolume
                else self.ui.cbctInterpolationCheckBox.checked
            ),
            "savedUtc": datetime.now(timezone.utc).isoformat(),
        }

    def onSaveSceneDisplayPreset(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode:
            return
        try:
            preset = self._currentSceneDisplayPreset()
            self._parameterNode.sceneDisplayPresetJson = json.dumps(
                preset,
                sort_keys=True,
                separators=(",", ":"),
            )
            self._applySceneDisplayPresetButton.enabled = True
            self._displayPresetStatusLabel.text = _(
                "Node-independent display parameters saved in this MRML scene at %1."
            ).replace("%1", preset["savedUtc"])
            self._displayPresetStatusLabel.styleSheet = "color: #207227;"
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onApplySceneDisplayPreset(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            preset = json.loads(self._parameterNode.sceneDisplayPresetJson)
            if not isinstance(preset, dict) or int(preset.get("version", 0)) not in {1, 2}:
                raise ValueError(_("The saved case display preset is invalid."))
            segmentationNode = self._reviewSegmentationNode
            if not segmentationNode:
                self._displayPresetStatusLabel.text = _(
                    "Display parameters are stored in this scene. Select an "
                    "authoritative segmentation to apply them."
                )
                self._displayPresetStatusLabel.styleSheet = "color: #b36b00;"
                return
            sourceVolume = None
            try:
                sourceVolume = self.logic.getSegmentationSourceVolume(
                    segmentationNode
                )
            except ValueError:
                pass

            activeWorkflowPreset = self._workflowViewActivePresetKey
            activeWorkflowKeys = set(self._workflowViewVisibleKeys)
            if self._workflowViewPriorState:
                self._restoreWorkflowViewState(updateUi=False)
            self.logic.setSegmentationVisibility2D(
                segmentationNode,
                bool(preset["segmentation2DVisible"]),
            )
            self.logic.setSegmentationVisibility3D(
                segmentationNode,
                bool(preset["segmentation3DVisible"]),
            )
            self.logic.setSegmentationOpacity2D(
                segmentationNode,
                float(preset["segmentation2DOpacity"]),
            )
            self.logic.setSegmentationOpacity3D(
                segmentationNode,
                float(preset["segmentation3DOpacity"]),
            )
            self.logic.setSegmentation2DRenderingMode(
                segmentationNode,
                str(preset["segmentation2DRenderingMode"]),
            )
            if sourceVolume:
                if bool(preset["autoWindowLevel"]):
                    self.logic.setScalarVolumeAutoWindowLevel(sourceVolume, True)
                else:
                    self.logic.setScalarVolumeWindowLevel(
                        sourceVolume,
                        float(preset["window"]),
                        float(preset["level"]),
                    )
                self.logic.setScalarVolumeInvertedGrayscale(
                    sourceVolume,
                    bool(preset["invertedGrayscale"]),
                )
                self.logic.setScalarVolumeInterpolation(
                    sourceVolume,
                    bool(preset["interpolate"]),
                )
            if activeWorkflowPreset == "custom":
                self._applyWorkflowViewKeys(
                    activeWorkflowKeys,
                    activePresetKey="custom",
                    updateStatus=False,
                )
            elif activeWorkflowPreset:
                self._applyWorkflowViewPreset(
                    activeWorkflowPreset,
                    updateStatus=False,
                )
            self._syncSegmentationDisplayControls()
            self._displayPresetStatusLabel.text = _(
                "Saved scene display parameters applied; source voxels and masks are unchanged."
                if sourceVolume
                else "Segmentation display parameters applied; CBCT grayscale settings "
                "remain stored until a referenced source volume is available."
            )
            self._displayPresetStatusLabel.styleSheet = "color: #207227;"
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onCbctInvertGrayscaleToggled(self, inverted: bool) -> None:
        if (
            self._updatingSegmentationReviewUI
            or not self._reviewSegmentationNode
            or not self.logic
        ):
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not change the source CBCT grayscale direction.")
        ):
            sourceVolume = self.logic.getSegmentationSourceVolume(
                self._reviewSegmentationNode
            )
            self.logic.setScalarVolumeInvertedGrayscale(
                sourceVolume,
                inverted,
            )
        self._syncSegmentationDisplayControls()

    def onRestoreLoadedCbctDisplay(self) -> None:
        if not self._reviewSegmentationNode or not self.logic:
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not restore the loaded source CBCT display settings.")
        ):
            sourceVolume = self.logic.getSegmentationSourceVolume(
                self._reviewSegmentationNode
            )
            baseline = self._loadedVolumeDisplaySettingsByNodeId.get(
                sourceVolume.GetID()
            )
            if not baseline:
                raise ValueError(
                    _("No loaded display baseline is available for this CBCT.")
                )
            self.logic.restoreScalarVolumeDisplaySettings(
                sourceVolume,
                baseline,
            )
        self._syncSegmentationDisplayControls()
