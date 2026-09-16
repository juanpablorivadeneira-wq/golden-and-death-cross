' Lanza "Iniciar Cross Monitor.bat" sin mostrar la ventana negra de consola.
Set objShell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = scriptDir
objShell.Run """" & scriptDir & "\Iniciar Cross Monitor.bat""", 0, False
