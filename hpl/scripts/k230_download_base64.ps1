param(
    [Parameter(Mandatory=$true)][string]$RemotePath,
    [Parameter(Mandatory=$true)][string]$FilePath,
    [string]$Port = "COM3",
    [int]$TimeoutSec = 120,
    [string]$ExpectedSHA256 = ""
)

$ErrorActionPreference = "Stop"
if ($RemotePath -notmatch '^/[A-Za-z0-9._/-]+$' -or $RemotePath -match '(^|/)\.\.(/|$)') {
    throw "RemotePath must be a simple absolute POSIX path; when calling from Git Bash set MSYS2_ARG_CONV_EXCL=*"
}
$p = New-Object System.IO.Ports.SerialPort($Port, 115200, "None", 8, "One")
$p.ReadTimeout = 200
$p.DtrEnable = $true
$p.RtsEnable = $true
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
    if ($initial -match 'Password:\s*$') { throw "K230 is waiting for a password" }
    if ($initial -notmatch '\[root@canaan[^\r\n]*\]#\s*$') {
        throw "K230 root shell prompt not detected; output: $initial"
    }

    [void]$p.ReadExisting()
    $p.Write("echo __K230_DOWNLOAD_BEGIN__; base64 $RemotePath; echo __K230_DOWNLOAD_END__`r`n")
    $all = ""
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        $s = $p.ReadExisting()
        if ($s) {
            $all += $s
            if ($all -match '[\r\n]__K230_DOWNLOAD_END__[\r\n]') { break }
        }
        Start-Sleep -Milliseconds 50
    }
    $match = [regex]::Match($all, '[\r\n]__K230_DOWNLOAD_BEGIN__[\r\n]+(.*?)[\r\n]__K230_DOWNLOAD_END__', [Text.RegularExpressions.RegexOptions]::Singleline)
    if (-not $match.Success) { throw "Download markers not found; output: $all" }
    $clean = [regex]::Replace($match.Groups[1].Value, '[^A-Za-z0-9+/=]', '')
    $bytes = [Convert]::FromBase64String($clean)
    $hash = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    if ($ExpectedSHA256 -and $hash -ne $ExpectedSHA256.ToLowerInvariant()) {
        throw "SHA-256 mismatch: expected=$ExpectedSHA256 actual=$hash"
    }
    [IO.File]::WriteAllBytes($FilePath, $bytes)
    Write-Output "DOWNLOAD_VERIFIED path=$RemotePath bytes=$($bytes.Length) sha256=$hash"
} finally {
    if ($p.IsOpen) { $p.Close() }
}
