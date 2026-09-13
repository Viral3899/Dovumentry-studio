@echo off
setlocal
REM RUN THIS FIRST after ALL Flow images are generated.
REM Run this file inside the folder containing the generated Flow images.
REM It safely renames image files sequentially: 1.jpeg, 2.jpeg, 3.jpeg...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$files=Get-ChildItem -File | Where-Object { $_.Extension -match '^\.(png|jpe?g|webp)$' } | Sort-Object Name; $i=1; foreach($f in $files){ $tmp=('__flow_tmp_{0:D6}{1}' -f $i,$f.Extension.ToLower()); Rename-Item -LiteralPath $f.FullName -NewName $tmp; $i++ }; $files=Get-ChildItem -File | Where-Object { $_.Name -like '__flow_tmp_*' } | Sort-Object Name; $i=1; foreach($f in $files){ Rename-Item -LiteralPath $f.FullName -NewName ((('{0}' -f $i)+$f.Extension.ToLower())); $i++ }; Write-Host ('Renamed '+($i-1)+' image files.')"
pause
