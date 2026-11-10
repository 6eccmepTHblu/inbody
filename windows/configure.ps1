$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$state = Join-Path $root '.local'
$Host.UI.RawUI.WindowTitle = 'InBody: пароль сайта и ngrok'
Set-Location -LiteralPath $root
try {
    New-Item -ItemType Directory -Path $state -Force | Out-Null
    $userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $state /inheritance:r /grant:r (('*{0}:(OI)(CI)F') -f $userSid) '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось ограничить доступ к папке с токеном.' }
    if (!(Test-Path -LiteralPath (Join-Path $root 'результаты\auth.json'))) {
        Write-Host 'Задайте пароль для входа на ваш сайт InBody. Ввод скрыт; пароль в чат не отправляется.'
        & (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'app.py') passwd
        if ($LASTEXITCODE -ne 0) { throw 'Пароль не задан. Запустите настройку повторно.' }
    }
    $config = Join-Path $state 'ngrok.yml'
    if (!(Test-Path -LiteralPath $config)) {
        Write-Host 'Войдите или зарегистрируйтесь в ngrok в открывшемся браузере.'
        Write-Host 'На странице Your Authtoken скопируйте только токен и вставьте сюда. Ввод скрыт.'
        Start-Process 'https://dashboard.ngrok.com/get-started/your-authtoken'
        $secret = Read-Host 'ngrok authtoken' -AsSecureString
        $token = [System.Net.NetworkCredential]::new('', $secret).Password.Trim()
        if ($token -notmatch '^[A-Za-z0-9_.-]{20,}$') { throw 'Нужен сам authtoken, без команды ngrok config add-authtoken.' }
        $yaml = "version: '3'`nagent:`n  authtoken: '$token'`n  web_addr: '127.0.0.1:4040'`n"
        [IO.File]::WriteAllText($config, $yaml, [Text.UTF8Encoding]::new($false))
        $token = $null
        $yaml = $null
        & ngrok.exe config check --config $config
        if ($LASTEXITCODE -ne 0) { throw 'ngrok не принял конфигурацию.' }
    }
    & (Join-Path $PSScriptRoot 'install-autostart.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить автозапуск. Проверьте .local\autostart-result.txt.' }
    Write-Host 'Автозапуск настроен. Ожидаю постоянную ссылку ngrok...'
    $url = $null
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $tunnels = Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2
            $url = ($tunnels.tunnels | Where-Object { $_.public_url -like 'https://*' } | Select-Object -First 1).public_url
            if ($url) { break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if (!$url) { throw 'Туннель пока не подключился. Подробности в .local\Tunnel.log и .local\Tunnel.error.log.' }
    $url | Set-Content -LiteralPath (Join-Path $state 'public-url.txt') -Encoding UTF8
    Write-Host "Готово: $url"
    Start-Process $url
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
}
Read-Host 'Нажмите Enter, чтобы закрыть окно'
