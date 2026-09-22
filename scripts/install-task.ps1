# Registers the profile updater on this PC: every 6 hours and at logon.
# StartWhenAvailable runs a missed update as soon as the PC is back on; each run rebuilds
# from full history, so one run after any downtime catches everything up.
# Needs: git, gh (logged in; then `gh auth setup-git`), Python 3 on PATH, this repo cloned.
$repo = Split-Path $PSScriptRoot -Parent
$pythonw = Join-Path (Split-Path (Get-Command python).Source) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found next to python.exe" }

git -C $repo config user.name 'Lincoln'
git -C $repo config user.email 'lincolnstuek@gmail.com'

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$repo\scripts\update.py`" --push" -WorkingDirectory $repo
$triggers = @(
    (New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Hours 6)),
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'lstuek-profile' -Action $action -Trigger $triggers -Settings $settings -Description 'Update GitHub profile stats' -Force | Out-Null
Write-Host "Registered 'lstuek-profile' for $repo. Log: $env:LOCALAPPDATA\lstuek-profile.log"
