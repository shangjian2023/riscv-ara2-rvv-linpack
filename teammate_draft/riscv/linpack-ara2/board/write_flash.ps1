# flash.ps1 - K230 image raw write (ASCII paths only, run ELEVATED)
$ErrorActionPreference = "Stop"
Start-Transcript -Path "D:\k230_flash\log.txt" -Force
$Img = "D:\k230_flash\image.img"

# ---- safety gate: Disk 1 must be a 8-40GB USB disk ----
$d = Get-Disk -Number 1
if ($d.BusType -ne "USB" -or $d.Size -gt 40GB -or $d.Size -lt 8GB) {
    Write-Output ("ABORT: Disk 1 is {0} {1}GB - not the expected SD card" -f $d.BusType, [math]::Round($d.Size/1GB,1))
    Stop-Transcript
    exit 1
}
Write-Output ("target OK: Disk 1 {0} {1}GB {2}" -f $d.FriendlyName, [math]::Round($d.Size/1GB,1), $d.BusType)
try { Clear-Disk -Number 1 -RemoveData -RemoveOEM -Confirm:$false; Write-Output "cleared" } catch { Write-Output "clear skipped: $($_.Exception.Message)" }

# ---- raw write ----
$src = [System.IO.File]::OpenRead($Img)
$dst = [System.IO.File]::Open("\\.\PhysicalDrive1", "Open", "ReadWrite", "ReadWrite")
$buf = New-Object byte[] (4MB)
$written = 0L
$t0 = [Diagnostics.Stopwatch]::StartNew()
while (($n = $src.Read($buf, 0, $buf.Length)) -gt 0) {
    $dst.Write($buf, 0, $n)
    $written += $n
    if ($t0.ElapsedMilliseconds -gt 10000) {
        Write-Output ("progress {0:N0}/{1:N0} MB" -f ($written/1MB), ($src.Length/1MB))
        $t0.Restart()
    }
}
$dst.Flush()
$dst.Close(); $src.Close()
Write-Output ("WRITE_DONE {0:N0} bytes" -f $written)
Write-Output "FLASH_OK - eject the card now"
Stop-Transcript
