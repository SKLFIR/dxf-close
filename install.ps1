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

# Версию и tkinter проверяем ПОРОЗНЬ. Если требовать их разом, Python без tcl/tk
# выглядит как отсутствующий, и установщик уходит ставить второй Python вместо того,
# чтобы сказать, чего именно не хватает.
# Внутри проб НЕ должно быть двойных кавычек: PowerShell 5.1 портит их при
# передаче аргумента во внешний exe, и Python получает битый код.
$ProbeVersion = 'import sys; print(sys.version_info[0]*100+sys.version_info[1]); print(sys.executable)'
$ProbeTk      = 'import tkinter; print(1)'

$script:Checked = @()

function Last-Line($value) {
    # вывод команды может прийти массивом строк — берём последнюю непустую
    if ($null -eq $value) { return '' }
    $line = @($value) | Where-Object { $_ -and "$_".Trim() } | Select-Object -Last 1
    if ($null -eq $line) { return '' }
    return "$line".Trim()
}

function Test-PythonExe($exe, $launcher = $false) {
    if (-not $exe) { return $null }
    try {
        if ($launcher) { $out = & $exe '-3' '-c' $ProbeVersion 2>$null }
        else           { $out = & $exe '-c' $ProbeVersion 2>$null }
        $lines = @(@($out) | Where-Object { $_ -and "$_".Trim() } | ForEach-Object { "$_".Trim() })
        if ($lines.Count -lt 2) {
            $script:Checked += "$exe — не отвечает как Python"
            return $null
        }
        if ($lines[0] -notmatch '^\d+$') {
            $script:Checked += "$exe — не отвечает как Python"
            return $null
        }
        if ([int]$lines[0] -lt 309) {
            $script:Checked += "$exe — версия ниже 3.9"
            return $null
        }
        $real = $lines[1]
        if (-not (Test-Path $real)) { $real = $exe }
        $tk = & $real '-c' $ProbeTk 2>$null
        $hasTk = ((Last-Line $tk) -eq '1')
        if (-not $hasTk) { $script:Checked += "$real — есть, но без модуля tkinter" }
        return [pscustomobject]@{ Path = $real; Tk = $hasTk }
    } catch {
        $script:Checked += "$exe — запустить не удалось"
    }
    return $null
}

function Get-PythonCandidates {
    $cands = @()

    # 1. реестр — самый надёжный источник: сюда пишутся и python.org, и winget
    foreach ($root in @('HKLM:\SOFTWARE\Python\PythonCore',
                        'HKCU:\SOFTWARE\Python\PythonCore',
                        'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore')) {
        if (-not (Test-Path $root)) { continue }
        foreach ($key in (Get-ChildItem $root -ErrorAction SilentlyContinue)) {
            $ipKey = Join-Path $key.PSPath 'InstallPath'
            if (-not (Test-Path $ipKey)) { continue }
            $props = Get-ItemProperty $ipKey -ErrorAction SilentlyContinue
            if (-not $props) { continue }
            $exe = $props.ExecutablePath
            if (-not $exe -and $props.'(default)') { $exe = Join-Path $props.'(default)' 'python.exe' }
            if ($exe -and (Test-Path $exe)) { $cands += $exe }
        }
    }

    # 2. обычные места установки; %LOCALAPPDATA%\Python — это Python Install Manager
    $roots = @((Join-Path $env:LOCALAPPDATA 'Programs\Python'),
               (Join-Path $env:LOCALAPPDATA 'Python'),
               'C:\Program Files', 'C:\')
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        foreach ($dir in (Get-ChildItem $root -Directory -Filter 'Python*' -ErrorAction SilentlyContinue)) {
            $exe = Join-Path $dir.FullName 'python.exe'
            if (Test-Path $exe) { $cands += $exe }
            foreach ($sub in (Get-ChildItem $dir.FullName -Directory -ErrorAction SilentlyContinue)) {
                $exe = Join-Path $sub.FullName 'python.exe'
                if (Test-Path $exe) { $cands += $exe }
            }
        }
    }
    return ($cands | Select-Object -Unique)
}

function Find-Python {
    $withoutTk = $null

    # явно указанный путь имеет приоритет:
    #   $env:DXFCLOSE_PYTHON = 'C:\...\python.exe'
    $probes = @()
    if ($env:DXFCLOSE_PYTHON) { $probes += ,@($env:DXFCLOSE_PYTHON, $false) }

    # py launcher и PATH
    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher) { $probes += ,@($launcher.Source, $true) }
    foreach ($name in @('python3', 'python')) {
        $exe = Get-Command $name -ErrorAction SilentlyContinue
        # заглушка Microsoft Store живёт там же, но она просто не пройдёт проверку
        if ($exe) { $probes += ,@($exe.Source, $false) }
    }
    foreach ($c in (Get-PythonCandidates)) { $probes += ,@($c, $false) }

    foreach ($p in $probes) {
        $res = Test-PythonExe $p[0] $p[1]
        if (-not $res) { continue }
        if ($res.Tk) { return $res.Path }
        if (-not $withoutTk) { $withoutTk = $res.Path }
    }

    if ($withoutTk) {
        Say 'Python есть, но собран без модуля tkinter — окно программы без него не откроется.' Yellow
        Say 'Переустановите Python с python.org, отметив компонент "tcl/tk and IDLE".' Yellow
        return $withoutTk
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

    if ($env:DXFCLOSE_PYTHON) {
        Say "Указанный путь не подошёл: $env:DXFCLOSE_PYTHON" Yellow
    }

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
    $script:Checked = @()
    $python = Find-Python
    if (-not $python) {
        Say ''
        Say 'Python поставить не удалось.' Red
        if ($script:Checked.Count) {
            Say 'Что проверялось:' DarkGray
            foreach ($line in ($script:Checked | Select-Object -Unique)) { Say "  $line" DarkGray }
        }
        Say ''
        Say 'Поставьте вручную: https://www.python.org/downloads/windows/'
        Say 'Нужен файл вида python-3.12.10-amd64.exe — "Windows installer (64-bit)".'
        Say 'Это .exe, а не архив с исходниками (.tar.xz / .zip — не подойдут).'
        Say 'При установке отметьте "Add python.exe to PATH" и компонент "tcl/tk and IDLE".'
        Say 'Затем повторите команду установки.'
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
