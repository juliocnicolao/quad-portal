# Instala a tarefa agendada do Monitor Diario no Windows Task Scheduler.
#
# Uso (PowerShell, nao precisa admin, roda como o usuario atual):
#     cd C:\Users\julio\Projetos\clientes\market-portal
#     powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1
#
# Cria/atualiza a tarefa 'QUAD-MonitorDiario' com 2 triggers diarios
# (08:30 e 18:30, hora local). Cada disparo invoca scripts\run_monitor.bat,
# que chama `python -m scheduler.runner`.
#
# Para remover: scripts\uninstall_scheduler.ps1

$ErrorActionPreference = "Stop"

$TaskName = "QUAD-MonitorDiario"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Wrapper  = Join-Path $RepoRoot "scripts\run_monitor.bat"

if (-not (Test-Path $Wrapper)) {
    throw "Wrapper nao encontrado: $Wrapper"
}

Write-Host "Repo root: $RepoRoot"
Write-Host "Wrapper:   $Wrapper"

# Acao: invoca o .bat a partir do repo root
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$Wrapper`"" `
    -WorkingDirectory $RepoRoot

# Triggers: 08:30 e 18:30 hora local (TZ do sistema).
$T1 = New-ScheduledTaskTrigger -Daily -At 08:30
$T2 = New-ScheduledTaskTrigger -Daily -At 18:30

# Settings:
#  - StartWhenAvailable: se perder o horario, roda ao acordar
#  - MultipleInstances IgnoreNew: evita sobreposicao
#  - ExecutionTimeLimit 30min: kill se travar
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

# Rodar como o usuario atual, nao elevado
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

# Se ja existe, substitui
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Tarefa '$TaskName' ja existe - substituindo..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description "Monitor Diario (QUAD) - coleta calendar + options flow + truflation 2x/dia." `
    -Action $Action `
    -Trigger @($T1, $T2) `
    -Settings $Settings `
    -Principal $Principal | Out-Null

Write-Host ""
Write-Host "OK: tarefa '$TaskName' registrada." -ForegroundColor Green
Write-Host "Triggers:"
Write-Host "  - diario 08:30 (hora local)"
Write-Host "  - diario 18:30 (hora local)"
Write-Host ""
Write-Host "Para rodar agora manualmente:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Para ver status:"
Write-Host "  Get-ScheduledTaskInfo -TaskName '$TaskName'"
