' اجرای برنامه بدون پنجره‌ی سیاه. اگر از قبل اجرا باشد، فقط صفحه را باز می‌کند.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = folder
sh.Run "pythonw """ & folder & "\app.py""", 0, False
