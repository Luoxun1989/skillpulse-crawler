# scripts/install_schtask.ps1
# 用法：在仓库根目录 powershell 执行 .\scripts\install_schtask.ps1
$TaskName = "SkillPulseCrawler"
$WorkingDir = (Get-Location).Path
$PythonExe = Join-Path $WorkingDir ".venv\Scripts\python.exe"
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m skillpulse_crawler run" -WorkingDirectory $WorkingDir
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 23:00
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Weekly content harvest for skillpulse digest"
Write-Host "Installed task: $TaskName"