Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "D:\Projects\PoE_Price-Trade_Checker"
sh.Run Chr(34) & "C:\Users\Winai\anaconda3\pythonw.exe" & Chr(34) & " run.py", 0, False
