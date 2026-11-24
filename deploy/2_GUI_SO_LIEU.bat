@echo off
setlocal
rem Gom du lieu do (records + session_log + cau hinh) thanh 1 file zip tren Desktop de gui ve.
set "DEST=%LINEAGE_AUTO_DIR%"
if "%DEST%"=="" set "DEST=C:\LineageAuto"
set "APP=%DEST%\main"
if not exist "%APP%\main.exe" (
  echo [LOI] Chua cai tool o %APP%. Chay 1_CAI_DAT.bat truoc.
  goto :end
)
if not exist "%APP%\records" (
  echo [LOI] Chua co du lieu. Trong tool bam "Bat dau chi quan sat" truoc.
  goto :end
)
echo Hay DUNG che do quan sat / san truoc khi gom (de file summary duoc ghi).
powershell -NoProfile -Command ^
  "$out = Join-Path ([Environment]::GetFolderPath('Desktop')) ('LineageAuto_data_' + (Get-Date -Format 'yyyyMMdd_HHmm') + '.zip');" ^
  "$items = @('%APP%\records') + (@('%APP%\session_log.txt','%APP%\lineage_auto_config.json') | Where-Object { Test-Path $_ });" ^
  "Compress-Archive -Path $items -DestinationPath $out -Force;" ^
  "'Da tao: ' + $out + '  (' + [math]::Round((Get-Item $out).Length/1MB,1) + ' MB)';" ^
  "if (-not $env:NOLAUNCH) { explorer.exe /select,$out }"
echo Gui file zip tren Desktop ve may dev bang TeamViewer (File Transfer).
:end
echo.
if "%NOLAUNCH%"=="" pause
endlocal
