param([string]$UserName = [Security.Principal.WindowsIdentity]::GetCurrent().Name)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$state = Join-Path $root '.local'
$shell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (!([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -UserName "{1}"' -f $PSCommandPath, $UserName
    $process = Start-Process -FilePath $shell -Verb RunAs -WindowStyle Hidden -ArgumentList $arguments -PassThru -Wait
    exit $process.ExitCode
}

New-Item -ItemType Directory -Path $state -Force | Out-Null
try {
    # S4U runs before sign-in without storing the Windows password, with limited privileges.
    $principal = New-ScheduledTaskPrincipal -UserId $UserName -LogonType S4U -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    foreach ($role in @('Web', 'Tunnel')) {
        $startup = New-ScheduledTaskTrigger -AtStartup
        $startup.Delay = 'PT20S'
        $triggers = @($startup, (New-ScheduledTaskTrigger -AtLogOn -User $UserName))
        $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -Role {1}' -f (Join-Path $PSScriptRoot 'run.ps1'), $role
        $action = New-ScheduledTaskAction -Execute $shell -Argument $arguments -WorkingDirectory $root
        Register-ScheduledTask -TaskName "InBody-$role" -Action $action -Trigger $triggers -Principal $principal -Settings $settings `
            -Description 'InBody local site: startup before Windows sign-in, restart after failure.' -Force | Out-Null
    }
    Start-ScheduledTask -TaskName 'InBody-Web'
    if (Test-Path -LiteralPath (Join-Path $state 'ngrok.yml')) { Start-ScheduledTask -TaskName 'InBody-Tunnel' }
    'OK' | Set-Content -LiteralPath (Join-Path $state 'autostart-result.txt') -Encoding UTF8
} catch {
    $_.Exception.Message | Set-Content -LiteralPath (Join-Path $state 'autostart-result.txt') -Encoding UTF8
    exit 1
}
