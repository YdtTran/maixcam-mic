// WHEP playback and WHIP talkback use UDP ICE media; HTTP carries SDP only.
export async function selectedIceTransport(peer: RTCPeerConnection): Promise<string> {
  const stats = await peer.getStats();
  let pair: { localCandidateId: string } | undefined;
  stats.forEach((report) => {
    if (report.type === "transport" && report.selectedCandidatePairId)
      pair = stats.get(report.selectedCandidatePairId);
  });
  if (!pair) stats.forEach((report) => {
    if (report.type === "candidate-pair" && report.state === "succeeded" && report.nominated) pair = report;
  });
  if (!pair) throw new Error("ICE transport could not be verified");
  const candidate = stats.get(pair.localCandidateId);
  if (candidate?.protocol !== "udp") throw new Error("UDP media is required");
  return "udp";
}

async function gatherIce(peer: RTCPeerConnection) {
  if (peer.iceGatheringState === "complete") return;
  await new Promise<void>((resolve, reject) => {
    const change = () => { if (peer.iceGatheringState === "complete") finish(); };
    const finish = (error?: Error) => {
      clearTimeout(timer);
      peer.removeEventListener("icegatheringstatechange", change);
      error ? reject(error) : resolve();
    };
    const timer = setTimeout(() => finish(new Error("ICE gathering timed out")), 5000);
    peer.addEventListener("icegatheringstatechange", change);
  });
}
export class LiveStream {
  private peer: RTCPeerConnection | null = null;
  private session: string | null = null;
  private abort = new AbortController();
  private retry: ReturnType<typeof setTimeout> | null = null;
  private active = false;
  constructor(
    private video: HTMLVideoElement,
    private status: (state: string) => void,
  ) {}
  async start(url: string) {
    this.active = true;
    this.abort = new AbortController();
    const peer = new RTCPeerConnection({ bundlePolicy: "max-bundle" });
    this.peer = peer;
    const stream = new MediaStream();
    this.video.srcObject = stream;
    this.status("Connecting");
    peer.addTransceiver("video", { direction: "recvonly" });
    peer.addTransceiver("audio", { direction: "recvonly" });
    peer.ontrack = (event) => {
      if (this.peer !== peer) return;
      stream.addTrack(event.track);
      void this.video
        .play()
        .catch(() => this.status("Click Enable audio to play"));
    };
    peer.onconnectionstatechange = () => {
      if (this.peer !== peer) return;
      if (peer.connectionState === "connected") {
        void selectedIceTransport(peer).then(() => {
          if (this.peer === peer) { this.video.dataset.mediaTransport = "udp"; this.status("Online"); }
        }).catch((error) => { this.status(error.message); this.reconnect(url); });
      } else if (["failed", "disconnected"].includes(peer.connectionState)) {
        this.status("Offline"); this.reconnect(url);
      } else this.status("Connecting");
    };
    try {
      await peer.setLocalDescription(await peer.createOffer());
      if (peer.iceGatheringState !== "complete")
        await new Promise<void>((resolve) => {
          const finish = () => {
            clearTimeout(timer);
            peer.removeEventListener("icegatheringstatechange", change);
            resolve();
          };
          const change = () => {
            if (peer.iceGatheringState === "complete") finish();
          };
          const timer = setTimeout(finish, 5000);
          peer.addEventListener("icegatheringstatechange", change);
          this.abort.signal.addEventListener("abort", finish, { once: true });
        });
      if (this.peer !== peer) return;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: peer.localDescription!.sdp,
        signal: AbortSignal.any([
          this.abort.signal,
          AbortSignal.timeout(15000),
        ]),
      });
      if (!response.ok)
        throw new Error(`Camera stream unavailable (${response.status}).`);
      const locationHeader = response.headers.get("Location");
      if (locationHeader) this.session = new URL(locationHeader, url).href;
      const sdp = await response.text();
      if (this.peer !== peer) return;
      await peer.setRemoteDescription({ type: "answer", sdp });
    } catch (error) {
      if (this.abort.signal.aborted) return;
      this.status(
        error instanceof Error ? error.message : "Camera stream unavailable",
      );
      this.reconnect(url);
    }
  }
  private reconnect(url: string) {
    if (!this.active || this.retry) return;
    this.release();
    this.retry = setTimeout(() => {
      this.retry = null;
      if (this.active) void this.start(url);
    }, 2000);
  }
  stop() {
    this.active = false;
    if (this.retry) clearTimeout(this.retry);
    this.retry = null;
    this.release();
  }
  private release() {
    this.abort.abort();
    this.peer?.close();
    this.peer = null;
    const stream = this.video.srcObject as MediaStream | null;
    stream?.getTracks().forEach((track) => track.stop());
    this.video.srcObject = null;
    delete this.video.dataset.mediaTransport;
    if (this.session)
      void fetch(this.session, { method: "DELETE", keepalive: true }).catch(
        () => {},
      );
    this.session = null;
  }
}

export class Talkback {
  private stream: MediaStream | null = null;
  private peer: RTCPeerConnection | null = null;
  private session: string | null = null;
  private wanted = false;
  private pending: Promise<boolean> | null = null;
  constructor(private error: (message: string) => void) {}
  start() {
    this.wanted = true;
    this.pending = this.connect();
    return this.pending;
  }
  private async connect() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 }, video: false,
      });
      this.stream = stream;
      if (!this.wanted) { stream.getTracks().forEach((track) => track.stop()); return false; }
      const peer = new RTCPeerConnection({ bundlePolicy: "max-bundle" });
      this.peer = peer;
      stream.getAudioTracks().forEach((track) => peer.addTrack(track, stream));
      peer.onconnectionstatechange = () => {
        if (!this.wanted) return;
        if (peer.connectionState === "connected") {
          void selectedIceTransport(peer).catch((error) => { this.error(error.message); void this.stop(); });
        } else if (["failed", "disconnected"].includes(peer.connectionState)) {
          this.error("Talkback connection interrupted; release and retry."); void this.stop();
        }
      };
      await peer.setLocalDescription(await peer.createOffer());
      await gatherIce(peer);
      if (!this.wanted) return false;
      const response = await fetch("/api/talkback/offer", {
        method: "POST", headers: { "Content-Type": "application/sdp" },
        body: peer.localDescription!.sdp, signal: AbortSignal.timeout(15000),
      });
      const answer = await response.json();
      if (!response.ok) throw new Error(answer.error || `Talkback unavailable (${response.status}).`);
      this.session = answer.session;
      if (!this.wanted) return false;
      await peer.setRemoteDescription({ type: "answer", sdp: answer.sdp });
      return true;
    } catch (error) {
      if (this.wanted) this.error(error instanceof Error ? error.message : "Talkback unavailable");
      // Defer cleanup until connect settles, avoiding a self-await.
      queueMicrotask(() => { void this.stop(); });
      return false;
    }
  }
  async stop() {
    this.wanted = false;
    this.peer?.close();
    this.stream?.getTracks().forEach((track) => track.stop());
    await this.pending;
    this.peer?.close();
    this.peer = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    const session = this.session;
    this.session = null;
    if (session) {
      try {
        const response = await fetch("/api/talkback/stop", {
          method: "POST", headers: { "X-Talkback-Session": session }, keepalive: true,
          signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) this.error(`Could not confirm talkback stopped (${response.status}).`);
      } catch { this.error("Could not confirm talkback stopped."); }
    }
  }
}
