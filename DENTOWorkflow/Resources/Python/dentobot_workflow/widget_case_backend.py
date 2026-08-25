"""Extracted case imaging and backend UI methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


class CaseBackendWidgetMixin:
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
        if not self._parameterNode or not self._parameterNode.inputVolume:
            return
        with slicer.util.tryWithErrorDisplay(_("Could not display the selected volume.")):
            self._showVolumeInSliceViews(self._parameterNode.inputVolume)

    def onInputVolumeSelectionChanged(self, volumeNode) -> None:
        """Keep the visible selector authoritative and persist its exact node."""

        if not self._parameterNode:
            return
        parameterVolume = self._parameterNode.inputVolume
        parameterVolumeId = parameterVolume.GetID() if parameterVolume else None
        selectedVolumeId = volumeNode.GetID() if volumeNode else None
        if parameterVolumeId != selectedVolumeId:
            self._parameterNode.inputVolume = volumeNode
        self._updateBackendControls()

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

    def _createCaseBundle(self, destination: str | Path):
        if not self._parameterNode or not self.logic:
            raise CaseBundleError(_("DENTOBOT workflow state is unavailable."))
        with tempfile.TemporaryDirectory(
            prefix="dentobot-case-save-",
            dir=slicer.app.temporaryPath,
        ) as temporaryDirectory:
            scenePath = Path(temporaryDirectory) / "case.mrb"
            self._saveSceneSnapshotToMrb(scenePath)
            return create_case_bundle(
                destination,
                scenePath,
                case_label=self._parameterNode.caseName,
                workflow=self.logic.caseBundleWorkflowSummary(
                    self._parameterNode
                ),
                robot_profile=self.logic.caseBundleRobotProfile(),
                application={
                    "name": "DENTOBOT",
                    "module": "DENTOWorkflow",
                    "slicerVersion": str(
                        getattr(slicer.app, "applicationVersion", "unknown")
                    ),
                },
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
        freshnessIssues = self.logic.step6PlanningContextFreshnessIssues(
            self._parameterNode
        )
        if freshnessIssues:
            self.ui.caseBundleStatusLabel.text = _(
                "Saved and integrity-checked %1 with ROS excluded. Step 6 is "
                "not ready: %2"
            ).replace("%1", inspection.path.name).replace(
                "%2", " ".join(freshnessIssues)
            )
            self.ui.caseBundleStatusLabel.styleSheet = "color: #9a6500;"
        else:
            self.ui.caseBundleStatusLabel.text = _(
                "Saved integrity-checked package: %1. ROS runtime state was excluded."
            ).replace("%1", inspection.path.name)
            self.ui.caseBundleStatusLabel.styleSheet = "color: #207227;"

    def _openCaseBundle(self, bundlePath: str | Path):
        if not self.logic:
            raise CaseBundleError(_("DENTOBOT workflow logic is unavailable."))
        inspection = validate_case_bundle(bundlePath)
        recoveryLocationState = self._sceneLocationState()
        with tempfile.TemporaryDirectory(
            prefix="dentobot-case-open-",
            dir=slicer.app.temporaryPath,
        ) as temporaryDirectory:
            temporaryRoot = Path(temporaryDirectory)
            scenePath, inspection = extract_scene_mrb(
                inspection.path,
                temporaryRoot / "incoming",
            )
            recoveryPath = temporaryRoot / "recovery.mrb"
            self._saveSceneSnapshotToMrb(recoveryPath)
            try:
                if not slicer.util.loadScene(str(scenePath), {"clear": True}):
                    raise CaseBundleError(
                        _("Slicer could not replace the scene from the package.")
                    )
                slicer.app.processEvents()
                if self._parameterNode is None:
                    self.initializeParameterNode()
                self.logic.validateLoadedCaseBundleWorkflow(
                    self._parameterNode,
                    inspection.workflow,
                )
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
                    slicer.app.processEvents()
                    self._restoreSceneLocationState(recoveryLocationState)
                except Exception as exc:
                    recoveryError = _(" Recovery scene restoration failed: %1").replace(
                        "%1", str(exc)
                    )
                raise CaseBundleError(f"{loadError}{recoveryError}") from loadError

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
        )
        self._loadedCaseBundlePath = str(inspection.path)
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
        inspection = None
        with slicer.util.tryWithErrorDisplay(
            _("Could not open the selected DENTOBOT case package."),
            waitCursor=True,
        ):
            inspection = self._openCaseBundle(bundlePath)
        if inspection is None:
            return
        freshnessIssues = self.logic.step6PlanningContextFreshnessIssues(
            self._parameterNode
        )
        if not self._caseBundleRobotProfileCompatible:
            message = _(
                "Loaded %1, but the installed robot description differs from the "
                "saved fingerprint. Step 6 import is blocked until reconciled."
            ).replace("%1", inspection.path.name)
            color = "#9a6500"
        elif freshnessIssues:
            message = _(
                "Loaded and integrity-checked %1 with ROS disconnected. Step 6 "
                "remains blocked by saved lineage: %2"
            ).replace("%1", inspection.path.name).replace(
                "%2", " ".join(freshnessIssues)
            )
            color = "#9a6500"
        else:
            message = _(
                "Loaded and verified %1. ROS remains disconnected until Step 6."
            ).replace("%1", inspection.path.name)
            color = "#207227"
        self.ui.caseBundleStatusLabel.text = message
        self.ui.caseBundleStatusLabel.styleSheet = f"color: {color};"

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

        slicer.mrmlScene.Clear(0)
        self._loadedCaseBundlePath = ""
        self._caseBundleRobotProfileCompatible = None
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
            and self._parameterNode.inputVolume
            and not running
        )
        self.ui.segmentTeethButton.enabled = bool(
            configured
            and stagingRoot
            and self._parameterNode.inputVolume
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
        teethSegmentation = self._parameterNode.teethSegmentation
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
                not self._parameterNode.inputVolume
                or self._parameterNode.inputVolume.GetID() != volumeNode.GetID()
            ):
                self._parameterNode.inputVolume = volumeNode
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
                not self._parameterNode.inputVolume
                or self._parameterNode.inputVolume.GetID() != volumeNode.GetID()
            ):
                self._parameterNode.inputVolume = volumeNode
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

    def _onBackendCompleted(self, runId: str, returnCode: int) -> None:
        if not self._activeBackendRun or self._activeBackendRun["runId"] != runId:
            return

        runContext = self._activeBackendRun
        wasCancelled = self._backendCancellationRequested
        self._backendProcess = None
        self._activeBackendRun = None
        self._backendCancellationRequested = False
        if self._isCleaningUp:
            return
        self._updateBackendControls()

        if wasCancelled:
            self._setBackendStatus(_("Backend process cancelled."), "warning")
            return

        try:
            if runContext["operation"] == "health":
                self._completeHealthCheck(returnCode)
            elif runContext["operation"] == "roundtrip":
                self._completeRoundTrip(runContext, returnCode)
            elif runContext["operation"] == "segment-teeth":
                self._completeTeethSegmentation(runContext, returnCode)
        except Exception as exc:
            logging.exception("DENTOBOT backend completion handling failed")
            self._setBackendStatus(str(exc), "error")

    def _completeHealthCheck(self, returnCode: int) -> None:
        report = self.logic.findJsonReport(self._backendOutputLines, "health")
        if not report:
            raise RuntimeError(
                _("The backend did not return a valid health JSON document.")
            )
        if report.get("schemaVersion") != "1.0":
            raise RuntimeError(_("The backend health schema version is not supported."))

        if returnCode != 0 or report.get("status") != "ok":
            errors = report.get("errors") or [
                _("Backend health check failed with exit code %1.").replace(
                    "%1", str(returnCode)
                )
            ]
            raise RuntimeError(" ".join(str(error) for error in errors))

        requestedDevice = str(report.get("requestedDevice") or _("unspecified"))
        openvinoDevices = report.get("openvino", {}).get("devices") or []
        acceleratorText = (
            _("; OpenVINO sees %1").replace(
                "%1", ", ".join(str(device) for device in openvinoDevices)
            )
            if openvinoDevices
            else ""
        )
        pythonVersion = report.get("python", {}).get("version", _("unknown"))
        self._setBackendStatus(
            _("Backend healthy: Python %1; explicit device %2%3.")
            .replace("%1", str(pythonVersion))
            .replace("%2", requestedDevice)
            .replace("%3", acceleratorText),
            "success",
        )

    def _completeTeethSegmentation(
        self,
        runContext: dict,
        returnCode: int,
    ) -> None:
        runPaths = runContext["paths"]
        resultPath = runPaths["result"]
        if not resultPath.is_file():
            raise RuntimeError(
                _("The backend did not create the expected segmentation metadata.")
            )

        report = json.loads(resultPath.read_text(encoding="utf-8"))
        self.logic.validateTeethSegmentationReport(
            report,
            runContext["runId"],
            expectedDevice=runContext.get("device"),
        )
        if returnCode != 0 or report.get("status") != "ok":
            errorCode = report.get("errorCode")
            errors = report.get("errors") or [
                _("Teeth segmentation failed with exit code %1.")
                .replace("%1", str(returnCode))
            ]
            prefix = f"[{errorCode}] " if errorCode else ""
            raise RuntimeError(prefix + " ".join(str(error) for error in errors))
        if not runPaths["output"].is_file():
            raise RuntimeError(_("The expected teeth segmentation NIfTI is missing."))

        sourceVolume = slicer.mrmlScene.GetNodeByID(runContext["sourceVolumeId"])
        if not sourceVolume:
            raise RuntimeError(_("The source CBCT volume is no longer in the scene."))

        labelmapNode = None
        colorTableNode = None
        segmentationNode = None
        try:
            labelmapNode = slicer.util.loadLabelVolume(
                str(runPaths["output"]),
                {"name": f"DENTOBOT_TeethLabels_{runContext['runId'][:8]}"},
            )
            if not labelmapNode:
                raise RuntimeError(
                    _("Slicer could not import the returned teeth label map.")
                )
            self.logic.validateMatchingVolumeGeometry(
                sourceVolume,
                labelmapNode,
                requireMatchingScalarType=False,
            )
            self.logic.validateLabelmapAgainstReport(labelmapNode, report)

            colorTableNode = self.logic.createTeethColorTable(
                report["labels"],
                runContext["runId"],
            )
            labelmapNode.CreateDefaultDisplayNodes()
            labelmapNode.GetDisplayNode().SetAndObserveColorNodeID(
                colorTableNode.GetID()
            )

            segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode",
                f"DENTOsegmentation_Teeth_{runContext['runId'][:8]}",
            )
            segmentationNode.CreateDefaultDisplayNodes()
            segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(
                sourceVolume
            )
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                labelmapNode,
                segmentationNode,
            )
            expectedSegmentCount = int(report["metrics"]["segmentCount"])
            actualSegmentCount = (
                segmentationNode.GetSegmentation().GetNumberOfSegments()
            )
            if actualSegmentCount != expectedSegmentCount:
                raise RuntimeError(
                    _(
                        "Imported segmentation contains %1 segments, but the "
                        "validated backend report specifies %2."
                    )
                    .replace("%1", str(actualSegmentCount))
                    .replace("%2", str(expectedSegmentCount))
                )

            self._setBackendStatus(
                _("Creating interactive 3D surfaces for validated labels..."),
                "working",
            )
            slicer.app.processEvents()
            segmentationNode.CreateClosedSurfaceRepresentation()
            displayNode = segmentationNode.GetDisplayNode()
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetOpacity3D(0.55)

            reviewMetadataWarning = (
                self.logic.applyTeethSegmentationReviewMetadata(
                    segmentationNode,
                    sourceVolume,
                    report,
                    resultMetadataPath=resultPath,
                    segmentationNiftiPath=runPaths["output"],
                )
            )
            if reviewMetadataWarning:
                logging.warning(reviewMetadataWarning)

            parameterNode = self.logic.getParameterNode()
            parameterNode.teethSegmentation = segmentationNode
            if self._parameterNode:
                self._updateBackendControls()
                self.ui.backendCollapsibleButton.collapsed = True
                self.ui.segmentationReviewCollapsibleButton.collapsed = False
            slicer.util.setSliceViewerLayers(background=sourceVolume, fit=False)
        except Exception:
            if segmentationNode:
                slicer.mrmlScene.RemoveNode(segmentationNode)
            raise
        finally:
            if labelmapNode:
                slicer.mrmlScene.RemoveNode(labelmapNode)
            if colorTableNode:
                slicer.mrmlScene.RemoveNode(colorTableNode)

        self._setBackendStatus(
            _(
                "Teeth segmentation completed on %1: %2 validated segments are "
                "visible in 2D and 3D. Review this research output before use."
            )
            .replace("%1", str(report["device"]["actual"]))
            .replace("%2", str(report["metrics"]["segmentCount"])),
            "success",
        )

    def _completeRoundTrip(self, runContext: dict, returnCode: int) -> None:
        runPaths = runContext["paths"]
        resultPath = runPaths["result"]
        if not resultPath.is_file():
            raise RuntimeError(
                _("The backend did not create the expected result JSON document.")
            )

        report = json.loads(resultPath.read_text(encoding="utf-8"))
        if report.get("schemaVersion") != "1.0" or report.get("command") != "roundtrip":
            raise RuntimeError(_("The backend result contract is not supported."))
        if report.get("runId") != runContext["runId"]:
            raise RuntimeError(_("The result run ID does not match the requested run."))
        if returnCode != 0 or report.get("status") != "ok":
            errors = report.get("errors") or [
                _("Round trip failed with exit code %1.").replace("%1", str(returnCode))
            ]
            raise RuntimeError(" ".join(str(error) for error in errors))
        if not report.get("geometryMatch") or not report.get("dataMatch"):
            raise RuntimeError(_("Backend round-trip validation did not pass."))
        if not runPaths["output"].is_file():
            raise RuntimeError(_("The expected round-trip NIfTI is missing."))

        sourceVolume = slicer.mrmlScene.GetNodeByID(runContext["sourceVolumeId"])
        if not sourceVolume:
            raise RuntimeError(_("The source CBCT volume is no longer in the scene."))

        outputVolume = slicer.util.loadVolume(
            str(runPaths["output"]),
            {"name": f"DENTOBOT_RoundTrip_{runContext['runId'][:8]}"},
        )
        if not outputVolume:
            raise RuntimeError(_("Slicer could not import the round-trip NIfTI."))
        outputVolume.SetName(f"DENTOBOT_RoundTrip_{runContext['runId'][:8]}")

        try:
            self.logic.validateMatchingVolumeGeometry(sourceVolume, outputVolume)
        except Exception:
            slicer.mrmlScene.RemoveNode(outputVolume)
            raise

        outputVolume.SetAttribute("DENTOBOT.BridgeOperation", "roundtrip")
        outputVolume.SetAttribute("DENTOBOT.RunId", runContext["runId"])
        outputVolume.SetAttribute("DENTOBOT.SourceVolumeID", sourceVolume.GetID())
        outputVolume.SetAttribute("DENTOBOT.ResultMetadataPath", str(resultPath))

        parameterNode = self.logic.getParameterNode()
        parameterNode.roundTripVolume = outputVolume
        if self._parameterNode:
            self._updateBackendControls()
        self._setBackendStatus(
            _(
                "Round trip passed for %1. Geometry and voxel data were validated; "
                "the returned volume is now in the MRML scene."
            ).replace("%1", sourceVolume.GetName() or _("Unnamed volume")),
            "success",
        )
