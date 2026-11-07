$ErrorActionPreference = 'Stop'
$paperDir = $PSScriptRoot
$repoDir = Split-Path -Parent $paperDir
Push-Location -LiteralPath $paperDir
try {
    & latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex
    if ($LASTEXITCODE -ne 0) { throw 'LaTeX compilation failed.' }
    $pdfDir = Join-Path $repoDir 'output\pdf'
    New-Item -ItemType Directory -Path $pdfDir -Force | Out-Null
    $target = Join-Path $pdfDir 'cotb2027-mimic-iv-ed-draft.pdf'
    Copy-Item -LiteralPath (Join-Path $paperDir 'build\main.pdf') -Destination $target
    Write-Output $target
} finally {
    Pop-Location
}
