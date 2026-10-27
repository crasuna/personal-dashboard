' Portable launcher: use a shortcut to this file, do not copy this file alone.
Option Explicit
Dim shell, fso, root, scriptPath, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = fso.BuildPath(root, "launch.py")
If Not fso.FileExists(scriptPath) Then
  MsgBox "Please run this launcher from the extracted project folder.", 16, "Personal Dashboard"
  WScript.Quit 1
End If
shell.CurrentDirectory = root
On Error Resume Next
command = "py -3 " & Chr(34) & scriptPath & Chr(34)
shell.Run command, 0, False
If Err.Number <> 0 Then
  Err.Clear
  command = "python " & Chr(34) & scriptPath & Chr(34)
  shell.Run command, 0, False
End If
If Err.Number <> 0 Then
  MsgBox "Python was not found. Run Start-Dashboard.cmd to see setup instructions.", 16, "Personal Dashboard"
End If
On Error GoTo 0
