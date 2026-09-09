# scripts/uninstall_schtask.ps1
Unregister-ScheduledTask -TaskName "SkillPulseCrawler" -Confirm:$false
Write-Host "Uninstalled task: SkillPulseCrawler"