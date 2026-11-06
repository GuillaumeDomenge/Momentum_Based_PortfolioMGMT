param(
    [int]$BatchSize = 50
)

$ErrorActionPreference = "Stop"
$projectDirectory = Split-Path -Parent $PSScriptRoot
$attemptsPath = Join-Path $projectDirectory "data\raw\tiingo\attempts.json"
$queuePath = Join-Path $projectDirectory "data\processed\tiingo_remaining.csv"

if ($BatchSize -lt 1 -or $BatchSize -gt 50) {
    throw "BatchSize must be between 1 and 50."
}

Set-Location -LiteralPath $projectDirectory
& momentum-fill-tiingo --config config.yaml --dry-run
if ($LASTEXITCODE -ne 0) {
    throw "Unable to refresh the Tiingo remaining-ticker list."
}

$queue = @(Import-Csv -LiteralPath $queuePath)
$unattempted = @($queue | Where-Object { $_.status -eq "unattempted" })
$failed = @($queue | Where-Object { $_.status -eq "failed" })

Write-Host "Remaining tickers: $($queue.Count) ($($unattempted.Count) unattempted, $($failed.Count) failed)."
if ($unattempted.Count -eq 0) {
    Write-Host "No unattempted tickers remain. Failed identifiers require mapping or --retry-failed."
    exit 0
}

if (Test-Path -LiteralPath $attemptsPath) {
    $attempts = Get-Content -LiteralPath $attemptsPath -Raw | ConvertFrom-Json
    $cutoff = [datetimeoffset]::UtcNow.AddMinutes(-60)
    $recentAttempts = @(
        $attempts.PSObject.Properties.Value |
            Where-Object {
                $_.attempted_at_utc -and ([datetimeoffset]$_.attempted_at_utc) -gt $cutoff
            }
    )
    if ($recentAttempts.Count -gt 0) {
        $latest = $recentAttempts |
            ForEach-Object { [datetimeoffset]$_.attempted_at_utc } |
            Sort-Object -Descending |
            Select-Object -First 1
        $minutesRemaining = [math]::Ceiling(60 - ([datetimeoffset]::UtcNow - $latest).TotalMinutes)
        throw "Tiingo was used within the last hour. Retry in approximately $minutesRemaining minutes."
    }
}

$requestCount = [math]::Min($BatchSize, $unattempted.Count)
Write-Host "Attempting $requestCount previously unattempted tickers."
& momentum-fill-tiingo --config config.yaml --max-symbols $requestCount
if ($LASTEXITCODE -ne 0) {
    throw "Tiingo batch failed with exit code $LASTEXITCODE."
}

$updated = @(Import-Csv -LiteralPath $queuePath)
$updatedUnattempted = @($updated | Where-Object { $_.status -eq "unattempted" })
$updatedFailed = @($updated | Where-Object { $_.status -eq "failed" })
Write-Host "After batch: $($updated.Count) unresolved ($($updatedUnattempted.Count) unattempted, $($updatedFailed.Count) failed)."
