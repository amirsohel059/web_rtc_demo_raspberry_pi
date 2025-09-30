# Pi Edge Demo: YOLOv8 + WebRTC (Raspberry Pi 4, Bookworm 64‑bit, headless)

This repo gives you two things:

1) **YOLOv8 object detection** on the Raspberry Pi Camera (Picamera2) — headless.
2) **WebRTC live streaming (video + audio)** from the Pi to any browser (LAN or Internet via Cloudflare Tunnel).

> Tested on Raspberry Pi OS **Bookworm 64‑bit Lite**, CSI camera (libcamera/Picamera2), Python 3.11.

---

## 0) Clone & layout

```bash
git clone <your-repo-url> pi-edge-demo
cd pi-edge-demo
# put your trained YOLOv8 model here:
mkdir -p models
# scp your file from Windows (example)
# scp C:/path/to/best.pt pi@<PI_IP>:/home/pi/pi-edge-demo/models/best.pt
ls -lh models/best.pt
```

Repo layout:

```
pi-edge-demo/
├─ README.md
├─ requirements.txt
├─ pi_cam_yolov8.py        # YOLOv8 + Picamera2 console demo (no GUI)
├─ server.py               # WebRTC server (video + audio)
├─ index.html              # Web page viewer
└─ models/
   └─ best.pt             # (you add this)
```

---

## 1) System packages (no venv)

```bash
sudo apt update
sudo apt install -y   python3 python3-pip git   rpicam-apps v4l-utils python3-picamera2 python3-simplejpeg   libatlas-base-dev libopenblas-dev libjpeg-dev libpng-dev   libavcodec-dev libavformat-dev libswscale-dev   portaudio19-dev
```

> If pip refuses system installs on Bookworm, allow them:
```bash
sudo mv /usr/lib/python3.11/EXTERNALLY-MANAGED /usr/lib/python3.11/EXTERNALLY-MANAGED.old || true
```

---

## 2) Python packages (system‑wide)

```bash
python3 -m pip install -U pip wheel setuptools
# Headless OpenCV (no GUI)
python3 -m pip uninstall -y opencv-python opencv-contrib-python || true
python3 -m pip install -r requirements.txt
# Torch (CPU) from official index
python3 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

Sanity check:
```bash
python3 - << 'PY'
import sys, torch, cv2, ultralytics
print("Python:", sys.version.split()[0])
print("Torch:", torch.__version__, "CUDA?", torch.cuda.is_available())
print("OpenCV:", cv2.__version__)
print("Ultralytics:", ultralytics.__version__)
PY
```

---

## 3) YOLOv8 quick tests

### Image test (no camera)
```bash
mkdir -p data && cd data
wget -O bus.jpg https://ultralytics.com/images/bus.jpg
cd ..
python3 -m ultralytics detect predict model=models/best.pt source=data/bus.jpg imgsz=320 conf=0.25 show=False save=True
# outputs -> runs/detect/predict*/
```

### Live camera (Picamera2, console log only)
```bash
python3 pi_cam_yolov8.py
```
- Adjust speed/quality: set env `PI_YOLO_IMGSZ=256` or `320` before running.
- Small models (e.g., yolov8n/s) give better FPS on Pi.

---

## 4) WebRTC (video + audio) — LAN

Run the WebRTC server:
```bash
python3 server.py
# serves on http://0.0.0.0:8080
```

From your Windows PC on the **same LAN**, open:
```
http://<PI_IP>:8080/
```
Click **Start**. You should see video and hear audio.

### Tuning
- **Blue-ish video**: fixed by using BGR24 frames; optional AWB via env:
  ```bash
  PI_AWB=Daylight python3 server.py
  PI_AWB=Tungsten python3 server.py
  ```
- **Low mic level**: use `alsamixer` (F4 → Capture) to raise input; or add software gain:
  ```bash
  PI_AUDIO_GAIN_DB=10 python3 server.py   # +10 dB
  ```
- Force mic device / sample rate:
  ```bash
  PI_AUDIO_DEV=1 PI_AUDIO_SR=48000 python3 server.py
  ```

---

## 5) WebRTC over Internet (no port‑forward): Cloudflare Tunnel

Quick Tunnel (no domain needed):
```bash
# leave server.py running in one terminal
# in another terminal:
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cloudflared.deb
sudo apt install -y ./cloudflared.deb

cloudflared tunnel --url http://localhost:8080
# copy the https://*.trycloudflare.com URL and share it
```

---

## 6) Env knobs & examples

```bash
# VIDEO
PI_W=640 PI_H=480 PI_FPS=20       # default video settings
PI_AWB=Auto|Daylight|Tungsten     # optional AWB

# AUDIO
PI_AUDIO_DEV=<idx>                # force input device index
PI_AUDIO_SR=48000                 # force sample rate
PI_AUDIO_BLKSZ=960                # ALSA block size (20ms @ 48k)
PI_AUDIO_GAIN_DB=10               # software gain in dB
```

---

## 7) Troubleshooting

- **Audio error: Invalid sample rate** → the code auto‑probes rates; or set `PI_AUDIO_SR=48000`.
- **Very low audio** → raise with `alsamixer` (F4 → Capture), or set `PI_AUDIO_GAIN_DB=6..12`.
- **Black video on WebRTC** → ensure server.py running; check browser console; try lower resolution/FPS.
- **No connection over Internet** → Quick Tunnel uses STUN only; some networks require TURN (not included in this demo).

---

## 8) Credits / Notes
- Picamera2 formats & AWB controls: Picamera2 manual and community guidance.
- aiortc: Python WebRTC stack used for signaling & media transport.
- Cloudflare Tunnel: quick public HTTPS URL via `cloudflared`.
