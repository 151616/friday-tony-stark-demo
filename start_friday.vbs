' Silent launcher for FRIDAY — runs start_friday.bat with no visible window.
' Used by the Windows Startup shortcut and by the in-app restart hotkey.
Set fso = CreateObject("Scripting.FileSystemObject")
sDir = fso.GetParentFolderName(WScript.ScriptFullName)
sBat = sDir & "\start_friday.bat"
CreateObject("WScript.Shell").Run Chr(34) & sBat & Chr(34), 0, False
