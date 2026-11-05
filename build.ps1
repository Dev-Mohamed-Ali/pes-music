$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.venv')) { py -3.12 -m venv .venv }
.\.venv\Scripts\python -m pip install -q -e '.[build]'

$env:PYTHONPATH = 'src'
.\.venv\Scripts\python -m unittest discover tests
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }

.\.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name PESMusic `
    --icon assets\icon.ico `
    --add-binary 'tools\VGAudioCli.exe;tools' `
    --add-data 'assets\icon.ico;assets' `
    --collect-data customtkinter `
    --paths src `
    src\PESMusic.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }

Write-Host "Built: $PSScriptRoot\dist\PESMusic.exe" -ForegroundColor Green
