# MaixCAM H.264 video + Air6 HS microphone -> MediaMTX H.264/Opus. Run after mediamtx.exe.
# The camera emits empty H.264 NAL units; remove them before RTSP publish.
param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
  [string]$MaixIp,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
  [string]$LaptopIp
)

ffmpeg `
  -rtsp_transport tcp `
  -analyzeduration 10000000 `
  -probesize 20000000 `
  -i "rtsp://${MaixIp}:8554/live" `
  -rtsp_transport tcp `
  -i "rtsp://${LaptopIp}:8554/air6mic" `
  -map 0:v:0 `
  -map 1:a:0 `
  '-c:v' copy `
  '-bsf:v' "filter_units=remove_types=0,dump_extra=freq=keyframe" `
  '-c:a' libopus `
  -ar 48000 `
  -ac 1 `
  '-b:a' 64k `
  -f rtsp `
  -rtsp_transport tcp `
  "rtsp://${LaptopIp}:8554/maix01"
