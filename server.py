#!/usr/bin/env python3
import asyncio, os, time
from fractions import Fraction
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.rtcconfiguration import RTCConfiguration, RTCIceServer
from av import VideoFrame, AudioFrame

from picamera2 import Picamera2
import sounddevice as sd
import numpy as np

# ========================
# Config (env overrides)
# ========================

VIDEO_WIDTH  = int(os.environ.get("PI_W", "640"))
VIDEO_HEIGHT = int(os.environ.get("PI_H", "480"))
VIDEO_FPS    = int(os.environ.get("PI_FPS", "20"))
AWB_MODE     = os.environ.get("PI_AWB", "").strip()

ENV_AUDIO_DEVICE = os.environ.get("PI_AUDIO_DEV")
ENV_AUDIO_SR     = os.environ.get("PI_AUDIO_SR")
AUDIO_BLOCK      = int(os.environ.get("PI_AUDIO_BLKSZ", "960"))  # ~20ms @ 48k

GAIN_DB = float(os.environ.get("PI_AUDIO_GAIN_DB", "0"))
GAIN    = 10 ** (GAIN_DB / 20.0) if GAIN_DB != 0 else 1.0

ICE_SERVERS = [
    RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
    # add TURN here later if needed
]

# ========================
# Helpers (audio)
# ========================

def pick_input_device():
    devs = sd.query_devices()
    prefer = ("voice", "google", "sndrpigoogle", "mic", "hifi")
    best = None
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0:
            name = (d.get("name") or "").lower()
            if any(k in name for k in prefer):
                return i
            if best is None:
                best = i
    return best

def pick_samplerate(device_index):
    candidates = []
    if ENV_AUDIO_SR:
        try: candidates.append(int(ENV_AUDIO_SR))
        except: pass
    try:
        d = sd.query_devices(device_index)
        default_sr = int(round(d.get("default_samplerate", 0)))
        if default_sr: candidates.append(default_sr)
    except Exception:
        pass
    for sr in (48000, 44100, 32000, 16000, 8000):
        if sr not in candidates: candidates.append(sr)
    for sr in candidates:
        try:
            sd.check_input_settings(device=device_index, samplerate=sr, channels=1)
            return sr
        except Exception:
            continue
    raise RuntimeError("No supported sample rate for selected input device.")

# ========================
# Media tracks
# ========================

class PiCameraTrack(MediaStreamTrack):
    kind = "video"
    def __init__(self, width=640, height=480, fps=20):
        super().__init__()
        self.picam = Picamera2()
        # Use BGR888 -> bgr24 to avoid blue tint
        cfg = self.picam.create_preview_configuration(main={"size": (width, height), "format": "BGR888"})
        self.picam.configure(cfg)
        self.picam.start()
        time.sleep(0.2)
        if AWB_MODE:
            try:
                self.picam.set_controls({"AwbEnable": True, "AwbMode": AWB_MODE})
            except Exception:
                pass
        self.fps = int(fps)
        self._tb = Fraction(1, self.fps)
        self._pts = 0
        self._frame_interval = 1.0 / self.fps
        self._last = time.time()

    async def recv(self):
        now = time.time()
        delay = self._frame_interval - (now - self._last)
        if delay > 0: await asyncio.sleep(delay)
        self._last = time.time()
        bgr = self.picam.capture_array()
        frame = VideoFrame.from_ndarray(bgr, format="bgr24")
        frame.pts = self._pts
        frame.time_base = self._tb
        self._pts += 1
        return frame

class MicrophoneAudioTrack(MediaStreamTrack):
    kind = "audio"
    def __init__(self):
        super().__init__()
        if ENV_AUDIO_DEVICE is not None:
            device_index = int(ENV_AUDIO_DEVICE)
        else:
            device_index = pick_input_device()
        if device_index is None:
            raise RuntimeError("No input audio device found.")
        samplerate = pick_samplerate(device_index)
        self.device_index = device_index
        self.samplerate   = samplerate
        self.channels     = 1
        self.blocksize    = AUDIO_BLOCK if AUDIO_BLOCK > 0 else 960
        print(f"[Audio] Using device idx {self.device_index} @ {self.samplerate} Hz, block {self.blocksize}, gain {GAIN_DB:+.1f} dB")
        self.stream = sd.InputStream(device=self.device_index, samplerate=self.samplerate,
                                     channels=self.channels, dtype="int16", blocksize=self.blocksize)
        self.stream.start()
        self._tb  = Fraction(1, self.samplerate)
        self._pts = 0

    async def recv(self):
        data, _ = self.stream.read(self.blocksize)
        if data.ndim == 1: data = data.reshape(-1, 1)
        if GAIN != 1.0:
            x = (data.astype(np.float32) * GAIN).clip(-32768, 32767)
            data = x.astype(np.int16)
        samples = data.shape[0]
        frame = AudioFrame(format="s16", layout="mono", samples=samples)
        frame.sample_rate = self.samplerate
        frame.planes[0].update(data.tobytes())
        frame.pts = self._pts
        frame.time_base = self._tb
        self._pts += samples
        return frame

# ========================
# Web app & signaling
# ========================

ROOT = os.path.dirname(os.path.realpath(__file__))
pcs = set()

async def index(request): return web.FileResponse(path=os.path.join(ROOT, "index.html"))

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=ICE_SERVERS))
    pcs.add(pc)

    w   = int(request.query.get("w",   str(VIDEO_WIDTH)))
    h   = int(request.query.get("h",   str(VIDEO_HEIGHT)))
    fps = int(request.query.get("fps", str(VIDEO_FPS)))
    pc.addTrack(PiCameraTrack(width=w, height=h, fps=fps))
    pc.addTrack(MicrophoneAudioTrack())

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

async def on_shutdown(app):
    await asyncio.gather(*(pc.close() for pc in pcs))

def main():
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    web.run_app(app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()
