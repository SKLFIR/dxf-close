# Установка «Замыкание контуров DXF» на Windows.
#
#   powershell -c "irm https://raw.githubusercontent.com/SKLFIR/dxf-close/main/install.ps1 | iex"
#
# Ставит Python (если его нет), кладёт программу в отдельное окружение
# и создаёт ярлык на рабочем столе.

$ErrorActionPreference = 'Stop'

$Repo    = 'https://github.com/SKLFIR/dxf-close/archive/refs/heads/main.zip'
$AppDir  = Join-Path $env:LOCALAPPDATA 'dxf-close'
$VenvDir = Join-Path $AppDir 'venv'

function Say($text, $color = 'White') { Write-Host $text -ForegroundColor $color }

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = ($machine, $user | Where-Object { $_ }) -join ';'
}

function Find-Python {
    foreach ($cmd in @('py -3', 'python3', 'python')) {
        $parts = $cmd -split ' '
        $exe = Get-Command $parts[0] -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        try {
            $args = @()
            if ($parts.Count -gt 1) { $args += $parts[1] }
            $args += @('-c', 'import sys; print(sys.executable if sys.version_info[:2] >= (3, 9) else "")')
            $out = & $exe.Source @args 2>$null
            if ($out -and $out.Trim()) { return $out.Trim() }
        } catch { }
    }
    return $null
}

Say ''
Say '=== Замыкание контуров DXF — установка ===' Cyan
Say ''

# --- 1. Python -------------------------------------------------------------
$python = Find-Python
if (-not $python) {
    Say 'Python не найден, ставлю через winget…' Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Say 'winget недоступен.' Red
        Say 'Поставьте Python вручную: https://www.python.org/downloads/'
        Say 'При установке отметьте галочку "Add python.exe to PATH", затем повторите команду.'
        exit 1
    }
    winget install -e --id Python.Python.3.12 --scope user `
        --accept-package-agreements --accept-source-agreements
    Refresh-Path
    $python = Find-Python
    if (-not $python) {
        Say 'Python установлен, но не виден в этом окне.' Yellow
        Say 'Закройте PowerShell, откройте заново и повторите команду.'
        exit 1
    }
}
Say "Python: $python" Green

# --- 2. окружение ----------------------------------------------------------
if (Test-Path $VenvDir) {
    Say 'Обновляю существующую установку…'
} else {
    Say 'Создаю окружение…'
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    & $python -m venv $VenvDir
}
$VenvPy = Join-Path $VenvDir 'Scripts\python.exe'
if (-not (Test-Path $VenvPy)) { Say 'Не удалось создать окружение.' Red; exit 1 }

Say 'Ставлю программу и зависимости…'
& $VenvPy -m pip install --upgrade pip --quiet
& $VenvPy -m pip install --upgrade --force-reinstall $Repo --quiet
if ($LASTEXITCODE -ne 0) { Say 'Установка не удалась.' Red; exit 1 }

# --- 3. ярлык --------------------------------------------------------------
Say 'Создаю ярлык на рабочем столе…'
& $VenvPy -m dxf_close --install-shortcut

Say ''
Say 'Готово. Ярлык «Замыкание контуров DXF» лежит на рабочем столе.' Green
Say "Из командной строки: $VenvDir\Scripts\dxf-close.exe файл.dxf -r 0.2 --save" DarkGray
Say ''
