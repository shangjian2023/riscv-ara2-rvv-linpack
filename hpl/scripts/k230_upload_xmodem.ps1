param(
    [Parameter(Mandatory=$true)][string]$FilePath,
    [Parameter(Mandatory=$true)][string]$RemotePath,
    [string]$Port = "COM3",
    [int]$TimeoutSec = 900
)

$ErrorActionPreference = "Stop"
$SOH = 0x01
$EOT = 0x04
$ACK = 0x06
$NAK = 0x15
$CAN = 0x18
$CRC = 0x43
$BLOCK_SIZE = 128

function Get-Crc16([byte[]]$Data, [int]$Offset, [int]$Count) {
    [uint32]$crc = 0
    for ($i = 0; $i -lt $Count; $i++) {
        $crc = $crc -bxor ([uint32]$Data[$Offset + $i] -shl 8)
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($crc -band 0x8000) -ne 0) {
                $crc = (($crc -shl 1) -bxor 0x1021) -band 0xFFFF
            } else {
                $crc = ($crc -shl 1) -band 0xFFFF
            }
        }
    }
    return $crc
}

function Read-ProtocolByte($Serial, [int]$TimeoutMs) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.ElapsedMilliseconds -lt $TimeoutMs) {
        if ($Serial.BytesToRead -gt 0) {
            return $Serial.ReadByte()
        }
        Start-Sleep -Milliseconds 10
    }
    return -1
}

