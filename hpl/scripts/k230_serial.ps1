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
        # Wait for a recognizable console state, then log in only if needed.
        # Handles: already-logged-in shell, login prompt, or board still booting.
        $deadline = [Diagnostics.Stopwatch]::StartNew()
        $ready = $false
        while (-not $ready -and $deadline.Elapsed.TotalSeconds -lt 25) {
            $p.Write("`r`n")
            Start-Sleep -Milliseconds 1200
            $probe = $p.ReadExisting()
            if ($probe) { Write-Output $probe }
            if ($probe -match 'login:\s*$') {
                $p.Write("root`r`n")
                Start-Sleep -Seconds 2
                $loginOut = $p.ReadExisting()
                if ($loginOut) { Write-Output $loginOut }
                if ($loginOut -match 'Password:\s*$') {
                    $p.Write("`r`n")
                    Start-Sleep -Seconds 2
                    $pwOut = $p.ReadExisting()
                    if ($pwOut) { Write-Output $pwOut }
                }
                $ready = $true
            } elseif ($probe -match '[#]\s*$') {
                # Already at a root shell; nothing to do.
                $ready = $true
            }
        }
        if (-not $ready) {
            Write-Output "WARN: no shell or login prompt detected within 25s; sending command anyway"
        }
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
