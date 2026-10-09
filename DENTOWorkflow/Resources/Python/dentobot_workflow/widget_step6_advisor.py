"""Step 6.3 "Find Working Configuration" dialog (S6-ADVISOR-GUI-01).

Thin Qt driver for ``advisor_service.FeasibilityAdvisorSession``: a ``qt.QTimer``
runs one ``session.step()`` per tick so the dialog repaints and Cancel works
between steps. Clinical review gates are explicit prompts (default answer: skip);
trial configurations are temporarily applied to the live simulation state and
the service attempts to restore the baseline. Only the operator's explicit
"Apply & Save to branch" action calls ``session.apply_and_save``. No modal
dialog is auto-answered.
"""

from __future__ import annotations

from .runtime import *
from . import advisor_home
from . import advisor_service as advisor
from . import step6_working_config


class Step6AdvisorWidgetMixin:
    _ADVISOR_COLUMNS = ("Rank", "Setting change", "Result", "Failed step", "Reason", "Review", "Evidence")

    # ---- entry point (6.3 button, action owner 3) -------------------------------------
    def _onStep6FindWorkingConfig(self) -> None:
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        if getattr(self, "_workflowActionBusy", False) or getattr(self, "_advisorState", None):
            return
        root = advisor.default_evidence_root(os.environ)
        self._advisorState = {
            "root": root, "session": None, "timer": None, "dialog": None,
            "running": False, "fixButtons": [], "restoreFailed": False, "paused": False,
        }
        self._advisorNewSession()
        self._advisorBuildDialog()
        self._advisorShowSetup()
        self._advisorState["dialog"].show()

    def _advisorNewSession(self) -> None:
        state = self._advisorState
        state["session"] = advisor.FeasibilityAdvisorSession(
            self.logic,
            self._robotWorkflowFacade,
            self._parameterNode,
            state["root"],
            target_fdi=str(getattr(self._parameterNode, "targetToothSegmentId", "") or ""),
            stop_after_first_pass=not state.get("keepSearching", False),
            opening_applier=self._advisorApplyOpening,
            ui_refresh=self._advisorRefreshUi,
            connect_wrapper=self._advisorConnect,
        )

    # ---- production owners used by the service -----------------------------------------
    def _advisorApplyOpening(self, opening: float) -> None:
        del opening  # the service already set the parameter node's target gap
        wasUpdating = self._updatingFromParameterNode
        self._updatingFromParameterNode = True
        try:
            self.logic.createOrUpdateStep6CaseJawOpening(self._parameterNode)
        finally:
            self._updatingFromParameterNode = wasUpdating
        self._robotWorkflowFacade.clearTransientState()
        self._updateStep6CaseJawOpeningControls()

    def _advisorRefreshUi(self) -> None:
        self._updateRobotPlacement()

    def _advisorConnect(self, call):
        """Connect exactly like the 6.1 button does: parameter-node refresh suppressed meanwhile."""

        previous = getattr(self, "_suppressParameterRefreshDuringRobotConnect", False)
        self._suppressParameterRefreshDuringRobotConnect = True
        try:
            return call()
        finally:
            self._suppressParameterRefreshDuringRobotConnect = previous

    # ---- dialog construction -------------------------------------------------------------
    def _advisorBuildDialog(self) -> None:
        state = self._advisorState
        dialog = qt.QDialog(slicer.util.mainWindow())
        dialog.objectName = "DENTOBOTStep6AdvisorDialog"
        dialog.setWindowTitle(_("Find Working Configuration (Step 6.3)"))
        dialog.setWindowModality(qt.Qt.ApplicationModal)
        dialog.resize(1040, 700)
        layout = qt.QVBoxLayout(dialog)
        intro = qt.QLabel(
            _(
                "SIMULATION ONLY. Searches the approved levers in a fixed order (Base translation, lip/barrier "
                "variant candidates, mouth opening up to 46 mm in 0.5 mm steps, Base depth, Base yaw last) and stops at "
                "the first working candidate. Each trial temporarily changes the live simulation configuration; "
                "the search attempts to restore the starting configuration when it ends or is cancelled. "
                "Temporary trial changes may be visible and are not retained as the branch configuration. "
                "Lip/barrier variants (only the approved endpoint values; the barrier is never disabled) are "
                "evaluated only when the baseline's own contact evidence names the lip slab and after your "
                "explicit review; otherwise they stay UNTESTED. "
                "Opening, barrier variants, Base yaw and a shortened drilling depth need your explicit review. "
                "The window may stop repainting while one planning step runs (the length is not yet measured); "
                "Cancel takes effect when that step finishes. "
                "The search never moves the robot or uses different joints; unless you tick the Task Home consent "
                "below it does not accept or re-validate Task Home either. Use Apply & Save to branch only after "
                "the search reports that baseline restoration completed."
            ),
            dialog,
        )
        intro.objectName = "DENTOBOTStep6AdvisorIntroLabel"
        intro.wordWrap = True
        layout.addWidget(intro)

        setupGroup = qt.QGroupBox(_("Setup state"), dialog)
        setupGroup.objectName = "DENTOBOTStep6AdvisorSetupGroup"
        setupLayout = qt.QVBoxLayout(setupGroup)
        state["setupTable"] = qt.QTableWidget(0, 3, setupGroup)
        state["setupTable"].objectName = "DENTOBOTStep6AdvisorSetupTable"
        state["setupTable"].setHorizontalHeaderLabels([_("Issue"), _("Kind"), _("Fix")])
        state["setupTable"].horizontalHeader().setStretchLastSection(True)
        state["setupTable"].setColumnWidth(0, 560)
        state["setupTable"].setMaximumHeight(150)
        setupLayout.addWidget(state["setupTable"])
        layout.addWidget(setupGroup)

        consentGroup = qt.QGroupBox(_("Task Home revalidation (optional; OFF by default)"), dialog)
        consentGroup.objectName = "DENTOBOTStep6AdvisorHomeConsentGroup"
        consentLayout = qt.QVBoxLayout(consentGroup)
        consentLabel = qt.QLabel(
            _(advisor_home.CONSENT_TEXT) + " "
            + _("Without this consent a trial that makes the saved Task Home stale (or an opening change, which disconnects ROS) "
                "stops the search for explicit operator review. With it, an opening change that preserves a VALID branch "
                "pauses for your own Connect and Continue. If the branch needs rebuilding, the search stops for "
                "branch review instead."),
            consentGroup,
        )
        consentLabel.objectName = "DENTOBOTStep6AdvisorHomeConsentLabel"
        consentLabel.wordWrap = True
        consentLayout.addWidget(consentLabel)
        state["consentBox"] = qt.QCheckBox(
            _("I consent to Task Home revalidation for this search (simulation only)"), consentGroup)
        state["consentBox"].objectName = "DENTOBOTStep6AdvisorHomeConsentCheckBox"
        state["consentBox"].checked = False
        consentLayout.addWidget(state["consentBox"])
        layout.addWidget(consentGroup)

        state["statusLabel"] = qt.QLabel(_("Ready."), dialog)
        state["statusLabel"].objectName = "DENTOBOTStep6AdvisorStatusLabel"
        state["statusLabel"].wordWrap = True
        layout.addWidget(state["statusLabel"])
        state["progressBar"] = qt.QProgressBar(dialog)
        state["progressBar"].objectName = "DENTOBOTStep6AdvisorProgressBar"
        state["progressBar"].setRange(0, 1)
        layout.addWidget(state["progressBar"])

        state["resultsTable"] = qt.QTableWidget(0, len(self._ADVISOR_COLUMNS), dialog)
        state["resultsTable"].objectName = "DENTOBOTStep6AdvisorResultsTable"
        state["resultsTable"].setHorizontalHeaderLabels([_(name) for name in self._ADVISOR_COLUMNS])
        state["resultsTable"].horizontalHeader().setStretchLastSection(True)
        state["resultsTable"].setColumnWidth(1, 220)
        state["resultsTable"].setColumnWidth(4, 320)
        layout.addWidget(state["resultsTable"], 1)

        state["stagedLabel"] = qt.QLabel(_("No candidate is staged."), dialog)
        state["stagedLabel"].objectName = "DENTOBOTStep6AdvisorStagedLabel"
        state["stagedLabel"].wordWrap = True
        layout.addWidget(state["stagedLabel"])

        buttons = qt.QHBoxLayout()
        specs = (
            ("startButton", "DENTOBOTStep6AdvisorStartButton", _("Start search"), self._advisorOnStart),
            ("cancelButton", "DENTOBOTStep6AdvisorCancelButton", _("Cancel"), self._advisorOnCancel),
            ("pauseConnectButton", "DENTOBOTStep6AdvisorPauseConnectButton", _("Connect ROS + MoveIt (6.1)"),
             lambda: self._advisorOnFix("connect")),
            ("continueButton", "DENTOBOTStep6AdvisorContinueButton", _("Continue"), self._advisorOnContinue),
            ("moreButton", "DENTOBOTStep6AdvisorKeepSearchingButton", _("Keep searching for alternatives"),
             self._advisorOnKeepSearching),
            ("applyButton", "DENTOBOTStep6AdvisorApplySaveButton", _("Apply & Save to branch"),
             self._advisorOnApplyAndSave),
            ("exportButton", "DENTOBOTStep6AdvisorExportButton", _("Export evidence"), self._advisorOnExport),
            ("closeButton", "DENTOBOTStep6AdvisorCloseButton", _("Close"), self._advisorOnClose),
        )
        for key, name, text, handler in specs:
            button = qt.QPushButton(text, dialog)
            button.objectName = name
            button.clicked.connect(lambda checked=False, handler=handler: handler())
            buttons.addWidget(button)
            state[key] = button
        layout.addLayout(buttons)
        dialog.rejected.connect(self._advisorOnRejected)
        state["dialog"] = dialog
        for key in ("pauseConnectButton", "continueButton"):
            state[key].setVisible(False)
        self._advisorSetButtons("idle")

    def _advisorSetButtons(self, mode: str) -> None:
        state = getattr(self, "_advisorState", None)
        if not state:
            return
        session = state["session"]
        best = session.best_candidate() if session is not None and session.finished else None
        unavailable = bool(state.get("restoreFailed") or state.get("configurationApplied"))
        busy = bool(state.get("running") or getattr(self, "_workflowActionBusy", False))
        state["startButton"].enabled = mode == "idle" and not unavailable and not busy
        state["cancelButton"].enabled = mode in ("running", "paused")
        if state.get("consentBox") is not None:  # consent is per search: tick it before Start or before "Keep searching"
            state["consentBox"].enabled = mode in ("idle", "done") and not unavailable and not busy
        for key in ("pauseConnectButton", "continueButton"):
            if state.get(key) is not None:
                state[key].setVisible(mode == "paused")
                state[key].enabled = mode == "paused"
        state["moreButton"].enabled = (
            mode == "done" and not unavailable and session is not None
            and session.outcome == advisor.FOUND
        )
        state["applyButton"].enabled = mode == "done" and not unavailable and best is not None
        state["exportButton"].enabled = (
            mode != "running" and not busy and session is not None and bool(session.baseline)
        )
        state["closeButton"].enabled = mode not in ("running", "paused")
        for button in state.get("fixButtons", ()):
            button.enabled = not busy and mode not in ("running", "paused")
        state["applyButton"].toolTip = (
            _("Stores the staged configuration on this PreparedBranch (saved in the dentocase) and then re-applies it "
              "through the normal Restore owner. Clinically sensitive changes are listed for your confirmation.")
            if best is not None and not unavailable else _("Available only after a passing candidate and confirmed baseline restoration.")
        )

    # ---- setup diagnostics ------------------------------------------------------------------
    def _advisorShowSetup(self, issues=None) -> None:
        state = self._advisorState
        issues = issues if issues is not None else state["session"].setup_report()
        table = state["setupTable"]
        table.setRowCount(0)
        state["fixButtons"] = []
        state["setupIssues"] = list(issues)
        for row, issue in enumerate(issues):
            table.insertRow(row)
            table.setItem(row, 0, qt.QTableWidgetItem(issue.message))
            mode = {"blocking": _("blocks the search"), "blocks_apply": _("blocks Apply & Save to branch")}.get(
                issue.severity, _("the search applies this"))
            table.setItem(row, 1, qt.QTableWidgetItem(mode))
            if issue.fix_id:
                button = qt.QPushButton(_(issue.fix_label), table)
                button.objectName = f"DENTOBOTStep6AdvisorFixButton{row}"
                button.clicked.connect(lambda checked=False, fix=issue.fix_id: self._advisorOnFix(fix))
                button.enabled = not state.get("running") and not getattr(self, "_workflowActionBusy", False)
                table.setCellWidget(row, 2, button)
                state["fixButtons"].append(button)
        if not issues:
            table.insertRow(0)
            table.setItem(0, 0, qt.QTableWidgetItem(_("No setup issues found.")))

    def _advisorOnFix(self, fix_id: str) -> None:
        """Operator-initiated fix actions run the same production handlers as their buttons."""

        state = getattr(self, "_advisorState", None)
        if not state or state.get("running") or getattr(self, "_workflowActionBusy", False):
            return

        handlers = {
            "connect": self._onShellConnectRobot,
            "disconnect": self._onShellDisconnectRobot,
            "sync_scene": self._onShellSyncCollisionScene,
            "goto_6_1": lambda: self._configureRobotSimulationShellSubstep(1),
            "goto_6_2": lambda: self._configureRobotSimulationShellSubstep(2),
            "goto_6_3": lambda: self._configureRobotSimulationShellSubstep(3),
        }
        handler = handlers.get(fix_id)
        if handler is None:
            return
        navigation_fixes = {"goto_6_1", "goto_6_2", "goto_6_3"}
        if state.get("paused") and fix_id != "connect":
            return  # a paused search is continued or cancelled, never abandoned by navigating away
        if fix_id in navigation_fixes:
            if not self._advisorCloseForNavigation():
                return
            handler()
            return
        state["dialog"].hide()
        try:
            handler()
        finally:
            if getattr(self, "_advisorState", None) is state:
                state["dialog"].show()
                if state.get("paused"):
                    self._advisorSetButtons("paused")
                else:
                    self._advisorShowSetup()
                    self._advisorSetButtons("idle")

    def _advisorCloseForNavigation(self) -> bool:
        """Release the application-modal dialog before moving the main workflow."""

        state = getattr(self, "_advisorState", None)
        if not state or state.get("running") or getattr(self, "_workflowActionBusy", False):
            return False
        dialog = state.get("dialog")
        self._advisorState = None
        if dialog is not None:
            dialog.hide()
            dialog.deleteLater()
        return True

    # ---- run control -------------------------------------------------------------------------------
    def _advisorOnStart(self) -> None:
        state = getattr(self, "_advisorState", None)
        if (
            not state or state.get("running") or state.get("restoreFailed")
            or state.get("configurationApplied") or getattr(self, "_workflowActionBusy", False)
        ):
            return
        session = state["session"]
        if session.phase != advisor.IDLE:  # resume after a cancel/finish: a new session reuses the checkpoints
            self._advisorNewSession()
            session = state["session"]
        consent = state.get("consentBox")
        consented = bool(consent is not None and consent.checked)
        if consented:
            session.grant_home_revalidation_consent(advisor_home.CONSENT_TEXT)
        issues = session.prepare()
        self._advisorShowSetup(issues)
        if session.finished:
            if consent is not None:
                consent.checked = False  # consent is per search, also when setup blocked it
            state["statusLabel"].text = session.message
            self._advisorSetButtons("idle")
            return
        self._workflowActionBusy = True
        state["running"] = True
        state["cancelRequested"] = False
        self._advisorSetButtons("running")
        state["statusLabel"].text = _("Starting the ordered search…") + (
            " " + _("(Task Home revalidation consent: ON; simulation only, no joint moves)") if consented else "")
        timer = qt.QTimer()
        timer.setSingleShot(True)
        timer.setInterval(10)
        timer.timeout.connect(self._advisorTick)
        state["timer"] = timer
        timer.start()

    def _advisorOnCancel(self) -> None:
        state = getattr(self, "_advisorState", None)
        paused = bool(state and state.get("paused"))
        if not state or not (state.get("running") or paused) or state.get("cancelRequested"):
            return
        try:
            state["session"].cancel()
        except Exception as exc:
            self._advisorReportRestoreUnconfirmed(
                _("Cancellation failed (%1). The original Step 6 state is not confirmed restored.").replace(
                    "%1", str(exc)[:240]
                )
            )
            return
        state["cancelRequested"] = True
        state["cancelButton"].enabled = False
        state["statusLabel"].text = _(
            "Cancellation requested. The current step will finish, then baseline restoration will be attempted…"
        )
        if paused:  # a paused search has no step in flight: drive the restoration now
            state["stagedLabel"].text = _("No candidate is staged.")
            state["paused"] = False
            state["running"] = True
            self._workflowActionBusy = True
            self._advisorSetButtons("running")
            state["cancelButton"].enabled = False
            state["timer"].start()

    def _advisorOnContinue(self) -> None:
        """The operator's Continue after their own Connect; the service refuses on any joint/identity drift."""

        state = getattr(self, "_advisorState", None)
        if not state or not state.get("paused") or state.get("running"):
            return
        try:
            event = state["session"].resume()
        except Exception as exc:  # the search stays paused and unchanged; Cancel restores the original configuration
            state["statusLabel"].text = _(
                "Continue could not be evaluated (%1); the search stays paused. Cancel restores the original "
                "configuration."
            ).replace("%1", str(exc)[:240])
            return
        if event.kind == "pause":  # refused: still paused, nothing changed; the operator can fix or Cancel
            state["statusLabel"].text = event.message
            return
        state["paused"] = False
        state["running"] = True
        self._workflowActionBusy = True
        state["stagedLabel"].text = _("No candidate is staged.")
        state["statusLabel"].text = event.message
        self._advisorSetButtons("running")
        state["timer"].start()

    def _advisorEnterPause(self, event) -> None:
        state = self._advisorState
        state["paused"] = True
        state["running"] = False
        self._workflowActionBusy = False  # the production Connect owner must be usable by the operator
        state["statusLabel"].text = event.message
        state["stagedLabel"].text = _(
            "Paused for your action: nothing continues until you press Continue after your own Connect. "
            "Cancel restores the original configuration."
        )
        self._advisorSetButtons("paused")

    def _advisorOnRejected(self) -> None:
        """Closing the window mid-search cancels (and restores); the dialog stays up until done."""

        state = getattr(self, "_advisorState", None)
        if not state:
            return
        if state["running"] or state.get("paused"):
            self._advisorOnCancel()
            state["dialog"].show()
            state["dialog"].raise_()
        else:
            self._advisorOnClose()

    def _advisorOnClose(self) -> None:
        state = getattr(self, "_advisorState", None)
        if not state:
            return
        if state["running"] or state.get("paused"):
            self._advisorOnCancel()
            state["dialog"].show()
            state["dialog"].raise_()
            return
        state["dialog"].hide()
        state["dialog"].deleteLater()
        self._advisorState = None

    def _advisorOnKeepSearching(self) -> None:
        state = getattr(self, "_advisorState", None)
        if (
            not state or state.get("running") or state.get("restoreFailed")
            or state.get("configurationApplied") or getattr(self, "_workflowActionBusy", False)
        ):
            return
        state["keepSearching"] = True
        state["session"] = None
        self._advisorNewSession()
        self._advisorOnStart()

    def _advisorTick(self) -> None:
        state = getattr(self, "_advisorState", None)
        if not state or not state["running"]:
            return
        session = state["session"]
        recovery = state.get("errorRecovery")
        try:
            event = session.step()
            if event.kind == "gate":
                approved = self._advisorAskGate(event)
                (session.approve_stage if approved else session.decline_stage)(event.stage)
            if event.kind == "pause":
                self._advisorEnterPause(event)
                return
            self._advisorShowProgress(event)
        except Exception as exc:  # Request one bounded service restoration; never retry a failed restore tick.
            if recovery:
                self._advisorReportRestoreUnconfirmed(
                    _("An unexpected error interrupted the bounded restoration attempt (%1). Do not plan from this "
                      "state; use Restore Branch Step 6 Config and review 6.1-6.3.").replace("%1", str(exc)[:240])
                )
            else:
                self._advisorBeginErrorRecovery(exc)
            return
        if recovery:
            recovery["remaining"] -= 1
            if session.finished:
                try:
                    self._advisorFinish()
                except Exception as exc:
                    self._advisorReportRestoreUnconfirmed(
                        _("Restoration ended, but the GUI could not confirm its result (%1). Do not plan from this "
                          "state; use Restore Branch Step 6 Config.").replace("%1", str(exc)[:240])
                    )
                return
            if recovery["remaining"] <= 0:
                self._advisorReportRestoreUnconfirmed(
                    _("The bounded restoration window ended without a completion report. Do not plan from this "
                      "state; use Restore Branch Step 6 Config and review 6.1-6.3.")
                )
                return
            state["timer"].start()
            return
        if session.finished:
            try:
                self._advisorFinish()
            except Exception as exc:
                self._advisorReportRestoreUnconfirmed(
                    _("The search ended, but the GUI could not confirm the restored state (%1). Do not plan from this "
                      "state; use Restore Branch Step 6 Config.").replace("%1", str(exc)[:240])
                )
        else:
            state["timer"].start()

    def _advisorBeginErrorRecovery(self, error) -> None:
        state = getattr(self, "_advisorState", None)
        if not state:
            return
        session = state.get("session")
        if session is None or getattr(session, "finished", False):
            self._advisorReportRestoreUnconfirmed(
                _("The search stopped unexpectedly (%1), and no active service restoration could be requested. "
                  "Do not plan from this state; use Restore Branch Step 6 Config.").replace("%1", str(error)[:240])
            )
            return
        cancel = getattr(session, "cancel", None)
        if not callable(cancel):
            self._advisorReportRestoreUnconfirmed(
                _("The search stopped unexpectedly (%1), and this service cannot request restoration. Do not plan "
                  "from this state; use Restore Branch Step 6 Config.").replace("%1", str(error)[:240])
            )
            return
        try:
            cancel()
        except Exception as cancel_error:
            self._advisorReportRestoreUnconfirmed(
                _("The search error (%1) was followed by a failed restoration request (%2). Do not plan from this "
                  "state; use Restore Branch Step 6 Config.").replace("%1", str(error)[:120]).replace(
                    "%2", str(cancel_error)[:120]
                )
            )
            return
        budget = max(1, len(getattr(advisor, "APPLY_STEPS", ())) + 2)
        state["errorRecovery"] = {"message": str(error)[:240], "remaining": budget}
        state["running"] = True
        state["cancelRequested"] = True
        self._workflowActionBusy = True
        state["statusLabel"].text = _(
            "Unexpected search error (%1). Cancellation was requested; a bounded baseline restoration is now running…"
        ).replace("%1", str(error)[:240])
        self._advisorSetButtons("running")
        state["cancelButton"].enabled = False
        if state.get("timer") is not None:
            state["timer"].start()
        else:
            self._advisorReportRestoreUnconfirmed(
                _("The search stopped unexpectedly and no timer is available to finish baseline restoration. Do not "
                  "plan from this state; use Restore Branch Step 6 Config.")
            )

    def _advisorReportRestoreUnconfirmed(self, message: str) -> None:
        state = getattr(self, "_advisorState", None)
        if not state:
            return
        state["running"] = False
        state["paused"] = False
        if state.get("consentBox") is not None:
            state["consentBox"].checked = False
        state["restoreFailed"] = True
        state["errorRecovery"] = None
        self._workflowActionBusy = False
        state["statusLabel"].text = message
        state["stagedLabel"].text = _(
            "Baseline restoration is not confirmed. A candidate cannot be applied from this session."
        )
        self._advisorSetButtons("restore_failed")
        panel = getattr(self, "_robotSimulationPanel", None)
        if panel is not None:
            panel.showBranchConfigStatus(message, "error")
        self._updateStep6PlanningUi(message, error=True)

    def _advisorAskGate(self, event) -> bool:
        """Explicit review gate before the first candidate of a clinically sensitive stage."""

        box = qt.QMessageBox(self._advisorState["dialog"])
        box.objectName = "DENTOBOTStep6AdvisorGateMessageBox"
        box.setIcon(qt.QMessageBox.Question)
        box.setWindowTitle(_("Clinical review: %1").replace("%1", event.stage.replace("_", " ")))
        box.setText(
            event.message
            + "\n\n"
            + _("This lever is clinically sensitive. Candidate configurations temporarily change simulation state; "
                "baseline restoration is attempted when the search ends. No trial is retained on the branch without "
                "your final confirmation. %1 candidate state(s) are in this stage.")
            .replace("%1", str(event.total))
        )
        evaluate = box.addButton(_("Evaluate this stage"), qt.QMessageBox.YesRole)
        evaluate.objectName = "DENTOBOTStep6AdvisorGateEvaluateButton"
        skip = box.addButton(_("Skip this stage"), qt.QMessageBox.NoRole)
        skip.objectName = "DENTOBOTStep6AdvisorGateSkipButton"
        box.setDefaultButton(skip)
        box.setEscapeButton(skip)
        box.exec_()
        return box.clickedButton() == evaluate

    def _advisorShowProgress(self, event) -> None:
        state = self._advisorState
        session = state["session"]
        progress = session.progress()
        total = max(1, int(progress["total"]))
        state["progressBar"].setRange(0, total)
        state["progressBar"].setValue(min(total, int(progress["index"])))
        stage = (progress["stage"] or event.stage or "").replace("_", " ")
        if session.phase == advisor.RESTORING:
            text = _("Restoring your original Step 6 state…")
        else:
            text = _("Stage: %1 | candidate %2 of at most %3 | step: %4 %5")
            text = (text.replace("%1", stage or "-").replace("%2", str(progress["index"] + (1 if session.phase == advisor.EVALUATING else 0)))
                    .replace("%3", str(total)).replace("%4", str(progress["step"] or "-"))
                    .replace("%5", str(progress["label"] or "")))
        if state.get("errorRecovery"):
            text = _("Restoring the original Step 6 configuration after an unexpected error…")
        state["statusLabel"].text = text
        if event.kind in ("candidate", "reused"):
            self._advisorFillResults()

    def _advisorFillResults(self) -> None:
        state = self._advisorState
        table = state["resultsTable"]
        rows = state["session"].ranked()
        table.setRowCount(0)
        for index, row in enumerate(rows):
            table.insertRow(index)
            values = (
                str(row["rank"]), row["change_text"], row["result"] + (" (reused)" if row["reused"] else ""),
                row["failed_step"] or "-", row["reason"][:240], ", ".join(row["review_items"]) or "-",
            )
            for column, value in enumerate(values):
                table.setItem(index, column, qt.QTableWidgetItem(value))
            link = qt.QPushButton(_("Open"), table)
            link.objectName = f"DENTOBOTStep6AdvisorEvidenceButton{index}"
            link.toolTip = row["evidence_dir"]
            link.clicked.connect(lambda checked=False, path=row["evidence_dir"]: self._advisorOpenEvidence(path))
            table.setCellWidget(index, 6, link)

    def _advisorOpenEvidence(self, path: str) -> None:
        if path:
            qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(str(path)))

    def _advisorFinish(self) -> None:
        state = self._advisorState
        session = state["session"]
        state["running"] = False
        state["paused"] = False
        self._workflowActionBusy = False
        if state.get("consentBox") is not None:
            state["consentBox"].checked = False  # consent is per search and is never carried to the next one
        restore_issues = list(getattr(session, "restore_issues", ()) or ())
        restored = bool(session.finished and not restore_issues)
        state["restoreFailed"] = not restored
        self._advisorFillResults()
        policy = self._robotWorkflowFacade.jointPlanningPolicy()
        if self._robotSimulationPanel is not None:
            self._robotSimulationPanel.setPlanningPolicy(
                policy["planner_id"], policy["planning_attempts"], policy["planning_time_sec"]
            )
        self._updateRobotPlacement()
        self._updateStep6PlanningUi()
        self._refreshShellRobotCapabilities()
        best = session.best_candidate()
        state["statusLabel"].text = session.message
        if state.get("errorRecovery"):
            error = state["errorRecovery"].get("message", "")
            if restored:
                state["statusLabel"].text = _(
                    "The search stopped after an unexpected error (%1). The service reported baseline restoration "
                    "complete. %2"
                ).replace("%1", error).replace("%2", session.message)
            else:
                state["statusLabel"].text = _(
                    "The search stopped after an unexpected error (%1). Baseline restoration was not confirmed. "
                    "Do not plan from this state; use Restore Branch Step 6 Config. %2"
                ).replace("%1", error).replace("%2", session.message)
        if not restored:
            reason = "; ".join(str(issue) for issue in restore_issues)[:300] or _(
                "the service did not report a completed restoration"
            )
            warning = _(
                "Baseline restoration was not confirmed (%1). Do not plan from this state; use Restore Branch Step 6 "
                "Config and review 6.1-6.3."
            ).replace("%1", reason)
            if warning not in state["statusLabel"].text:
                state["statusLabel"].text += " " + warning
            panel = getattr(self, "_robotSimulationPanel", None)
            if panel is not None:
                panel.showBranchConfigStatus(warning, "error")
            self._updateStep6PlanningUi(warning, error=True)
        if best is None:
            state["stagedLabel"].text = _("No candidate is staged.")
        elif not restored:
            state["stagedLabel"].text = _(
                "A candidate passed, but baseline restoration is unconfirmed. It cannot be applied from this session."
            )
        else:
            row = next(r for r in session.ranked() if r["state_key"] == best["state_key"])
            review = row["review_items"]
            state["stagedLabel"].text = (
                _("RECOMMENDED, NOT RETAINED: %1 (%2).").replace("%1", row["change_text"]).replace("%2", row["result"])
                + (_(" Needs your review: %1.").replace("%1", ", ".join(review)) if review else "")
            )
        state["errorRecovery"] = None
        self._advisorSetButtons("done")

    # ---- the ONLY storing path: the operator's click ---------------------------------------------------
    def _advisorOnApplyAndSave(self) -> None:
        state = getattr(self, "_advisorState", None)
        if (
            not state or state.get("running") or state.get("restoreFailed")
            or state.get("configurationApplied") or getattr(self, "_workflowActionBusy", False)
        ):
            return
        session = state["session"]
        best = session.best_candidate()
        if best is None:
            return
        items = session.required_acknowledgements(best)
        config = advisor.working_configuration_record(best, session.saved_home, session.original)
        summary = self._step6WorkingConfigurationSummary(step6_working_config.normalize(config))
        text = (
            _("Save this configuration on the active PreparedBranch and apply it through the normal Restore owner?")
            + "\n\n" + summary
            + ("\n\n" + _("Clinical review required:") + "\n- " + "\n- ".join(items) if items else "")
            + "\n\n" + _(
                "The search temporarily applied trial configurations and attempted to restore the starting state. "
                "No trial configuration has been retained on this branch. Task Home is staged only; it has not been "
                "accepted or moved."
            )
        )
        box = qt.QMessageBox(state["dialog"])
        box.objectName = "DENTOBOTStep6AdvisorApplyConfirmMessageBox"
        box.setIcon(qt.QMessageBox.Question)
        box.setWindowTitle(_("Apply & Save to branch"))
        box.setText(text)
        confirm = box.addButton(_("Apply & Save"), qt.QMessageBox.YesRole)
        cancel = box.addButton(_("Do not save"), qt.QMessageBox.NoRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec_()
        if box.clickedButton() != confirm:
            return
        try:
            session.apply_and_save(acknowledged=items, record=best)
        except (PermissionError, ValueError, RuntimeError) as exc:
            state["statusLabel"].text = _("Not saved: ") + str(exc)
            return
        state["statusLabel"].text = _("Saved on this branch. Applying it through Restore Branch Step 6 Config…")
        restore_error = ""
        try:
            self.onRestoreStep6WorkingConfiguration()
            self._refreshStep6WorkingConfigurationStatus()
        except Exception as exc:
            restore_error = str(exc)[:240]
        if not restore_error and getattr(self, "_step6WorkingConfigurationRestoreSucceeded", False):
            state["configurationApplied"] = True
            state["statusLabel"].text = _(
                "Saved on this branch and restored through the Restore owner. Task Home is staged only; it has not "
                "been accepted or moved. Review 6.2 before planning."
            )
            self._advisorSetButtons("applied")
        else:
            state["restoreFailed"] = True
            state["statusLabel"].text = _(
                "Saved on this branch, but Restore did not complete%1. The Step 6 state may have changed. Do not "
                "plan from this state; use Restore Branch Step 6 Config and review 6.1-6.3."
            ).replace("%1", ": " + restore_error if restore_error else "")
            panel = getattr(self, "_robotSimulationPanel", None)
            if panel is not None:
                panel.showBranchConfigStatus(state["statusLabel"].text, "error")
            self._updateStep6PlanningUi(state["statusLabel"].text, error=True)
            self._advisorSetButtons("restore_failed")

    def _advisorOnExport(self) -> None:
        state = getattr(self, "_advisorState", None)
        if not state or state.get("running") or getattr(self, "_workflowActionBusy", False):
            return
        path = state["session"].export_evidence()
        state["statusLabel"].text = _("Evidence package: %1").replace("%1", path)
        self._advisorOpenEvidence(path)