if ($RemotePath -notmatch '^/[A-Za-z0-9._/-]+$' -or $RemotePath -match '(^|/)\.\.(/|$)') {
    throw "RemotePath must be a simple absolute POSIX path; when calling from Git Bash set MSYS2_ARG_CONV_EXCL=*"
}
$bytes = [IO.File]::ReadAllBytes((Resolve-Path $FilePath))
$localHash = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
$remoteDir = [regex]::Replace($RemotePath, '/[^/]+$', '')
$p = New-Object System.IO.Ports.SerialPort($Port, 115200, "None", 8, "One")
$p.ReadTimeout = 200
$p.WriteTimeout = 5000
$p.DtrEnable = $true
$p.RtsEnable = $true
$sw = [Diagnostics.Stopwatch]::StartNew()
try {
    $p.Open()
    Start-Sleep -Milliseconds 300
    [void]$p.ReadExisting()
    $p.Write([byte[]]@(17, 24, 24, 3, 17), 0, 5)
    $p.Write("`r`n")
    Start-Sleep -Milliseconds 800
    $initial = $p.ReadExisting()
    if ($initial -match 'login:\s*$') {
        $p.Write("root`r`n")
        Start-Sleep -Seconds 2
        $initial += $p.ReadExisting()
    }
    if ($initial -match 'Password:\s*$') {
        throw "K230 is waiting for a password; log in before uploading"
    }
    if ($initial -notmatch '\[root@canaan[^\r\n]*\]#\s*$') {
        throw "K230 root shell prompt not detected; refusing to upload blindly; initial output: $initial"
    }

    [void]$p.ReadExisting()
    $p.Write("mkdir -p $remoteDir && echo __XMODEM_READY__ && rx -b $RemotePath`r`n")
    $request = -1
    $startup = ""
    $receiverReady = $false
    $startupWatch = [Diagnostics.Stopwatch]::StartNew()
    while ($startupWatch.ElapsedMilliseconds -lt 15000) {
        $value = Read-ProtocolByte $p 1000
        if ($value -ge 0) { $startup += [char]$value }
        if (-not $receiverReady) {
            if ($startup -match '[\r\n]__XMODEM_READY__[\r\n]') { $receiverReady = $true }
            continue
        }
        if ($value -eq $CRC -or $value -eq $NAK) {
            $request = $value
            break
        }
        if ($value -eq $CAN) { throw "XMODEM receiver cancelled during startup" }
    }
    if ($request -ne $CRC -and $request -ne $NAK) {
        throw "XMODEM receiver did not start; startup output: $startup"
    }
    $useCrc = $request -eq $CRC
    $mode = if ($useCrc) { "CRC16" } else { "checksum" }
    Write-Output "Receiver ready; mode=$mode, bytes=$($bytes.Length)"

    $blockNumber = 1
    $offset = 0
    $nextReport = 131072
    while ($offset -lt $bytes.Length) {
        if ($sw.Elapsed.TotalSeconds -gt $TimeoutSec) {
            throw "Upload timed out after $TimeoutSec seconds"
        }
        $count = [Math]::Min($BLOCK_SIZE, $bytes.Length - $offset)
        $packetLength = if ($useCrc) { $BLOCK_SIZE + 5 } else { $BLOCK_SIZE + 4 }
        [byte[]]$packet = New-Object byte[] $packetLength
        $packet[0] = $SOH
        $packet[1] = [byte]($blockNumber -band 0xFF)
        $packet[2] = [byte](255 - $packet[1])
        for ($i = 0; $i -lt $BLOCK_SIZE; $i++) {
            $packet[3 + $i] = if ($i -lt $count) { $bytes[$offset + $i] } else { 0x1A }
        }
        if ($useCrc) {
            [uint32]$crc = Get-Crc16 $packet 3 $BLOCK_SIZE
            $packet[$packet.Length - 2] = [byte](($crc -shr 8) -band 0xFF)
            $packet[$packet.Length - 1] = [byte]($crc -band 0xFF)
        } else {
            [uint32]$sum = 0
            for ($i = 0; $i -lt $BLOCK_SIZE; $i++) { $sum += $packet[3 + $i] }
            $packet[$packet.Length - 1] = [byte]($sum -band 0xFF)
        }

        $accepted = $false
        for ($attempt = 1; $attempt -le 10 -and -not $accepted; $attempt++) {
            $p.Write($packet, 0, $packet.Length)
            $reply = Read-ProtocolByte $p 10000
            if ($reply -eq $ACK) {
                $accepted = $true
            } elseif ($reply -eq $CAN) {
                throw "Receiver cancelled at offset $offset"
            } elseif ($reply -eq $CRC -or $reply -eq $NAK) {
                [void](Read-ProtocolByte $p 100)
            }
        }
        if (-not $accepted) {
            throw "Block $blockNumber was not acknowledged at offset $offset"
        }
        $offset += $count
        $blockNumber++
        if ($offset -ge $nextReport -or $offset -eq $bytes.Length) {
            $pct = [math]::Round(100.0 * $offset / $bytes.Length, 1)
            Write-Output "upload $pct% ($offset/$($bytes.Length) bytes)"
            $nextReport += 131072
        }
    }

    $finished = $false
    for ($attempt = 1; $attempt -le 10 -and -not $finished; $attempt++) {
        $p.Write([byte[]]@($EOT), 0, 1)
        $reply = Read-ProtocolByte $p 10000
        if ($reply -eq $ACK) { $finished = $true }
    }
    if (-not $finished) { throw "Receiver did not acknowledge end of transfer" }
    Start-Sleep -Milliseconds 500
    [void]$p.ReadExisting()
    $p.Write("python3 -c `"import os; os.truncate('$RemotePath',$($bytes.Length))`" && sha256sum $RemotePath`r`n")
    $verifyOutput = ""
    $remoteHash = $null
    $verifyWatch = [Diagnostics.Stopwatch]::StartNew()
    while ($verifyWatch.Elapsed.TotalSeconds -lt 60) {
        $value = Read-ProtocolByte $p 1000
        if ($value -ge 0) { $verifyOutput += [char]$value }
        $match = [regex]::Match($verifyOutput, '(?m)^([0-9a-f]{64})\s+' + [regex]::Escape($RemotePath) + '\s*$')
        if ($match.Success) {
            $remoteHash = $match.Groups[1].Value
            break
        }
    }
    if ($null -eq $remoteHash) {
        throw "Could not read remote SHA-256; output: $verifyOutput"
    }
    if ($remoteHash -ne $localHash) {
        throw "SHA-256 mismatch: local=$localHash remote=$remoteHash"
    }
    Write-Output "TRANSFER_VERIFIED path=$RemotePath bytes=$($bytes.Length) sha256=$localHash"
} finally {
    if ($p.IsOpen) { $p.Close() }
}
