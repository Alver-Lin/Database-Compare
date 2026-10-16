# Build a folder other people can start without Node or a project virtualenv.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$release = Join-Path $root "release\数据库对比工具"
$runtime = Join-Path $release "runtime"
$pyVersion = "3.12.10"
$embedUrl = "https://www.python.org/ftp/python/$pyVersion/python-$pyVersion-embed-amd64.zip"
$embedZip = Join-Path $env:TEMP "python-$pyVersion-embed-amd64.zip"
$getPip = Join-Path $env:TEMP "get-pip.py"

Write-Host "Building frontend..."
Push-Location (Join-Path $root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
Pop-Location

if (Test-Path $release) {
    Remove-Item $release -Recurse -Force
}
New-Item -ItemType Directory -Path $release | Out-Null
New-Item -ItemType Directory -Path (Join-Path $release "backend\app\routers") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $release "backend\drivers") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $release "backend\data") | Out-Null

Copy-Item (Join-Path $root "backend\app\*.py") (Join-Path $release "backend\app")
Copy-Item (Join-Path $root "backend\app\routers\*.py") (Join-Path $release "backend\app\routers")
Copy-Item (Join-Path $root "backend\requirements.txt") (Join-Path $release "backend")
Copy-Item (Join-Path $root "backend\drivers\*.jar") (Join-Path $release "backend\drivers")
Copy-Item (Join-Path $root "backend\drivers\*.class") (Join-Path $release "backend\drivers")
Copy-Item (Join-Path $root "frontend\dist") (Join-Path $release "web") -Recurse

$jreZip = Join-Path $env:TEMP "temurin17-jre-win-x64.zip"
if (-not (Test-Path $jreZip) -or (Get-Item $jreZip).Length -lt 20MB) {
    Write-Host "Downloading portable Java..."
    $urls = @(
        "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse",
        "https://github.com/adoptium/temurin17-binaries/releases/latest/download/OpenJDK17U-jre_x64_windows_hotspot.zip"
    )
    $downloaded = $false
    foreach ($url in $urls) {
        try {
            curl.exe -L --fail --retry 2 -o $jreZip $url
            if ($LASTEXITCODE -eq 0 -and (Test-Path $jreZip) -and (Get-Item $jreZip).Length -gt 20MB) {
                $downloaded = $true
                break
            }
        } catch {}
    }
    if (-not $downloaded) { throw "portable Java download failed" }
}
$jreStage = Join-Path $env:TEMP "temurin17-jre-stage"
if (Test-Path $jreStage) { Remove-Item $jreStage -Recurse -Force }
Expand-Archive -Path $jreZip -DestinationPath $jreStage -Force
$jreHome = Get-ChildItem $jreStage -Directory | Where-Object { Test-Path (Join-Path $_.FullName "bin\java.exe") } | Select-Object -First 1
if (-not $jreHome) { throw "java.exe not found in downloaded JRE" }
$jreDest = Join-Path $release "jre"
if (Test-Path $jreDest) { Remove-Item $jreDest -Recurse -Force }
Move-Item $jreHome.FullName $jreDest

Write-Host "Downloading Python $pyVersion ..."
Invoke-WebRequest -Uri $embedUrl -OutFile $embedZip
if (-not (Test-Path $getPip) -or (Get-Item $getPip).Length -lt 1000) {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
}
Expand-Archive -Path $embedZip -DestinationPath $runtime -Force
$pth = Get-ChildItem $runtime -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) { throw "embeddable python ._pth not found" }
$pthText = Get-Content $pth.FullName -Raw
$pthText = $pthText -replace "#import site", "import site"
if ($pthText -notmatch "Lib\\site-packages") {
    $pthText = $pthText.TrimEnd() + "`r`nLib\site-packages`r`n"
}
Set-Content -Path $pth.FullName -Value $pthText -Encoding ascii

$python = Join-Path $runtime "python.exe"
Write-Host "Installing Python packages..."
& $python $getPip
if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }
& $python -m pip install --disable-pip-version-check -r (Join-Path $release "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$bat = @'
@echo off
cd /d "%~dp0"
set "PATH=%~dp0jre\bin;%PATH%"
echo Database comparison tool
echo Local: http://127.0.0.1:8765/
echo LAN:   http://THIS-PC-IP:8765/
echo Close this window to stop.
echo.
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8765/"
runtime\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8765
'@
$gbk = [System.Text.Encoding]::GetEncoding(936)
[System.IO.File]::WriteAllText((Join-Path $release "启动.bat"), $bat.Replace("`n", "`r`n"), $gbk)

$readme = @'
数据库对比工具

1. 双击「启动.bat」。
2. 浏览器会打开 http://127.0.0.1:8765/ 。若没有自动打开，手动访问这个地址。
3. 同一局域网的其他人把 127.0.0.1 换成这台电脑的 IP，端口仍是 8765。
4. 关掉黑色命令行窗口，服务就停止。

依赖：
- 压缩包里已经带了 Python 和 Java，对方电脑不用单独安装。
- 达梦、OceanBase、MySQL、PostgreSQL、SQLite、Oracle 都可以直接连。

任务数据保存在 backend\data\app.db。不要把这个文件发给不相关的人，里面有数据库连接信息。
'@
$utf8bom = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllText((Join-Path $release "使用说明.txt"), $readme.Replace("`n", "`r`n"), $utf8bom)

$zip = Join-Path ([Environment]::GetFolderPath("Desktop")) "数据库对比工具.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $release -DestinationPath $zip
Write-Host "Package: $release"
Write-Host "Zip: $zip"
