# ============================================================
# CareLens 360 - Snowflake Upload
# DOWNLOAD SNOWFLAKE CLI TO UPLOAD ALL FILES TO STAGE VIA POWERSHELL
# ============================================================

$BASE = "<local dataset path>"
$STAGE = "@<internal stage>"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " CareLens 360 - Snowflake Upload" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan


# ------------------------------------------------------------
# 1. STRUCTURED CSV FILES
# ------------------------------------------------------------

Write-Host ""
Write-Host "[1/7] Uploading structured CSV files..." -ForegroundColor Yellow

snow sql -q "PUT 'file:///$BASE/structured/*.csv' '$STAGE/STRUCTURED/' AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Structured upload failed." -ForegroundColor Red
    exit 1
}


# ------------------------------------------------------------
# 2. CLINICAL NOTES
# ------------------------------------------------------------

Write-Host ""
Write-Host "[2/7] Uploading clinical notes..." -ForegroundColor Yellow

snow sql -q "PUT 'file:///$BASE/documents/clinical_notes/*' '$STAGE/UNSTRUCTURED/CLINICAL_DOCUMENTS/CLINICAL_NOTES/' AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Clinical notes upload failed." -ForegroundColor Red
    exit 1
}


# ------------------------------------------------------------
# 3. DISCHARGE SUMMARIES
# ------------------------------------------------------------

Write-Host ""
Write-Host "[3/7] Uploading discharge summaries..." -ForegroundColor Yellow

snow sql -q "PUT 'file:///$BASE/documents/discharge_summaries/*' '$STAGE/UNSTRUCTURED/CLINICAL_DOCUMENTS/DISCHARGE_SUMMARIES/' AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Discharge summaries upload failed." -ForegroundColor Red
    exit 1
}


# ------------------------------------------------------------
# 4. SCANNED DOCUMENTS
# ------------------------------------------------------------

Write-Host ""
Write-Host "[4/7] Uploading scanned documents..." -ForegroundColor Yellow

snow sql -q "PUT 'file:///$BASE/documents/scanned/*' '$STAGE/UNSTRUCTURED/CLINICAL_DOCUMENTS/SCANNED/' AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Scanned documents upload failed." -ForegroundColor Red
    exit 1
}


# ------------------------------------------------------------
# 5. REGULATORY DOCUMENTS
# ------------------------------------------------------------

Write-Host ""
Write-Host "[5/7] Uploading regulatory documents..." -ForegroundColor Yellow

snow sql -q "PUT 'file:///$BASE/documents/regulatory/*' '$STAGE/UNSTRUCTURED/REGULATORY/' AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Regulatory upload failed." -ForegroundColor Red
    exit 1
}


# ------------------------------------------------------------
# 6. SAFETY DOCUMENTS
# ------------------------------------------------------------

Write-Host ""
Write-Host "[6/7] Uploading safety documents..." -ForegroundColor Yellow

snow sql -q "PUT 'file:///$BASE/documents/safety/*' '$STAGE/UNSTRUCTURED/SAFETY/' AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Safety upload failed." -ForegroundColor Red
    exit 1
}




# ------------------------------------------------------------
# VERIFY
# ------------------------------------------------------------

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Upload completed successfully!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "Verifying stage contents..." -ForegroundColor Yellow

snow sql -q "LIST $STAGE;"
