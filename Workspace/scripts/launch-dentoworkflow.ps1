[CmdletBinding()]
param()

throw @"
This launcher name was retired because it could be confused with the full
Windows WSLg workflow. Choose one explicit profile:

  Full Steps 0-6 simulation in WSLg:
    Workspace\scripts\launch-lab-workflow.bat

  Legacy native Windows Slicer fallback, Steps 0-5 only (no Step 6/SlicerROS2):
    powershell -ExecutionPolicy Bypass -File Workspace\scripts\launch-native-windows-steps0-5.ps1
"@
