$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Security

$secure = Read-Host "MiniMax TTS API key（输入不会显示）" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$plainBytes = $null
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $plainBytes = [Text.Encoding]::UTF8.GetBytes($plain)
    $entropy = [Text.Encoding]::UTF8.GetBytes("risc-v-demo-minimax-tts-v1")
    $protected = [Security.Cryptography.ProtectedData]::Protect(
        $plainBytes,
        $entropy,
        [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    $directory = Join-Path $env:USERPROFILE ".config\risc-v"
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $path = Join-Path $directory "minimax-tts-key.dpapi"
    [IO.File]::WriteAllBytes($path, $protected)
    Write-Output "ENCRYPTED_KEY_SAVED $path"
    Write-Output "Only the current Windows user can decrypt this file. No plaintext key was written."
} finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if ($plainBytes -ne $null) {
        [Array]::Clear($plainBytes, 0, $plainBytes.Length)
    }
    $plain = $null
    $secure = $null
}
