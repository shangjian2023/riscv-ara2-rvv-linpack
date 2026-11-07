$ErrorActionPreference = "Continue"
$p = New-Object System.IO.Ports.SerialPort("COM8", 115200, "None", 8, "One")
$p.ReadTimeout = 200
$p.DtrEnable = $true; $p.RtsEnable = $true
$p.Open()
Write-Output "READY v2 - U-Boot aware, 30min budget"
$sw = [Diagnostics.Stopwatch]::StartNew()
$win = ""
$state = "detect"
$gotAny = $false       # any bytes received yet (gates the Enter-ping)
$pings = 0
$bootRetry = 0
while ($sw.ElapsedMilliseconds -lt 1800000) {
    try {
        $s = $p.ReadExisting()
        if ($s) {
            $gotAny = $true
            Write-Output $s
            $win = ($win + $s)
            if ($win.Length -gt 4096) { $win = $win.Substring($win.Length - 4096) }
        }
    } catch {}
    # single gentle wake-up ONLY while totally silent (board may wait at login)
    if (-not $gotAny -and $pings -lt 3 -and ($sw.ElapsedMilliseconds -gt 10000)) {
        $p.Write("`r`n"); $pings++
    }
    switch ($state) {
        "detect" {
            if ($win -match "K230#\s*$") {
                Write-Output ">>> [v2] U-Boot prompt -> boot"
                $p.Write("boot`r`n"); $win = ""; $state = "booting"
            } elseif ($win -match "login:?\s*$") {
                Write-Output ">>> [v2] linux login -> root"
                $p.Write("root`r`n"); $win = ""; $state = "linuxprompt"
            } elseif ($win -match "Hit any key|countdown|Starting kernel") {
                $win = ""; $state = "booting"   # do NOT touch the console
            }
        }
        "booting" {
            if ($win -match "login:?\s*$") {
                Write-Output ">>> [v2] login prompt -> root"
                $p.Write("root`r`n"); $win = ""; $state = "linuxprompt"
            } elseif ($win -match "K230#\s*$" -and $bootRetry -lt 2) {
                $bootRetry++
                Write-Output ">>> [v2] back at U-Boot, retry boot"
                $p.Write("boot`r`n"); $win = ""
            }
        }
        "linuxprompt" {
            if ($win -match "#\s*$") {
                Start-Sleep -Milliseconds 400
                Write-Output ">>> [v2] shell ready -> launching bench"
                $p.Write("grep -E 'model|isa|MHz' /proc/cpuinfo; echo B_BEGIN; cd / && ./bench; echo RC=`$?`r`n")
                $win = ""; $state = "bench"
            }
        }
        "bench" {
            if ($win -match "RC=0") {
                Write-Output ">>> [v2] BENCH COMPLETED (RC=0)"
                $p.Write("echo ALL_DONE`r`n"); $win = ""; $state = "done"
            } elseif ($win -match "RC=[1-9]") {
                Write-Output ">>> [v2] BENCH FAILED (nonzero exit)"
                $p.Write("echo ALL_FAIL`r`n"); $win = ""; $state = "done"
            }
        }
        "done" { }
    }
    Start-Sleep -Milliseconds 150
}
$p.Close()
Write-Output "SESSION_END"
