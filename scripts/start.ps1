$PORT = 8181
$URL  = "http://127.0.0.1:$PORT"
$ROOT = Split-Path $PSScriptRoot -Parent

Write-Host "Iniciando aa-transcript em $URL ..."

# Inicia o servidor em background
$job = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    & uv run aa-transcript
} -ArgumentList $ROOT

# Aguarda o servidor responder (timeout 60s)
$ready = $false
$deadline = (Get-Date).AddSeconds(60)

while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri $URL -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    Write-Host "ERRO: servidor nao respondeu em 60s."
    Receive-Job $job
    Stop-Job $job; Remove-Job $job
    exit 1
}

Write-Host "Servidor no ar. Abrindo $URL ..."
Start-Process $URL

# Aguarda o job (mantém o terminal aberto mostrando logs)
Write-Host "Pressione Ctrl+C para encerrar o servidor."
try {
    Receive-Job $job -Wait
} finally {
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -ErrorAction SilentlyContinue
}
