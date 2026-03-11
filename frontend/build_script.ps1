$ErrorActionPreference = "Stop"
$tempDir = Join-Path $env:TEMP "frontend_build"

npm cache clean --force

if (Test-Path $tempDir) { Remove-Item -Path $tempDir -Recurse -Force }
New-Item -ItemType Directory -Path $tempDir | Out-Null
Copy-Item -Path "g:\My Drive\Python\PDFoverseer\frontend\*" -Destination $tempDir -Recurse -Force -Exclude "node_modules", "dist"
Set-Location $tempDir

if (Test-Path "node_modules") { Remove-Item -Path "node_modules" -Recurse -Force }
if (Test-Path "package-lock.json") { Remove-Item -Path "package-lock.json" -Force }

npm install
npm run build

if (Test-Path "dist") {
    $targetDist = "g:\My Drive\Python\PDFoverseer\frontend\dist"
    if (Test-Path $targetDist) { Remove-Item -Path $targetDist -Recurse -Force }
    Copy-Item -Path "dist" -Destination "g:\My Drive\Python\PDFoverseer\frontend\" -Recurse -Force
    Write-Host "Build completed and copied successfully."
} else {
    Write-Host "Build failed."
}
