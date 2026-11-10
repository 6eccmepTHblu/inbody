param([Parameter(Mandatory = $true)][ValidateSet('Web', 'Tunnel')][string]$Role)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$state = Join-Path $root '.local'
Set-Location -LiteralPath $root
New-Item -ItemType Directory -Path $state -Force | Out-Null

if ($Role -eq 'Web') {
    $env:INBODY_HOST = '127.0.0.1'
    $env:INBODY_AUTH = '1'
    $env:INBODY_PDFS = Join-Path $root 'результаты'
    $exe = Join-Path $root '.venv\Scripts\python.exe'
    $arguments = @('-u', ('"{0}"' -f (Join-Path $root 'app.py')), '8000')
} else {
    $package = Get-AppxPackage -Name 'ngrok.ngrok'
    if (!$package) { throw 'Install ngrok from Microsoft Store first.' }
    $exe = Join-Path $package.InstallLocation 'ngrok.exe'
    $config = Join-Path $state 'ngrok.yml'
    if (!(Test-Path -LiteralPath $config)) { throw 'Run windows\configure.ps1 first.' }
    $arguments = @('http', 'http://127.0.0.1:8000', '--inspect=false', '--log=stdout', '--log-format=json', ('--config="{0}"' -f $config))
}

# Scheduler restarts this task on failure; logs are replaced on each start.
$process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru `
    -RedirectStandardOutput (Join-Path $state "$Role.log") -RedirectStandardError (Join-Path $state "$Role.error.log")
exit $process.ExitCode
