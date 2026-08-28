"""Extracted view catalog methods; public APIs remain on ViewerWidgetMixin."""

from __future__ import annotations

from .runtime import *


class ViewCatalogWidgetMixin:
    def _workflowViewSupportSegmentIds(self) -> list[str]:
        if not self._parameterNode or not self.logic:
            return []
        try:
            supportIds = self.logic.decodeTemplateSupportSegmentIds(
                self._parameterNode.templateSupportToothSegmentIdsJson
            )
        except ValueError:
            supportIds = []
        sourceModel = self._parameterNode.draftTemplateSupportModel
        if self.logic.isDraftTemplateSupportModelNode(sourceModel):
            try:
                supportIds = self.logic.getDraftTemplateSupportModelSummary(
                    sourceModel
                )["supportSegmentIds"]
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
        targetId = self._parameterNode.targetToothSegmentId
        return [
            segmentId
            for segmentId in supportIds
            if segmentId and segmentId != targetId
        ]

    def _workflowManagedDisplayNodes(self) -> list:
        """Return every user-facing displayable so presets never leave stale objects."""

        nodesById = {}
        if self._parameterNode:
            for fieldName in (
                "targetToothBoundsRoi",
                "trajectoryLine",
                "assistedTrajectoryEntries",
                "targetDockingReferencePlane",
                "targetDockingAssemblyModel",
                "draftTemplateSupportModel",
                "templateSupportBoundaryCurve",
                "templateSupportBoundaryPlane",
                "visibleTemplateSupportModel",
                "templateInsertionDirection",
                "templateUndercutSurfaceModel",
                "templateUndercutBlockoutModel",
                "patientContactShellModel",
                "templateDockingAssemblyModel",
                "templateDockingClearanceModel",
                "templateDockingReinforcementModel",
                "templateDockingChannelsModel",
                "finalPrintableTemplateModel",
                "templateShellRoi",
                "researchTemplateShellModel",
                "researchTemplateSleeveModel",
                "templateTrimPlane",
                "templateTrimCurve",
                "finalizedTemplateShellModel",
                "robotBaseTransform",
                "robotMountPlane",
                "draftPhantomSkullModel",
                "draftPhantomMandibleModel",
                "draftJawLandmarks",
                "draftJawGapLine",
            ):
                node = getattr(self._parameterNode, fieldName, None)
                if node and node.GetID() and node.IsA("vtkMRMLDisplayableNode"):
                    nodesById[node.GetID()] = node
        ownershipAttributes = (
            "DENTOBOT.TrajectoryRole",
            "DENTOBOT.MarkupsRole",
            "DENTOBOT.ModelRole",
            "DENTOBOT.BoundsRole",
        )
        for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode"):
            if node.IsA("vtkMRMLSegmentationNode"):
                continue
            hideFromEditors = getattr(node, "GetHideFromEditors", None)
            if hideFromEditors and hideFromEditors():
                continue
            if not node.GetDisplayNode():
                try:
                    node.CreateDefaultDisplayNodes()
                except Exception:
                    continue
            if node.GetID() and node.GetDisplayNode():
                nodesById[node.GetID()] = node
            if any(node.GetAttribute(attribute) for attribute in ownershipAttributes):
                nodesById[node.GetID()] = node
        if self.logic:
            for node in (
                *self.logic.robotModelNodes(),
                *self.logic.draftPhantomModelNodes(),
            ):
                if node and node.GetID():
                    nodesById[node.GetID()] = node
        try:
            ros_robot = find_ros2_robot_by_name("dentobot")
        except Exception:
            ros_robot = None
        if ros_robot:
            for index in range(ros_robot.GetNumberOfNodeReferences("model")):
                model = ros_robot.GetNthNodeReference("model", index)
                if model and model.GetID() and model.IsA("vtkMRMLDisplayableNode"):
                    nodesById[model.GetID()] = model
        return list(nodesById.values())

    def _workflowCuratedViewEntries(self, stageIndex: int) -> list[dict]:
        if not self._parameterNode or not self.logic or stageIndex < 4:
            return []
        if stageIndex == 10:
            return self._step6WorkflowViewEntries()
        segmentationNode = self._parameterNode.teethSegmentation
        targetId = self._parameterNode.targetToothSegmentId
        supportIds = self._workflowViewSupportSegmentIds()
        entries = []

        def addSegments(key, label, segmentIds, category, stages) -> None:
            if stageIndex not in stages or not segmentationNode:
                return
            segmentation = segmentationNode.GetSegmentation()
            validIds = [
                segmentId
                for segmentId in segmentIds
                if segmentation.GetSegment(segmentId)
            ]
            if validIds:
                entries.append(
                    {
                        "key": key,
                        "label": label,
                        "kind": "segments",
                        "segmentIds": validIds,
                        "category": category,
                    }
                )

        def addNode(key, label, node, category, stages) -> None:
            if (
                stageIndex not in stages
                or not node
                or not node.GetID()
                or not node.GetDisplayNode()
            ):
                return
            entries.append(
                {
                    "key": key,
                    "label": label,
                    "kind": "node",
                    "node": node,
                    "category": category,
                }
            )

        allStageIndices = {4, 5, 6, 7, 8, 9}
        if segmentationNode and targetId:
            targetLabel = targetId
            targetRecord = self._targetToothRecordsById.get(targetId)
            if targetRecord:
                targetLabel = targetRecord["displayName"]
            addSegments(
                "segments:target",
                _("[Mask] Target tooth — %1").replace("%1", targetLabel),
                [targetId],
                "target_mask",
                allStageIndices,
            )
            targetFdi = (
                str(targetRecord.get("fdiNumber") or "")
                if targetRecord
                else ""
            )
            if targetFdi:
                try:
                    detailIds = [
                        record["segmentId"]
                        for record in self.logic.getSegmentationReviewRecords(
                            segmentationNode
                        )
                        if record.get("fdiNumber") == targetFdi
                        and record.get("category") == "Pulp and root canals"
                    ]
                except ValueError:
                    detailIds = []
                addSegments(
                    "segments:targetDetail",
                    _("[Mask] Target pulp / root canal (%1)").replace(
                        "%1", str(len(detailIds))
                    ),
                    detailIds,
                    "target_detail",
                    {4},
                )
        addSegments(
            "segments:support",
            _("[Masks] Selected support teeth (%1)").replace(
                "%1", str(len(supportIds))
            ),
            supportIds,
            "support_mask",
            {5, 6, 7, 8, 9},
        )
        if segmentationNode:
            allSegmentIds = vtk.vtkStringArray()
            segmentationNode.GetSegmentation().GetSegmentIDs(allSegmentIds)
            subjectIds = {targetId, *supportIds}
            otherIds = [
                allSegmentIds.GetValue(index)
                for index in range(allSegmentIds.GetNumberOfValues())
                if allSegmentIds.GetValue(index) not in subjectIds
            ]
            addSegments(
                "segments:other",
                _("[Masks] Other segmented anatomy (%1)").replace(
                    "%1", str(len(otherIds))
                ),
                otherIds,
                "other_mask",
                allStageIndices,
            )

        addNode(
            "node:targetBounds",
            _("[4A] Target bounds box"),
            self._parameterNode.targetToothBoundsRoi,
            "bounds",
            allStageIndices,
        )
        targetTrajectories = []
        if segmentationNode and targetId:
            targetTrajectories = self.logic.dentobotTrajectoriesForTarget(
                segmentationNode,
                targetId,
            )
        for trajectoryNode in targetTrajectories:
            selectedSuffix = (
                _(" — selected")
                if trajectoryNode is self._parameterNode.trajectoryLine
                else ""
            )
            addNode(
                f"trajectory:{trajectoryNode.GetID()}",
                _("[4A] %1%2")
                .replace("%1", trajectoryNode.GetName() or _("Trajectory"))
                .replace("%2", selectedSuffix),
                trajectoryNode,
                "trajectory",
                allStageIndices,
            )
        addNode(
            "node:assistedEntries",
            _("[4A] Assisted crown entry points"),
            self._parameterNode.assistedTrajectoryEntries,
            "assisted",
            {4},
        )
        addNode(
            "node:targetDockingPlane",
            _("[4C] Occlusal reference plane"),
            self._parameterNode.targetDockingReferencePlane,
            "target_docking",
            {6, 7, 8, 9},
        )
        addNode(
            "node:targetDockingAssembly",
            _("[4C] Guide rails / four docks"),
            self._parameterNode.targetDockingAssemblyModel,
            "target_docking",
            {6, 7, 8, 9},
        )
        dockingAssembly = self._parameterNode.targetDockingAssemblyModel
        if dockingAssembly:
            role = self.logic.TARGET_DOCKING_MEASUREMENT_REFERENCE_ROLE
            for index in range(dockingAssembly.GetNumberOfNodeReferences(role)):
                measurementNode = dockingAssembly.GetNthNodeReference(role, index)
                addNode(
                    f"targetDockingMeasurement:{measurementNode.GetID()}"
                    if measurementNode
                    else f"targetDockingMeasurement:{index}",
                    measurementNode.GetName()
                    if measurementNode
                    else _("[4B] Dock measurement"),
                    measurementNode,
                    "target_docking_measurement",
                    {6, 7, 8, 9},
                )
        addNode(
            "node:draftSupport",
            _("[4B] Complete support-tooth draft"),
            self._parameterNode.draftTemplateSupportModel,
            "draft_support",
            {5, 6, 7},
        )
        addNode(
            "node:supportBoundary",
            _("[5A] Support boundary"),
            self._parameterNode.templateSupportBoundaryCurve,
            "support_boundary",
            {7, 8},
        )
        addNode(
            "node:supportPlane",
            _("[5A] Automatic support plane"),
            self._parameterNode.templateSupportBoundaryPlane,
            "support_plane",
            {7},
        )
        addNode(
            "node:visibleSupport",
            _("[5A] Visible support preview"),
            self._parameterNode.visibleTemplateSupportModel,
            "visible_support",
            {7, 8, 9},
        )
        addNode(
            "node:insertionDirection",
            _("[5B] Insertion direction"),
            self._parameterNode.templateInsertionDirection,
            "insertion",
            {8},
        )
        addNode(
            "node:undercut",
            _("[5B] Undercut preview"),
            self._parameterNode.templateUndercutSurfaceModel,
            "undercut",
            {8},
        )
        addNode(
            "node:blockout",
            _("[5B] Directional blockout"),
            self._parameterNode.templateUndercutBlockoutModel,
            "blockout",
            {8},
        )
        addNode(
            "node:patientShell",
            _("[5B] Patient-contact shell"),
            self._parameterNode.patientContactShellModel,
            "patient_shell",
            {8, 9},
        )
        for keySuffix, label, node in (
            (
                "dockingFusion",
                _("[5B] Integrated docking assembly"),
                self._parameterNode.templateDockingAssemblyModel,
            ),
            (
                "dockingClearance",
                _("[5B] Docking clearance"),
                self._parameterNode.templateDockingClearanceModel,
            ),
            (
                "reinforcement",
                _("[5B] Shell reinforcement"),
                self._parameterNode.templateDockingReinforcementModel,
            ),
            (
                "channels",
                _("[5B] Drill / dock channels"),
                self._parameterNode.templateDockingChannelsModel,
            ),
        ):
            addNode(
                f"node:{keySuffix}",
                label,
                node,
                "final_aux",
                {8, 9},
            )
        addNode(
            "node:finalTemplate",
            _("[5C] Final printable template"),
            self._parameterNode.finalPrintableTemplateModel,
            "final",
            {8, 9},
        )
        return entries

    def _workflowViewEntries(self, stageIndex: int) -> list[dict]:
        """Return grouped masks and existing display objects without scene mutation."""

        if not self._parameterNode or not self.logic:
            return []
        curated = list(self._workflowCuratedViewEntries(stageIndex))
        entries = list(curated)

        for segmentationNode in slicer.util.getNodesByClass(
            "vtkMRMLSegmentationNode"
        ):
            segmentationRole = str(
                segmentationNode.GetAttribute("DENTOBOT.SegmentationRole") or ""
            )
            step6DerivedAnatomy = segmentationRole in {
                self.logic.STEP6_FIXED_UPPER_ANATOMY_ROLE,
                self.logic.STEP6_MOVING_LOWER_ANATOMY_ROLE,
                self.logic.STEP6_TARGET_JAW_FALLBACK_ANATOMY_ROLE,
            }
            segmentation = segmentationNode.GetSegmentation()
            if not segmentation:
                continue
            segmentIds = vtk.vtkStringArray()
            segmentation.GetSegmentIDs(segmentIds)
            records = []
            for segmentIndex in range(segmentIds.GetNumberOfValues()):
                segmentId = segmentIds.GetValue(segmentIndex)
                segment = segmentation.GetSegment(segmentId)
                if not segment:
                    continue
                records.append(
                    {
                        "segmentId": segmentId,
                        **self.logic.describeSegmentForReview(
                            segment.GetName() or segmentId
                        ),
                    }
                )
            for groupKey, groupedIds in group_segmentation_records_detailed(
                records
            ).items():
                if not groupedIds:
                    continue
                authoritative = (
                    segmentationNode is self._parameterNode.teethSegmentation
                )
                entries.append(
                    {
                        "key": (
                            f"segments:anatomy:{groupKey}:{segmentationNode.GetID()}"
                        ),
                        "label": _("[%1] %2 (%3) — %4")
                        .replace(
                            "%1",
                            _("Dental mask group")
                            if authoritative
                            else _("Step 6 derived anatomy")
                            if step6DerivedAnatomy
                            else _("Other scene mask group"),
                        )
                        .replace(
                            "%2",
                            _(DETAILED_ANATOMY_GROUP_LABELS[groupKey]),
                        )
                        .replace("%3", str(len(groupedIds)))
                        .replace(
                            "%4",
                            segmentationNode.GetName() or _("Segmentation"),
                        ),
                        "kind": "segments",
                        "segmentationNode": segmentationNode,
                        "segmentIds": groupedIds,
                        "category": (
                            DETAILED_ANATOMY_GROUP_CATEGORY[groupKey]
                            if authoritative
                            else "case_jaw_opening"
                            if step6DerivedAnatomy
                            else "scene_mask"
                        ),
                        "anatomyGroup": groupKey,
                        "anatomyScopes": (
                            anatomy_scopes_for_group(groupKey)
                            if authoritative
                            else frozenset()
                        ),
                    }
                )

        representedNodeIds = set()
        for entry in entries:
            if entry["kind"] == "node" and entry.get("node"):
                representedNodeIds.add(entry["node"].GetID())
            elif entry["kind"] == "nodes":
                representedNodeIds.update(
                    node.GetID() for node in entry["nodes"] if node and node.GetID()
                )
        for node in self._workflowManagedDisplayNodes():
            if node.GetID() in representedNodeIds:
                continue
            classLabel = node.GetClassName().replace("vtkMRML", "").replace("Node", "")
            scalarVolume = node.IsA("vtkMRMLScalarVolumeNode")
            category = (
                "case_volume"
                if scalarVolume and node is self._parameterNode.inputVolume
                else "scene_volume"
                if scalarVolume
                else "scene_element"
            )
            labelPrefix = (
                _("Case CBCT")
                if category == "case_volume"
                else _("Other scene volume")
                if category == "scene_volume"
                else _("Scene/%1").replace("%1", classLabel)
            )
            entries.append(
                {
                    "key": f"scene:{node.GetID()}",
                    "label": _("[%1] %2")
                    .replace("%1", labelPrefix)
                    .replace("%2", node.GetName() or node.GetID()),
                    "kind": "node",
                    "node": node,
                    "category": category,
                }
            )
        volumeRenderingLogic = (
            slicer.modules.volumerendering.logic()
            if hasattr(slicer.modules, "volumerendering")
            else None
        )
        if volumeRenderingLogic:
            for volumeNode in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
                try:
                    renderingDisplay = (
                        volumeRenderingLogic.GetFirstVolumeRenderingDisplayNode(
                            volumeNode
                        )
                    )
                except Exception:
                    renderingDisplay = None
                if renderingDisplay:
                    entries.append(
                        {
                            "key": f"volumeRendering:{volumeNode.GetID()}",
                            "label": _("[Volume rendering — not a mask] %1").replace(
                                "%1", volumeNode.GetName() or volumeNode.GetID()
                            ),
                            "kind": "volume_rendering",
                            "node": volumeNode,
                            "displayNode": renderingDisplay,
                            "category": (
                                "case_volume_3d"
                                if volumeNode is self._parameterNode.inputVolume
                                else "scene_volume_rendering"
                            ),
                        }
                    )
        return entries

    def _step6WorkflowViewEntries(self) -> list[dict]:
        """Step 6 Elements list: case package, phantom, robot, mount — not the full 4A–5C dump."""
        entries: list[dict] = []
        parameterNode = self._parameterNode
        segmentationNode = parameterNode.teethSegmentation
        targetId = parameterNode.targetToothSegmentId

        def addSegments(key, label, segmentIds, category) -> None:
            if not segmentationNode:
                return
            segmentation = segmentationNode.GetSegmentation()
            validIds = [
                segmentId
                for segmentId in segmentIds
                if segmentation.GetSegment(segmentId)
            ]
            if validIds:
                entries.append(
                    {
                        "key": key,
                        "label": label,
                        "kind": "segments",
                        "segmentIds": validIds,
                        "category": category,
                    }
                )

        def addNode(key, label, node, category) -> None:
            if not node or not node.GetID():
                return
            if not node.GetDisplayNode():
                try:
                    node.CreateDefaultDisplayNodes()
                except Exception:
                    return
            if not node.GetDisplayNode():
                return
            entries.append(
                {
                    "key": key,
                    "label": label,
                    "kind": "node",
                    "node": node,
                    "category": category,
                }
            )

        def addNodes(key, label, nodes, category) -> None:
            valid = []
            for node in nodes:
                if not node or not node.GetID():
                    continue
                if not node.GetDisplayNode():
                    try:
                        node.CreateDefaultDisplayNodes()
                    except Exception:
                        continue
                if node.GetDisplayNode():
                    valid.append(node)
            if not valid:
                return
            entries.append(
                {
                    "key": key,
                    "label": label,
                    "kind": "nodes",
                    "nodes": valid,
                    "category": category,
                }
            )

        if segmentationNode and targetId:
            targetLabel = targetId
            targetRecord = self._targetToothRecordsById.get(targetId)
            if targetRecord:
                targetLabel = targetRecord["displayName"]
            addSegments(
                "segments:target",
                _("[Mask] Target tooth — %1").replace("%1", targetLabel),
                [targetId],
                "target_mask",
            )
        if parameterNode.trajectoryLine:
            addNode(
                "node:step6Trajectory",
                _("[4A] Selected trajectory"),
                parameterNode.trajectoryLine,
                "trajectory",
            )
        addNode(
            "node:step6Volume",
            _("[1] CBCT volume"),
            parameterNode.inputVolume,
            "case_volume",
        )
        addNode(
            "node:step6Bounds",
            _("[4A] Target tooth bounds"),
            parameterNode.targetToothBoundsRoi,
            "bounds",
        )
        addNode(
            "node:step6Docks",
            _("[4C] Guide rails / docks"),
            parameterNode.targetDockingAssemblyModel,
            "target_docking",
        )
        addNode(
            "node:step6Template",
            _("[5C] Final printable template"),
            parameterNode.finalPrintableTemplateModel,
            "final",
        )
        addNode(
            "node:step6CaseLowerJaw",
            _("[Step 6.0A] Opened lower-jaw planning surface"),
            parameterNode.step6OpenedLowerJawModel,
            "case_jaw_opening",
        )
        addNode(
            "node:step6FixedUpperAnatomy",
            _("[Step 6.0A] Fixed upper jaw + teeth"),
            parameterNode.step6FixedUpperAnatomy,
            "case_jaw_opening",
        )
        addNode(
            "node:step6MovingLowerAnatomy",
            _("[Step 6.0A] Moving lower jaw + teeth"),
            parameterNode.step6MovingLowerAnatomy,
            "case_jaw_opening",
        )
        addNode(
            "node:step6TargetJawFallbackAnatomy",
            _("[Step 6.0A fallback] Unopened target jaw + teeth (placement only)"),
            parameterNode.step6TargetJawFallbackAnatomy,
            "case_jaw_opening",
        )
        addNode(
            "node:step6CaseOpenedTargetGeometry",
            _("[Step 6.0A] Opened target-attached geometry"),
            parameterNode.step6OpenedTargetGeometryModel,
            "case_jaw_opening",
        )
        addNode(
            "node:step6CaseOpenedTrajectory",
            _("[Step 6.0A] Opened Entry-to-Target"),
            parameterNode.step6OpenedTrajectoryLine,
            "case_jaw_opening",
        )
        addNode(
            "node:step6CaseJawLandmarks",
            _("[Step 6.0A] Case TMJ/incisor landmarks"),
            parameterNode.step6CaseJawLandmarks,
            "case_jaw_opening",
        )
        addNode(
            "node:step6CaseJawGap",
            _("[Step 6.0A] Case incisor gap"),
            parameterNode.step6CaseJawGapLine,
            "case_jaw_opening",
        )
        addNodes(
            "nodes:step6Phantom",
            _("[Step 6] Draft phantom"),
            self.logic.draftPhantomModelNodes(),
            "phantom",
        )
        addNode(
            "node:step6JawLandmarks",
            _("[Step 6] Jaw landmarks"),
            parameterNode.draftJawLandmarks,
            "phantom_landmarks",
        )
        addNode(
            "node:step6JawGap",
            _("[Step 6] Incisor gap line"),
            parameterNode.draftJawGapLine,
            "phantom_landmarks",
        )
        addNode(
            "node:step6Mount",
            _("[Step 6] Mount plane"),
            parameterNode.robotMountPlane,
            "robot_mount",
        )
        addNode(
            "node:step6ForeheadProxy",
            _("[Step 6] Forehead proxy — unregistered / visualization only"),
            parameterNode.robotForeheadProxyModel,
            "forehead_proxy",
        )
        addNodes(
            "nodes:step6MrmlRobot",
            _("[Step 6] MRML robot links"),
            self.logic.robotModelNodes(),
            "robot_mrml",
        )
        try:
            ros_robot = find_ros2_robot_by_name("dentobot")
        except Exception:
            ros_robot = None
        if ros_robot is not None:
            ros_models = [
                ros_robot.GetNthNodeReference("model", index)
                for index in range(ros_robot.GetNumberOfNodeReferences("model"))
            ]
            addNodes(
                "nodes:step6RosRobot",
                _("[Step 6] ROS robot"),
                ros_models,
                "robot_ros",
            )
            goal_models = [
                ros_robot.GetNthNodeReference("goal_model", index)
                for index in range(ros_robot.GetNumberOfNodeReferences("goal_model"))
            ]
            addNodes(
                "nodes:step6GoalRobot",
                _("[Step 6] Goal robot"),
                goal_models,
                "robot_goal",
            )
        return entries

    @staticmethod
    def _workflowViewPresetCategories(presetKey: str) -> set[str] | None:
        categories = {
            "cbct_slices": {"case_volume"},
            "teeth_upper_both": {"upper_teeth"},
            "teeth_lower_both": {"lower_teeth"},
            "teeth_all_both": {"upper_teeth", "lower_teeth"},
            "all_masks": {
                "upper_teeth",
                "lower_teeth",
                "pulp_root_canals",
                "neural_canals",
                "jaws",
                "sinuses_airway",
                "restorations_implants",
                "other_mask",
            },
            "target_only": {"target_mask"},
            "trajectory_only": {
                "target_mask",
                "target_detail",
                "trajectory",
            },
            "plan": {"target_mask", "bounds", "trajectory", "assisted"},
            "support_masks": {"target_mask", "support_mask"},
            "support_design": {
                "target_mask",
                "support_mask",
                "draft_support",
                "support_boundary",
                "support_plane",
                "visible_support",
            },
            "docks_only": {"target_docking", "target_docking_measurement"},
            "undercut_analysis": {
                "visible_support",
                "insertion",
                "undercut",
                "blockout",
            },
            "shell_only": {"patient_shell"},
            "shell_guides": {
                "patient_shell",
                "trajectory",
                "target_docking",
                "final_aux",
            },
            "final_only": {"final"},
            "robot_mount_only": {
                "robot_mrml", "robot_ros", "robot_goal", "robot_mount", "forehead_proxy"
            },
            "case_package": {
                "case_volume",
                "target_mask",
                "bounds",
                "trajectory",
                "target_docking",
                "final",
                "case_jaw_opening",
            },
            "phantom_only": {"phantom", "phantom_landmarks"},
        }
        return categories.get(presetKey)

    def _workflowViewRecommendedCategories(self, stageIndex: int) -> set[str]:
        categories = recommended_view_categories(stageIndex)
        if stageIndex == 7:
            if not self._parameterNode.visibleTemplateSupportModel:
                categories.add("draft_support")
            return categories
        if stageIndex == 8:
            if self._parameterNode.finalPrintableTemplateModel:
                return {"final"}
            return categories
        if stageIndex == 9:
            return (
                {"final"}
                if self._parameterNode.finalPrintableTemplateModel
                else categories
            )
        if stageIndex == 10:
            ros_active = self.logic.isRos2MotionControlActive(
                self._parameterNode.robotBaseTransform
            )
            robot_category = {"robot_ros"} if ros_active else {"robot_mrml"}
            kind = self._step6SceneKind()
            if kind == "phantom":
                categories = {"phantom", "robot_mount", *robot_category}
                landmarks = self._parameterNode.draftJawLandmarks
                if landmarks is None or landmarks.GetNumberOfDefinedControlPoints() < 4:
                    categories.add("phantom_landmarks")
                return categories
            if (
                str(self._parameterNode.step6CaseJawPreparationMode)
                == "TargetJawFallback"
                and not self.logic.step6TargetJawFallbackFreshnessIssues(
                    self._parameterNode
                )
            ):
                # Placement-only review needs a legible jaw/robot composition,
                # not the template, docks, ROI, and every historical planning
                # overlay.  Operators can still add any of those through Views.
                return {
                    "case_volume",
                    "case_volume_3d",
                    "case_jaw_opening",
                    "trajectory",
                    "robot_mount",
                    "forehead_proxy",
                    *robot_category,
                }
            return {
                "case_volume",
                "case_volume_3d",
                "target_mask",
                "bounds",
                "trajectory",
                "target_docking",
                "final",
                "case_jaw_opening",
                "robot_mount",
                "forehead_proxy",
                *robot_category,
            }
        return categories

    def _workflowViewPresetDefinitions(
        self,
        stageIndex: int,
        entries: list[dict],
    ) -> list[tuple[str, str]]:
        categories = {entry["category"] for entry in entries}
        definitions = [
            ("scene", _("Current scene visibility (unchanged)")),
            ("recommended", _("Recommended for this step")),
        ]
        if "case_volume" in categories:
            definitions.append(("cbct_slices", _("CBCT slices only")))
        if "upper_teeth" in categories:
            definitions.append(
                ("teeth_upper_both", _("Upper teeth masks — 2D + 3D"))
            )
        if "lower_teeth" in categories:
            definitions.append(
                ("teeth_lower_both", _("Lower teeth masks — 2D + 3D"))
            )
        if categories & {"upper_teeth", "lower_teeth"}:
            definitions.append(
                ("teeth_all_both", _("All teeth masks — 2D + 3D"))
            )
        if categories & {
            "pulp_root_canals",
            "neural_canals",
            "jaws",
            "sinuses_airway",
            "restorations_implants",
            "other_mask",
        }:
            definitions.append(("all_masks", _("All segmentation masks")))
        if "target_mask" in categories:
            definitions.append(("target_only", _("Target tooth mask only")))
        if stageIndex == 4 and "trajectory" in categories:
            definitions.append(
                ("trajectory_only", _("Selected trajectory context only"))
            )
        if categories & {"trajectory", "bounds", "assisted"}:
            definitions.append(("plan", _("Target + trajectory planning")))
        if "support_mask" in categories:
            definitions.append(("support_masks", _("Target + support masks only")))
        if categories & {
            "support_boundary",
            "support_plane",
            "visible_support",
        }:
            definitions.append(("support_design", _("Support-surface design")))
        if "target_docking" in categories:
            definitions.append(("docks_only", _("Guide rails / docks only")))
        if categories & {"undercut", "blockout", "insertion"}:
            definitions.append(("undercut_analysis", _("Undercut analysis only")))
        if "patient_shell" in categories:
            definitions.append(("shell_only", _("Patient-contact shell only")))
            definitions.append(("shell_guides", _("Shell + trajectories + guides")))
        if "final" in categories:
            definitions.append(("final_only", _("Final printable template only")))
        if stageIndex == 10:
            definitions.append(("robot_mount_only", _("Robot + mount only")))
            if categories & {"target_mask", "trajectory", "target_docking", "final"}:
                definitions.append(
                    ("case_package", _("Case planning package"))
                )
            if "phantom" in categories:
                definitions.append(("phantom_only", _("Phantom only")))
        definitions.extend(
            (
                ("all", _("All elements available in this step")),
                ("custom", _("Custom element selection")),
            )
        )
        return definitions

    def _workflowViewKeysForPreset(
        self,
        presetKey: str,
        entries: list[dict],
        stageIndex: int,
    ) -> set[str]:
        if presetKey == "all":
            return {entry["key"] for entry in entries}
        if presetKey == "recommended":
            categories = self._workflowViewRecommendedCategories(stageIndex)
        else:
            categories = self._workflowViewPresetCategories(presetKey) or set()
        visibleKeys = {
            entry["key"]
            for entry in entries
            if entry["category"] in categories
        }
        if (
            self._parameterNode
            and not self._parameterNode.targetDockingMeasurementsVisible
        ):
            visibleKeys = {
                entry["key"]
                for entry in entries
                if entry["key"] in visibleKeys
                and entry["category"] != "target_docking_measurement"
            }
        if presetKey == "trajectory_only":
            selectedTrajectory = (
                self._parameterNode.trajectoryLine
                if self._parameterNode
                else None
            )
            visibleKeys = {
                entry["key"]
                for entry in entries
                if entry["key"] in visibleKeys
                and (
                    entry["category"] != "trajectory"
                    or entry.get("node") is selectedTrajectory
                )
            }
        if (
            presetKey == "recommended"
            and stageIndex == 4
            and not self._parameterNode.assistedTrajectoryEntries
        ):
            selectedTrajectory = (
                self._parameterNode.trajectoryLine
                if self._parameterNode
                else None
            )
            visibleKeys = {
                entry["key"]
                for entry in entries
                if entry["key"] in visibleKeys
                and (
                    entry["category"] != "trajectory"
                    or entry.get("node") is selectedTrajectory
                )
            }
        return visibleKeys
