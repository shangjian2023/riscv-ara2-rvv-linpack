$ErrorActionPreference = "Continue"
$ports = @()
foreach ($name in @("COM8","COM7")) {
    try {
        $p = New-Object System.IO.Ports.SerialPort($name, 115200, "None", 8, "One")
        $p.ReadTimeout = 200; $p.DtrEnable = $true; $p.RtsEnable = $true
        $p.Open(); $ports += ,@($name,$p)
        Write-Output "READY $name"
    } catch { Write-Output "OPENFAIL $name : $($_.Exception.Message)" }
}
$sw = [Diagnostics.Stopwatch]::StartNew()
$tot = @{}; foreach ($e in $ports) { $tot[$e[0]] = 0 }
while ($sw.ElapsedMilliseconds -lt 300000) {
    foreach ($e in $ports) {
        try {
            $s = $e[1].ReadExisting()
            if ($s) { $tot[$e[0]] += $s.Length
                Write-Output ("[$($e[0]) t={0,6}ms] >>>{1}<<<" -f $sw.ElapsedMilliseconds, ($s -replace "`r","{CR}" -replace "`n","{LF}")) }
        } catch {}
    }
    Start-Sleep -Milliseconds 150
}
foreach ($e in $ports) { $e[1].Close() }
Write-Output ("DONE " + (($tot.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join " "))
