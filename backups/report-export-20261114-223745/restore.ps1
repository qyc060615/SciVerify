$ErrorActionPreference = 'Stop'
$targetRoot = 'C:\Users\19879\SciVerify1'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'frontend/src/components/manuscript/WholePaperReport.tsx') -Destination (Join-Path $targetRoot 'frontend/src/components/manuscript/WholePaperReport.tsx') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'backend/app/api/routes/verification_jobs.py') -Destination (Join-Path $targetRoot 'backend/app/api/routes/verification_jobs.py') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'backend/requirements.txt') -Destination (Join-Path $targetRoot 'backend/requirements.txt') -Force
Remove-Item -LiteralPath (Join-Path $targetRoot 'frontend/src/components/manuscript/ReportExportControls.tsx') -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $targetRoot 'frontend/src/components/manuscript/ReportExportSnapshot.tsx') -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $targetRoot 'frontend/src/services/wholePaperPdf.ts') -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $targetRoot 'frontend/src/services/reportFileSave.ts') -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $targetRoot 'backend/app/services/report_export.py') -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $targetRoot 'backend/app/services/report_editor.py') -ErrorAction SilentlyContinue