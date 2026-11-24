@echo off
rem Dung bot / ghi du lieu tu xa (TeamViewer): tao file STOP canh main.exe.
rem Tool kiem tra file nay moi 0.5 giay, dung TAT CA (ca che do chi quan sat) roi tu xoa file.
set "DEST=%LINEAGE_AUTO_DIR%"
if "%DEST%"=="" set "DEST=C:\LineageAuto"
if not exist "%DEST%\main\main.exe" (
  echo [LOI] Chua cai tool o %DEST%\main.
  goto :end
)
type nul > "%DEST%\main\STOP"
echo Da gui lenh DUNG. Tool se dung trong khoang 1 giay.
:end
if "%NOLAUNCH%"=="" timeout /t 3 >nul
