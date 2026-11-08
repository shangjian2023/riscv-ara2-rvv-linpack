param(
    [Parameter(Mandatory=$true)][string]$Storyboard,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$items = Get-Content -LiteralPath $Storyboard -Raw -Encoding UTF8 | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
foreach ($item in $items) {
    $speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
    try {
        $speaker.SelectVoice("Microsoft Huihui Desktop")
        $speaker.Rate = 1
        $speaker.Volume = 100
        $path = Join-Path $OutputDirectory ($item.id + ".wav")
        $speaker.SetOutputToWaveFile($path)
        $speaker.Speak($item.narration)
        Write-Output "NARRATED $($item.id)"
    } finally {
        $speaker.Dispose()
    }
}
