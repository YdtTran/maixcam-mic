// Diagnostic receiver only; no changes to the operator WHEP/WHIP interfaces.
import { chromium } from '@playwright/test';

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  // Same-origin HTTP avoids depending on cross-origin WHEP CORS policies.
  await page.goto(new URL(process.env.WHEP_URL).origin);
  const result = await page.evaluate(async ({ url, mode, seconds }) => {
    const peer = new RTCPeerConnection({ bundlePolicy: 'max-bundle' });
    const video = document.createElement('video');
    video.muted = true;
    video.autoplay = true;
    const stream = new MediaStream();
    video.srcObject = stream;
    document.body.append(video);
    peer.ontrack = event => { stream.addTrack(event.track); void video.play(); };
    if (mode !== 'audio') peer.addTransceiver('video', { direction: 'recvonly' });
    if (mode !== 'video') peer.addTransceiver('audio', { direction: 'recvonly' });
    const started = performance.now();
    let session;
    const samples = [];
    const bufferSamples = {};
    const previous = {};
    try {
      await peer.setLocalDescription(await peer.createOffer());
      const deadline = performance.now() + 5000;
      while (peer.iceGatheringState !== 'complete' && performance.now() < deadline)
        await new Promise(resolve => setTimeout(resolve, 50));
      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/sdp' },
        body: peer.localDescription.sdp, signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error(`WHEP ${response.status}`);
      session = new URL(response.headers.get('Location'), url).href;
      await peer.setRemoteDescription({ type: 'answer', sdp: await response.text() });
      for (let i = 0; i < seconds; i++) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        const stats = await peer.getStats();
        const inbound = [...stats.values()].filter(s => s.type === 'inbound-rtp').map(s => ({
          kind: s.kind, packetsReceived: s.packetsReceived, packetsLost: s.packetsLost,
          jitterSeconds: s.jitter, jitterBufferDelaySeconds: s.jitterBufferDelay,
          jitterBufferEmittedCount: s.jitterBufferEmittedCount, framesDecoded: s.framesDecoded,
          framesDropped: s.framesDropped, freezeCount: s.freezeCount,
          totalFreezesDurationSeconds: s.totalFreezesDuration, concealedSamples: s.concealedSamples,
          totalSamplesReceived: s.totalSamplesReceived, totalDecodeTimeSeconds: s.totalDecodeTime,
        }));
        for (const report of inbound) {
          const prior = previous[report.kind];
          const count = report.jitterBufferEmittedCount - (prior?.jitterBufferEmittedCount || 0);
          const delay = report.jitterBufferDelaySeconds - (prior?.jitterBufferDelaySeconds || 0);
          if (count > 0) (bufferSamples[report.kind] ||= []).push(delay * 1000 / count);
          previous[report.kind] = report;
        }
        samples.push({ elapsedMs: performance.now() - started, state: peer.connectionState,
          videoCurrentTime: video.currentTime, inbound });
      }
      const last = samples.at(-1)?.inbound || [];
      const playing = samples.filter(s => s.videoCurrentTime > 0);
      const first = playing[0];
      const final = playing.at(-1);
      const playheadDrift = first && final && final.elapsedMs > first.elapsedMs
        ? ((final.elapsedMs - first.elapsedMs) - (final.videoCurrentTime - first.videoCurrentTime) * 1000)
          / ((final.elapsedMs - first.elapsedMs) / 1000) : null;
      const distribution = values => {
        values.sort((a, b) => a - b);
        const middle = Math.floor(values.length / 2);
        return { samples: values.length,
          median: values.length ? (values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2) : null,
          p95: values.length ? values[Math.ceil(values.length * .95) - 1] : null };
      };
      return { samples, final: last.map(s => ({ ...s,
        averageJitterBufferMs: s.jitterBufferEmittedCount ? s.jitterBufferDelaySeconds * 1000 / s.jitterBufferEmittedCount : null,
      })), intervalAverageJitterBufferMs: Object.fromEntries(
        Object.entries(bufferSamples).map(([kind, values]) => [kind, distribution(values)])),
        playheadRelativeDriftMsPerSecond: playheadDrift,
        endToEndLatencyMs: null, physicalAvSyncMs: null };
    } finally {
      peer.close();
      if (session) await fetch(session, { method: 'DELETE' }).catch(() => {});
    }
  }, { url: process.env.WHEP_URL, mode: process.env.STREAM_MODE || 'combined',
    seconds: Number(process.env.MEASURE_SECONDS || 30) });
  const mode = process.env.STREAM_MODE || 'combined';
  const video = result.final.find(s => s.kind === 'video');
  const audio = result.final.find(s => s.kind === 'audio');
  if (!result.final.length || result.final.some(s => !s.packetsReceived)
    || (mode !== 'audio' && !video?.framesDecoded)
    || (mode !== 'video' && !audio?.totalSamplesReceived))
    throw new Error('No received WebRTC media; signaling alone is insufficient');
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
}
