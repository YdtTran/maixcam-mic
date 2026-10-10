# MaixCAM H.264 video + headset microphone -> MediaMTX H.264/Opus. Run after mediamtx.exe.
# The camera emits empty H.264 NAL units; remove them before RTSP publish.
param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
  [string]$MaixIp,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
  [string]$LaptopIp,
  [ValidateSet('udp', 'tcp')]
  [string]$Transport = 'udp'
)

if ($Transport -eq 'tcp') {
  python -m pc.check_camera_udp --maix-ip $MaixIp --transport tcp
  if ($LASTEXITCODE -ne 0) { throw 'Camera TCP media unverified; use UDP.' }
}

ffmpeg `
  -rtsp_transport $Transport `
  -timeout 5000000 `
  -max_delay 100000 `
  -buffer_size 4194304 `
  -reorder_queue_size 512 `
  -analyzeduration 1000000 `
  -probesize 1000000 `
  -i "rtsp://${MaixIp}:8554/live" `
  -rtsp_transport $Transport `
  -timeout 5000000 `
  -max_delay 100000 `
  -buffer_size 4194304 `
  -reorder_queue_size 128 `
  -i "rtsp://${LaptopIp}:8554/headsetmic" `
  -map 0:v:0 `
  -map 1:a:0 `
  '-c:v' copy `
  '-bsf:v' "filter_units=remove_types=0,dump_extra=freq=keyframe" `
  '-c:a' libopus `
  -application lowdelay `
  -frame_duration 20 `
  -ar 48000 `
  -ac 1 `
  '-b:a' 64k `
  -f rtsp `
  -rtsp_transport $Transport `
  -buffer_size 4194304 `
  -pkt_size 1200 `
  "rtsp://${LaptopIp}:8554/maix01"
