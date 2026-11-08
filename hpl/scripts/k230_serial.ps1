param(
    [Parameter(Mandatory=$true)][string]$Command,
    [string]$Port = "COM3",
    [int]$TimeoutSec = 60,
    [switch]$Login
)

$ErrorActionPreference = "Stop"
$p = New-Object System.IO.Ports.SerialPort($Port, 115200, "None", 8, "One")
$p.ReadTimeout = 200
$p.DtrEnable = $true
$p.RtsEnable = $true
try {
    $p.Open()
    if ($Login) {
        $p.Write("root`r`n")
        Start-Sleep -Seconds 2
        $initial = $p.ReadExisting()
        if ($initial) { Write-Output $initial }
    }
    $p.Write($Command + "`r`n")
    $p.Write('echo __K230_RC__=$?' + "`r`n")
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $all = ""
    $rc = $null
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        $s = $p.ReadExisting()
        if ($s) {
            Write-Output $s
            $all += $s
            if ($all.Length -gt 131072) { $all = $all.Substring($all.Length - 131072) }
            $m = [regex]::Match($all, '__K230_RC__=(\d+)')
            if ($m.Success) { $rc = [int]$m.Groups[1].Value; break }
        }
        Start-Sleep -Milliseconds 100
    }
    if ($null -eq $rc) {
        Write-Error "Timed out after $TimeoutSec seconds waiting for K230 command completion"
        exit 124
    }
    exit $rc
} finally {
    if ($p.IsOpen) { $p.Close() }
}
