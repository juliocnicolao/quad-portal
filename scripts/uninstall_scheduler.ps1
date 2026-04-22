# Remove a tarefa agendada do Monitor Diario.
#
# Uso:
#     powershell -ExecutionPolicy Bypass -File scripts\uninstall_scheduler.ps1

$ErrorActionPreference = "Stop"
$TaskName = "QUAD-MonitorDiario"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "OK: tarefa '$TaskName' removida." -ForegroundColor Green
} else {
    Write-Host "Tarefa '$TaskName' nao existe — nada a fazer." -ForegroundColor Yellow
}
