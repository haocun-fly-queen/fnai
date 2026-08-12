' Launch the Weibo cookie service silently (no console window).
' Put a shortcut to this file in the Windows Startup folder for auto-start.
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = scriptDir
sh.Run "pythonw """ & scriptDir & "\weibo_cookie_service.py""", 0, False
