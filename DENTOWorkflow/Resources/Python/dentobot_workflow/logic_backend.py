"""Extracted volume metadata and backend commands methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class BackendLogicMixin:
    @classmethod
    def launcherBackendConfiguration(
        cls,
        environment: dict | None = None,
    ) -> tuple[str, str, str, str, str]:
        """Return the shared launcher contract without persisting it in MRML."""

        configuration = launcher_backend_configuration(environment)
        return (
            configuration.execution_mode,
            configuration.distribution,
            configuration.python_path,
            configuration.artifact_root,
            configuration.device,
        )

    @staticmethod
    def launcherBackendConfigurationIsComplete(
        executionMode: str,
        distribution: str,
        pythonPath: str,
        artifactRoot: str,
        device: str,
    ) -> bool:
        mode = executionMode.strip().lower()
        return bool(
            mode in SUPPORTED_EXECUTION_MODES
            and pythonPath.strip()
            and artifactRoot.strip()
            and device.strip().lower() in SUPPORTED_BACKEND_DEVICES
            and (mode != "wsl" or distribution.strip())
        )

    @classmethod
    def resolveBackendConfiguration(
        cls,
        executionMode: str,
        distribution: str,
        pythonPath: str,
        stagingRoot: str,
        device: str,
        useLauncherConfiguration: bool,
        environment: dict | None = None,
    ) -> tuple[str, str, str, str, str]:
        """Resolve portable launcher settings or explicit scene overrides."""

        executionMode = executionMode.strip()
        distribution = distribution.strip()
        pythonPath = pythonPath.strip()
        stagingRoot = stagingRoot.strip()
        device = device.strip()
        if useLauncherConfiguration:
            (
                launcherMode,
                launcherDistribution,
                launcherPython,
                launcherStagingRoot,
                launcherDevice,
            ) = (
                cls.launcherBackendConfiguration(environment)
            )
            if cls.launcherBackendConfigurationIsComplete(
                launcherMode,
                launcherDistribution,
                launcherPython,
                launcherStagingRoot,
                launcherDevice,
            ):
                executionMode = launcherMode
                distribution = launcherDistribution
                pythonPath = launcherPython
                stagingRoot = launcherStagingRoot
                device = launcherDevice
            else:
                executionMode = ""
                distribution = ""
                pythonPath = ""
                stagingRoot = ""
                device = ""
        return (
            executionMode,
            distribution,
            pythonPath,
            stagingRoot,
            device,
        )

    def getVolumeMetadata(self, volumeNode: vtkMRMLScalarVolumeNode) -> dict[str, str]:
        if not volumeNode or not volumeNode.IsA("vtkMRMLScalarVolumeNode"):
            raise ValueError(_("Select a valid scalar CBCT volume."))

        imageData = volumeNode.GetImageData()
        if not imageData:
            raise ValueError(_("The selected volume does not contain image data."))

        dimensions = tuple(int(value) for value in imageData.GetDimensions())
        spacing = tuple(float(value) for value in volumeNode.GetSpacing())
        if any(value <= 0 for value in dimensions) or any(not math.isfinite(value) or value <= 0 for value in spacing):
            raise ValueError(_("The selected volume has invalid dimensions or spacing."))

        ijkToRas = vtk.vtkMatrix4x4()
        volumeNode.GetIJKToRASMatrix(ijkToRas)
        determinant = ijkToRas.Determinant()
        if not math.isfinite(determinant) or abs(determinant) < 1e-12:
            raise ValueError(_("The selected volume has invalid IJK-to-RAS geometry."))

        scalarRange = imageData.GetScalarRange()
        orientation = self._orientationDescription(ijkToRas)
        parentTransform = volumeNode.GetParentTransformNode()
        geometryStatus = _("Valid IJK-to-RAS geometry")
        if parentTransform:
            geometryStatus += _("; parent transform present")

        return {
            "name": volumeNode.GetName() or _("Unnamed volume"),
            "dimensions": f"{dimensions[0]} x {dimensions[1]} x {dimensions[2]} voxels",
            "spacing": f"{spacing[0]:.3f} x {spacing[1]:.3f} x {spacing[2]:.3f} mm",
            "scalarType": imageData.GetScalarTypeAsString(),
            "scalarRange": f"{scalarRange[0]:.3f} to {scalarRange[1]:.3f}",
            "orientation": orientation,
            "geometryStatus": geometryStatus,
        }

    @staticmethod
    def validateWindowsStagingRoot(stagingRoot: str) -> Path:
        """Validate an explicit local Windows drive path used for run artifacts."""

        if not stagingRoot:
            raise ValueError(_("Enter a Windows staging directory."))
        if stagingRoot.startswith("\\\\") or stagingRoot.startswith("//"):
            raise ValueError(
                _("UNC/network paths are not supported by the baseline WSL bridge.")
            )
        if not re.match(r"^[A-Za-z]:[\\/]", stagingRoot):
            raise ValueError(
                _("Use an absolute Windows drive path such as C:\\DENTOBOTRuns.")
            )
        return Path(stagingRoot)

    @staticmethod
    def validateStagingRoot(stagingRoot: str, executionMode: str) -> Path:
        """Validate the artifact root for the selected process boundary."""

        if executionMode == "wsl":
            return DENTOWorkflowLogic.validateWindowsStagingRoot(stagingRoot)
        if executionMode != "local":
            raise ValueError(_("Unsupported backend execution mode."))
        if not stagingRoot:
            raise ValueError(_("Enter an absolute Linux staging directory."))
        rootPath = Path(stagingRoot)
        if not rootPath.is_absolute():
            raise ValueError(_("Use an absolute Linux staging directory."))
        return rootPath

    @staticmethod
    def windowsPathToWslPath(windowsPath: str | Path) -> str:
        """Map an absolute Windows drive path to WSL's conventional /mnt path."""

        return windows_path_to_wsl_path(windowsPath)

    @staticmethod
    def _wslExecutablePath() -> str:
        systemRoot = os.environ.get("SystemRoot", r"C:\Windows")
        return str(Path(systemRoot) / "System32" / "wsl.exe")

    def _buildWslPythonCommand(
        self,
        distribution: str,
        pythonPath: str,
        backendArguments: list[str],
    ) -> list[str]:
        return build_backend_python_command(
            execution_mode="wsl",
            distribution=distribution,
            python_path=pythonPath,
            backend_module=self.BACKEND_MODULE,
            backend_arguments=backendArguments,
            wsl_executable=self._wslExecutablePath(),
        )

    def _buildBackendPythonCommand(
        self,
        executionMode: str,
        distribution: str,
        pythonPath: str,
        backendArguments: list[str],
    ) -> list[str]:
        return build_backend_python_command(
            execution_mode=executionMode,
            distribution=distribution,
            python_path=pythonPath,
            backend_module=self.BACKEND_MODULE,
            backend_arguments=backendArguments,
            wsl_executable=self._wslExecutablePath(),
        )

    @staticmethod
    def _backendVisiblePath(path: Path, executionMode: str) -> str:
        if executionMode == "wsl":
            return DENTOWorkflowLogic.windowsPathToWslPath(path)
        if executionMode == "local":
            return str(path)
        raise ValueError(_("Unsupported backend execution mode."))

    def buildHealthCommand(
        self,
        distribution: str,
        pythonPath: str,
        executionMode: str = "wsl",
        device: str = "cuda:0",
    ) -> list[str]:
        """Build Bridge A without invoking a shell or activating an environment."""

        return self._buildBackendPythonCommand(
            executionMode,
            distribution,
            pythonPath,
            ["health", "--json", "--require-device", device],
        )

    def buildRoundTripCommand(
        self,
        distribution: str,
        pythonPath: str,
        inputPath: Path,
        outputPath: Path,
        resultJsonPath: Path,
        runId: str,
        executionMode: str = "wsl",
    ) -> list[str]:
        """Build Bridge B with explicit arguments and WSL-visible artifact paths."""

        return self._buildBackendPythonCommand(
            executionMode,
            distribution,
            pythonPath,
            [
                "roundtrip",
                "--input",
                self._backendVisiblePath(inputPath, executionMode),
                "--output",
                self._backendVisiblePath(outputPath, executionMode),
                "--result-json",
                self._backendVisiblePath(resultJsonPath, executionMode),
                "--run-id",
                runId,
            ],
        )

    def buildTeethSegmentationCommand(
        self,
        distribution: str,
        pythonPath: str,
        inputPath: Path,
        outputPath: Path,
        resultJsonPath: Path,
        runId: str,
        executionMode: str = "wsl",
        device: str = "cuda:0",
    ) -> list[str]:
        """Build Bridge C without shell activation or implicit CPU fallback."""

        return self._buildBackendPythonCommand(
            executionMode,
            distribution,
            pythonPath,
            [
                "segment-teeth",
                "--input",
                self._backendVisiblePath(inputPath, executionMode),
                "--output",
                self._backendVisiblePath(outputPath, executionMode),
                "--result-json",
                self._backendVisiblePath(resultJsonPath, executionMode),
                "--run-id",
                runId,
                "--device",
                device,
            ],
        )

    def createRoundTripRunPaths(
        self,
        stagingRoot: str,
        runId: str,
        executionMode: str = "wsl",
    ) -> dict[str, Path]:
        """Create one isolated artifact directory for a bridge run."""

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", runId):
            raise ValueError(_("The generated run ID is invalid."))
        rootPath = self.validateStagingRoot(stagingRoot, executionMode)
        runDirectory = rootPath / runId
        runDirectory.mkdir(parents=True, exist_ok=False)
        return {
            "directory": runDirectory,
            "input": runDirectory / "input.nii",
            "output": runDirectory / "roundtrip.nii",
            "result": runDirectory / "result.json",
        }

    def createTeethSegmentationRunPaths(
        self,
        stagingRoot: str,
        runId: str,
        executionMode: str = "wsl",
    ) -> dict[str, Path]:
        """Create one isolated artifact directory for a Bridge C inference."""

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", runId):
            raise ValueError(_("The generated run ID is invalid."))
        rootPath = self.validateStagingRoot(stagingRoot, executionMode)
        runDirectory = rootPath / runId
        runDirectory.mkdir(parents=True, exist_ok=False)
        return {
            "directory": runDirectory,
            "input": runDirectory / "input.nii",
            "output": runDirectory / "teeth-segmentation.nii",
            "result": runDirectory / "result.json",
        }

    @staticmethod
    def findJsonReport(lines: list[str], command: str) -> dict | None:
        """Find the last structured backend report among process output lines."""

        for line in reversed(lines):
            try:
                document = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(document, dict) and document.get("command") == command:
                return document
        return None

    @staticmethod
    def validateTeethSegmentationReport(
        report: dict,
        runId: str,
        expectedDevice: str | None = None,
    ) -> None:
        """Validate the schema before any returned label map enters MRML."""

        if not isinstance(report, dict):
            raise ValueError(_("The backend segmentation report is not a JSON object."))
        if (
            report.get("schemaVersion") != "1.0"
            or report.get("command") != "segment-teeth"
        ):
            raise ValueError(_("The backend segmentation contract is not supported."))
        if report.get("runId") != runId:
            raise ValueError(_("The segmentation result run ID does not match."))
        if report.get("status") not in ("ok", "error"):
            raise ValueError(_("The segmentation report has an invalid status."))
        if not isinstance(report.get("errors"), list):
            raise ValueError(_("The segmentation report error list is invalid."))
        if report.get("status") != "ok":
            return

        if not report.get("geometryMatch"):
            raise ValueError(_("Backend segmentation geometry validation did not pass."))
        if not report.get("labelValidationPassed"):
            raise ValueError(_("Backend segmentation label validation did not pass."))

        model = report.get("model")
        device = report.get("device")
        labels = report.get("labels")
        metrics = report.get("metrics")
        backend = report.get("backend")
        if not isinstance(model, dict) or model.get("task") != "teeth":
            raise ValueError(_("The backend did not report the required teeth model."))
        if model.get("taskId") != 113 or model.get("cropTaskId") != 115:
            raise ValueError(_("The backend model task identifiers are unexpected."))
        if not isinstance(device, dict):
            raise ValueError(_("The segmentation device metadata is missing."))
        requestedDevice = device.get("requested")
        actualDevice = device.get("actual")
        if (
            requestedDevice not in ("cpu", "cuda:0")
            or actualDevice != requestedDevice
            or (expectedDevice and requestedDevice != expectedDevice)
        ):
            raise ValueError(_("The segmentation device does not match the request."))
        if (
            not isinstance(backend, dict)
            or not isinstance(backend.get("packages"), dict)
            or not backend["packages"].get("TotalSegmentator")
        ):
            raise ValueError(_("TotalSegmentator version metadata is missing."))
        if not isinstance(labels, list) or not labels:
            raise ValueError(_("The TotalSegmentator teeth label map is missing."))
        if not isinstance(metrics, dict):
            raise ValueError(_("Segmentation metrics are missing."))

        labelIds = []
        for label in labels:
            if (
                not isinstance(label, dict)
                or not isinstance(label.get("id"), int)
                or label["id"] <= 0
                or not isinstance(label.get("name"), str)
                or not label["name"]
            ):
                raise ValueError(_("The segmentation label map is invalid."))
            labelIds.append(label["id"])
        if len(labelIds) != len(set(labelIds)):
            raise ValueError(_("The segmentation label map contains duplicate IDs."))
        labelNamesById = {
            int(label["id"]): str(label["name"])
            for label in labels
        }

        detectedLabelIds = metrics.get("detectedLabelIds")
        segmentCount = metrics.get("segmentCount")
        if (
            not isinstance(detectedLabelIds, list)
            or not detectedLabelIds
            or any(
                not isinstance(labelId, int) or labelId not in labelIds
                for labelId in detectedLabelIds
            )
            or len(detectedLabelIds) != len(set(detectedLabelIds))
        ):
            raise ValueError(_("Detected segmentation label IDs are invalid."))
        if segmentCount != len(detectedLabelIds):
            raise ValueError(_("The reported segmentation count is inconsistent."))
        perLabel = metrics.get("perLabel")
        if not isinstance(perLabel, list) or len(perLabel) != segmentCount:
            raise ValueError(_("Per-label segmentation metrics are inconsistent."))
        perLabelIds = []
        for labelMetric in perLabel:
            if (
                not isinstance(labelMetric, dict)
                or labelMetric.get("id") not in detectedLabelIds
                or labelMetric.get("name")
                != labelNamesById.get(labelMetric.get("id"))
                or not isinstance(labelMetric.get("voxelCount"), int)
                or labelMetric["voxelCount"] <= 0
                or not isinstance(labelMetric.get("volumeMm3"), (int, float))
                or not math.isfinite(float(labelMetric["volumeMm3"]))
                or float(labelMetric["volumeMm3"]) <= 0
            ):
                raise ValueError(_("A per-label segmentation metric is invalid."))
            perLabelIds.append(labelMetric["id"])
        if sorted(perLabelIds) != sorted(detectedLabelIds):
            raise ValueError(_("Per-label metric IDs are inconsistent."))
        if sum(
            int(labelMetric["voxelCount"])
            for labelMetric in perLabel
        ) != int(metrics.get("foregroundVoxelCount", -1)):
            raise ValueError(_("Foreground and per-label voxel counts differ."))
        for metricName in (
            "foregroundVoxelCount",
            "foregroundVolumeMm3",
            "voxelVolumeMm3",
        ):
            metricValue = metrics.get(metricName)
            if (
                not isinstance(metricValue, (int, float))
                or not math.isfinite(float(metricValue))
                or float(metricValue) <= 0
            ):
                raise ValueError(
                    _("The reported segmentation metric %1 is invalid.")
                    .replace("%1", metricName)
                )
        for metricName in (
            "runtimeSeconds",
            "inferenceSeconds",
        ):
            metricValue = report.get(metricName)
            if (
                not isinstance(metricValue, (int, float))
                or not math.isfinite(float(metricValue))
                or float(metricValue) < 0
            ):
                raise ValueError(
                    _("The reported inference metric %1 is invalid.")
                    .replace("%1", metricName)
                )
        peakAllocatedBytes = device.get("peakAllocatedBytes")
        if requestedDevice == "cuda:0":
            if not isinstance(peakAllocatedBytes, int) or peakAllocatedBytes < 0:
                raise ValueError(_("Peak GPU memory metadata is invalid."))
        elif peakAllocatedBytes is not None:
            raise ValueError(_("CPU inference must not report CUDA memory."))

    @staticmethod
    def validateLabelmapAgainstReport(labelmapNode, report: dict) -> None:
        """Verify imported MRML label values against the backend JSON."""

        if (
            not labelmapNode
            or not labelmapNode.IsA("vtkMRMLLabelMapVolumeNode")
            or not labelmapNode.GetImageData()
        ):
            raise ValueError(_("The returned node is not a valid label map volume."))
        labelArray = slicer.util.arrayFromVolume(labelmapNode)
        if not np.issubdtype(labelArray.dtype, np.integer):
            raise ValueError(_("The returned label map does not use integer voxels."))
        uniqueValues, voxelCounts = np.unique(labelArray, return_counts=True)
        actualCounts = {
            int(value): int(count)
            for value, count in zip(uniqueValues.tolist(), voxelCounts.tolist())
            if int(value) != 0
        }
        actualLabelIds = sorted(actualCounts)
        expectedLabelIds = sorted(
            int(value)
            for value in report["metrics"]["detectedLabelIds"]
        )
        if actualLabelIds != expectedLabelIds:
            raise ValueError(
                _("Imported label values do not match the validated backend report.")
            )
        expectedCounts = {
            int(labelMetric["id"]): int(labelMetric["voxelCount"])
            for labelMetric in report["metrics"]["perLabel"]
        }
        if actualCounts != expectedCounts:
            raise ValueError(
                _("Imported label voxel counts do not match the backend report.")
            )

    @staticmethod
    def createTeethColorTable(labels: list[dict], runId: str):
        """Create deterministic label names and colors for segmentation import."""

        if not labels:
            raise ValueError(_("Cannot create a color table without labels."))
        colorTableNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLColorTableNode",
            f"DENTOBOT_TeethColors_{runId[:8]}",
        )
        try:
            colorTableNode.SetTypeToUser()
            colorTableNode.SetNumberOfColors(
                max(int(label["id"]) for label in labels) + 1
            )
            colorTableNode.SetColor(0, "Background", 0.0, 0.0, 0.0, 0.0)
            for label in labels:
                labelId = int(label["id"])
                labelName = str(label["name"])
                hue = (labelId * 0.618033988749895) % 1.0
                red, green, blue = colorsys.hsv_to_rgb(hue, 0.68, 0.95)
                if not colorTableNode.SetColor(
                    labelId,
                    labelName,
                    red,
                    green,
                    blue,
                    1.0,
                ):
                    raise RuntimeError(
                        _("Could not assign color for teeth label %1.")
                        .replace("%1", str(labelId))
                    )
            return colorTableNode
        except Exception:
            slicer.mrmlScene.RemoveNode(colorTableNode)
            raise

    @staticmethod
    def validateMatchingVolumeGeometry(
        sourceVolume: vtkMRMLScalarVolumeNode,
        outputVolume: vtkMRMLScalarVolumeNode,
        tolerance: float = 1e-4,
        requireMatchingScalarType: bool = True,
    ) -> None:
        """Reject a returned MRML volume whose voxel grid differs from its source."""

        for volumeNode in (sourceVolume, outputVolume):
            if (
                not volumeNode
                or not volumeNode.IsA("vtkMRMLScalarVolumeNode")
                or not volumeNode.GetImageData()
            ):
                raise ValueError(_("Both bridge volumes must be valid scalar volumes."))

        sourceImage = sourceVolume.GetImageData()
        outputImage = outputVolume.GetImageData()
        if sourceImage.GetDimensions() != outputImage.GetDimensions():
            raise ValueError(_("Returned volume dimensions do not match the source."))
        if (
            requireMatchingScalarType
            and sourceImage.GetScalarType() != outputImage.GetScalarType()
        ):
            raise ValueError(_("Returned volume scalar type does not match the source."))

        sourceMatrix = vtk.vtkMatrix4x4()
        outputMatrix = vtk.vtkMatrix4x4()
        sourceVolume.GetIJKToRASMatrix(sourceMatrix)
        outputVolume.GetIJKToRASMatrix(outputMatrix)
        for row in range(4):
            for column in range(4):
                if (
                    abs(
                        sourceMatrix.GetElement(row, column)
                        - outputMatrix.GetElement(row, column)
                    )
                    > tolerance
                ):
                    raise ValueError(
                        _("Returned volume IJK-to-RAS geometry does not match the source.")
                    )

    @staticmethod
    def _orientationDescription(ijkToRas: vtk.vtkMatrix4x4) -> str:
        positiveLabels = ("R", "A", "S")
        negativeLabels = ("L", "P", "I")
        axisNames = ("I", "J", "K")
        descriptions = []

        for column, axisName in enumerate(axisNames):
            direction = [ijkToRas.GetElement(row, column) for row in range(3)]
            dominantAxis = max(range(3), key=lambda row: abs(direction[row]))
            label = (
                positiveLabels[dominantAxis]
                if direction[dominantAxis] >= 0
                else negativeLabels[dominantAxis]
            )
            descriptions.append(f"{axisName}->{label}")

        return ", ".join(descriptions) + " (Slicer RAS)"
