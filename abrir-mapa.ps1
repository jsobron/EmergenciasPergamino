[CmdletBinding()]
param(
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

$mapa = Join-Path $root 'data\mapa_pergamino.html'
if (-not (Test-Path -LiteralPath $mapa)) {
    & python -m ambulancias_pergamino exportar-mapa
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo generar el mapa.'
    }
}

function Test-MapaServer {
    param([int]$Puerto)

    try {
        $respuesta = Invoke-WebRequest -Uri "http://127.0.0.1:$Puerto/mapa_pergamino.html" -UseBasicParsing -TimeoutSec 2
        return $respuesta.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

$puertoFinal = $null
for ($puerto = $Port; $puerto -lt ($Port + 20); $puerto++) {
    $escucha = Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue
    if (-not $escucha) {
        $puertoFinal = $puerto
        break
    }
    if (Test-MapaServer -Puerto $puerto) {
        $puertoFinal = $puerto
        break
    }
}

if (-not $puertoFinal) {
    throw "No se encontro un puerto libre entre $Port y $($Port + 19)."
}

$servidorNuevo = $false
if (-not (Test-MapaServer -Puerto $puertoFinal)) {
    $servidor = Start-Process -FilePath 'python' `
        -ArgumentList @('-m', 'http.server', "$puertoFinal", '--bind', '127.0.0.1', '--directory', 'data') `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -PassThru
    $servidorNuevo = $true

    $listo = $false
    for ($intento = 0; $intento -lt 40; $intento++) {
        Start-Sleep -Milliseconds 250
        if (Test-MapaServer -Puerto $puertoFinal) {
            $listo = $true
            break
        }
        if ($servidor.HasExited) {
            break
        }
    }

    if (-not $listo) {
        throw 'El servidor local no respondio. Revisa que python este disponible.'
    }
}

$url = "http://127.0.0.1:$puertoFinal/mapa_pergamino.html"
Start-Process $url

Write-Host "Mapa abierto en $url"
if ($servidorNuevo) {
    Write-Host "Servidor iniciado en segundo plano (PID $($servidor.Id))."
}
else {
    Write-Host "Se reutilizo el servidor que ya estaba escuchando en el puerto $puertoFinal."
}
Write-Host "Para detenerlo: Get-NetTCPConnection -LocalPort $puertoFinal -State Listen | ForEach-Object { Stop-Process -Id `$_.OwningProcess }"
