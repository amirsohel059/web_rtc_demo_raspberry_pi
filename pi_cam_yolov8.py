from picamera2 import Picamera2
from ultralytics import YOLO
import time, os

MODEL = os.environ.get("PI_YOLO_MODEL", os.path.expanduser("~/pi-edge-demo/models/best.pt"))
IMG   = int(os.environ.get("PI_YOLO_IMGSZ", "320"))
CONF  = float(os.environ.get("PI_YOLO_CONF", "0.30"))

def main():
    print(f"Loading model: {MODEL}")
    model = YOLO(MODEL)

    print("Starting Picamera2…")
    picam = Picamera2()
    config = picam.create_preview_configuration(main={"size": (640, 480), "format": "RGB888"})
    picam.configure(config)
    picam.start()
    time.sleep(0.2)

    print("Running... Ctrl+C to stop.")
    t0, n = time.time(), 0
    try:
        while True:
            frame = picam.capture_array()  # HxWx3 RGB
            results = model.predict(frame, imgsz=IMG, conf=CONF, verbose=False)
            r = results[0]
            for b in r.boxes:
                name = model.names[int(b.cls[0])]
                conf = float(b.conf[0])
                xyxy = [round(x,1) for x in b.xyxy[0].tolist()]
                print(f"{name:>12} {conf:4.2f}  {xyxy}")
            n += 1
            if time.time() - t0 >= 1:
                print(f"FPS ~ {n/(time.time()-t0):.1f}")
                t0, n = time.time(), 0
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        picam.stop()

if __name__ == "__main__":
    main()
