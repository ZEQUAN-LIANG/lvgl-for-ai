Option Explicit
' Zero-console launcher for the LVGL web viewer.
' Double-click this file: pythonw starts core\web.pyw in the background.
' web.pyw checks 127.0.0.1:8765: if the viewer is already listening it opens
' the page and exits; otherwise it starts the server, which opens the page and
' stops after the last page closes. The port check and the URL live in Python,
' so this file only starts the no-console entry point. No cmd window is
' created, so there is no black-box flash.

Dim shell, fso, root
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

shell.CurrentDirectory = root
shell.Run "pythonw.exe -I core\web.pyw", 0, False
