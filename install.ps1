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

$Probe = 'import sys, tkinter; print(sys.executable if sys.version_info[:2] >= (3, 9) else "")'

function Test-PythonExe($exe) {
    try {
        $out = & $exe '-c' $Probe 2>$null
        if ($out -and $out.Trim()) { return $out.Trim() }
    } catch { }
    return $null
}

function Test-PythonLauncher($exe) {
    try {
        $out = & $exe '-3' '-c' $Probe 2>$null
        if ($out -and $out.Trim()) { return $out.Trim() }
    } catch { }
    return $null
}

function Find-Python {
    # сначала то, что в PATH
    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher -and $launcher.Source -notlike '*WindowsApps*') {
        $found = Test-PythonLauncher $launcher.Source
        if ($found) { return $found }
    }
    foreach ($name in @('python3', 'python')) {
        $exe = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        # заглушка из Microsoft Store — не Python, а редирект в магазин
        if ($exe.Source -like '*WindowsApps*') { continue }
        $found = Test-PythonExe $exe.Source
        if ($found) { return $found }
    }
    # затем обычные места установки: свежий winget/python.org мог не попасть в PATH
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        'C:\Program Files\Python312', 'C:\Program Files\Python313', 'C:\Program Files\Python311'
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $exes = Get-ChildItem -Path $root -Filter 'python.exe' -Recurse -Depth 2 -ErrorAction SilentlyContinue
        foreach ($e in ($exes | Sort-Object FullName -Descending)) {
            $found = Test-PythonExe $e.FullName
            if ($found) { return $found }
        }
    }
    return $null
}

function Install-PythonFromOrg {
    # winget не всегда доступен: источник msstore может не отвечать, а сам winget
    # отсутствовать на старых сборках. Официальный установщик работает всегда.
    $ver = '3.12.10'
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $url = "https://www.python.org/ftp/python/$ver/python-$ver-$arch.exe"
    $dst = Join-Path $env:TEMP "python-$ver-$arch.exe"
    Say "Качаю Python $ver с python.org…"
    Invoke-WebRequest -Uri $url -OutFile $dst -UseBasicParsing
    Say 'Устанавливаю (это займёт минуту)…'
    $p = Start-Process -FilePath $dst -Wait -PassThru -ArgumentList @(
        '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_tcltk=1',
        'Include_pip=1', 'Include_test=0'
    )
    Remove-Item $dst -ErrorAction SilentlyContinue
    return ($p.ExitCode -eq 0 -or $p.ExitCode -eq 3010)
}

Say ''
Say '=== Замыкание контуров DXF — установка ===' Cyan
Say ''

# --- 1. Python -------------------------------------------------------------
$python = Find-Python
if (-not $python) {
    Say 'Python не найден, ставлю…' Yellow
    $ok = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        # --source winget обязателен: иначе при недоступном msstore winget
        # считает пакет неоднозначным и молча ничего не ставит
        winget install -e --id Python.Python.3.12 --source winget --scope user `
            --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) { $ok = $true }
        else { Say 'winget не справился, пробую установщик с python.org…' Yellow }
    }
    if (-not $ok) {
        try { $ok = Install-PythonFromOrg }
        catch { Say "Не удалось скачать Python: $_" Red; $ok = $false }
    }
    Refresh-Path
    $python = Find-Python
    if (-not $python) {
        Say 'Python поставить не удалось.' Red
        Say 'Поставьте вручную: https://www.python.org/downloads/'
        Say 'Обязательно отметьте галочку "Add python.exe to PATH", затем повторите команду.'
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
$PipOpts = @('--retries', '5', '--timeout', '60', '--quiet')
& $VenvPy -m pip install --upgrade pip @PipOpts
& $VenvPy -m pip install --upgrade --force-reinstall $Repo @PipOpts
if ($LASTEXITCODE -ne 0) { Say 'Установка не удалась.' Red; exit 1 }

# --- 3. ярлык --------------------------------------------------------------
Say 'Создаю ярлык на рабочем столе…'
& $VenvPy -m dxf_close --install-shortcut

Say ''
Say 'Готово. Ярлык «Замыкание контуров DXF» лежит на рабочем столе.' Green
Say "Из командной строки: $VenvDir\Scripts\dxf-close.exe файл.dxf -r 0.2 --save" DarkGray
Say ''
