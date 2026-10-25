# Registers a daily Windows Task Scheduler job that runs Framefluence Autopilot.
#   Install:   powershell -ExecutionPolicy Bypass -File scripts\schedule_autopilot.ps1 [-Time 09:00]
#   Remove:    Unregister-ScheduledTask -TaskName "Framefluence Autopilot" -Confirm:$false
#   Run now:   Start-ScheduledTask -TaskName "Framefluence Autopilot"
param([string]$Time = "09:00")

# This script lives in scripts\; the repository root is one level up
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }

$action = New-ScheduledTaskAction -Execute $python -Argument "-m framefluence autopilot" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# StartWhenAvailable: if the PC was off/asleep at $Time, run as soon as it is back
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName "Framefluence Autopilot" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Daily trend briefing + inbox clips -> Reel drafts in review/" -Force | Out-Null
Write-Output "Scheduled 'Framefluence Autopilot' daily at $Time using $python"
