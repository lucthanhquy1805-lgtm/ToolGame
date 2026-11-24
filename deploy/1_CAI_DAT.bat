@echo off
setlocal
rem Lineage Classic Auto - cai dat tren may game. Chay bang cach bam dup.
rem LINEAGE_AUTO_DIR / NOLAUNCH chi dung khi test tren may dev.
set "SRC=%~dp0main"
set "DEST=%LINEAGE_AUTO_DIR%"
if "%DEST%"=="" set "DEST=C:\LineageAuto"

if not exist "%SRC%\main.exe" (
  echo [LOI] Khong thay thu muc "main" canh file nay. Hay giai nen ca file zip truoc.
  goto :end
)

echo === 1/3 Chep tool vao %DEST%\main ===
rem PLAN 0.12: tool cu con chay ngam (main.exe) se khoa file -> tat no truoc. Chi tat main.exe trong %DEST%\main.
powershell -NoProfile -Command "Get-Process -Name main -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq '%DEST%\main\main.exe' } | ForEach-Object { Write-Host ('   Tat tool cu dang chay (PID ' + $_.Id + ')'); Stop-Process -Id $_.Id -Force }; Start-Sleep -Milliseconds 800"
rem Giu lai cau hinh, log, con tro da dang ky va du lieu da ghi cua lan cai truoc.
rem /R:2 /W:2: thu lai 2 lan (mac dinh robocopy thu lai 1 trieu lan -> trong nhu bi treo).
robocopy "%SRC%" "%DEST%\main" /E /R:2 /W:2 /NFL /NDL /NJH /NJS /NP /XF lineage_auto_config.json lineage_auto_config.backup_*.json session_log.txt /XD records cursors
if errorlevel 8 (
  echo.
  echo [LOI] Chep file that bai ^(xem dong loi o tren^). Thuong do main.exe van dang chay:
  echo       mo Task Manager, tat "main.exe", roi chay lai file nay.
  goto :end
)
echo    Xong.

echo === 2/3 Tao loi tat tren Desktop ===
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Lineage Auto.lnk'); $s.TargetPath='%DEST%\main\main.exe'; $s.WorkingDirectory='%DEST%\main'; $s.Save()"
echo    Xong: "Lineage Auto" tren Desktop.
rem Nut dung tu xa: 3_DUNG_BOT.bat tao file STOP (PLAN 0.7).
copy /Y "%~dp03_DUNG_BOT.bat" "%DEST%\3_DUNG_BOT.bat" >nul
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\DUNG Lineage Auto.lnk'); $s.TargetPath='%DEST%\3_DUNG_BOT.bat'; $s.WorkingDirectory='%DEST%'; $s.Save()"
echo    Xong: "DUNG Lineage Auto" tren Desktop (bam dup = dung bot).

echo === 3/3 Driver Interception (can cho bot san; che do chi quan sat KHONG can) ===
if exist "%SystemRoot%\System32\drivers\keyboard.sys" if exist "%SystemRoot%\System32\drivers\mouse.sys" (
  echo    Da cai san. Bo qua.
  goto :launch
)
set "ANS=n"
set /p "ANS=   Cai driver Interception bay gio? Can quyen Admin va KHOI DONG LAI may. (y/n): "
if /i not "%ANS%"=="y" (
  echo    Bo qua. Van dung duoc che do "chi quan sat".
  goto :launch
)
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0Interception\command line installer\install-interception.exe' -ArgumentList '/install' -Verb RunAs -Wait"
echo    Da chay trinh cai. HAY KHOI DONG LAI MAY GAME de driver co hieu luc.
echo    Sau khi khoi dong lai: mo "Lineage Auto" tren Desktop.
goto :end

:launch
if not "%NOLAUNCH%"=="" goto :end
echo Mo tool...
start "" /D "%DEST%\main" "%DEST%\main\main.exe"
rem PLAN 0.28: khong de cua so cmd mo che Desktop / loi tat "DUNG Lineage Auto".
endlocal
exit

:end
echo.
if "%NOLAUNCH%"=="" pause
endlocal
