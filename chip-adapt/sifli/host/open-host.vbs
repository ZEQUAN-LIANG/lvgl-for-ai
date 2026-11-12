Option Explicit
' Zero-console launcher for the SiFli Huangshan Pi host.
' Double-click this file: pythonw starts host\server.py, which opens the
' browser. The port check and URL live in Python, so this file only starts
' the no-console entry point.

Dim shell, fso, root
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

shell.CurrentDirectory = root
shell.Run "pythonw.exe -I server.py --open", 0, False
