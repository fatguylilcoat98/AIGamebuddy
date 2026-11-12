' Source checkouts have no runtime\pythonw.exe. Hide the setup script.
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("Wscript.Shell")
sh.CurrentDirectory = dir
py = dir & "\runtime\pythonw.exe"
If fso.FileExists(py) Then
  sh.Run """" & py & """ -m backend.wizard_app", 0, False
Else
  sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & dir & "\Start-Buddy.ps1""", 0, False
End If
