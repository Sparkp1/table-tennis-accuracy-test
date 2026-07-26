import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog
import os
import csv

state = {
    "mode": "calibration",
    "playing": False,
    "frame": None,
    "frame_number": 0,
    "frame_count": 0,
    "shot": 1,
    "corner_points": [],
    "target_pixel": None,
    "target_cm": None,
    "homography": None,
    "annotations": [],
    "cap": None,
    "csv_path": None,
    "video_path": None,
    "fps": 30.0,
}

TABLE_WIDTH_CM = 152.5
TABLE_HALF_LENGTH_CM = 137.0

REAL_WORLD_CORNERS = np.array([
    [0,               0],
    [TABLE_WIDTH_CM,  0],
    [TABLE_WIDTH_CM,  TABLE_HALF_LENGTH_CM],
    [0,               TABLE_HALF_LENGTH_CM],
], dtype=np.float32)

CALIBRATION_PROMPTS = [
    "Click Top Left Corner",
    "Click Top Right Corner",
    "Click Bottom Right Corner",
    "Click Bottom Left Corner",
    "Click Target Point",
]


def pick_video():
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Select video file",
        filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv")]
    )
    root.destroy()
    return path


def pixel_to_cm(px, py, homography):
    pt = np.array([[[px, py]]], dtype=np.float32)
    result = cv2.perspectiveTransform(pt, homography)
    x = float(result[0][0][0])
    y = float(result[0][0][1])
    y = TABLE_HALF_LENGTH_CM - y  # flip y: image y=0 is top, real world y=0 is bottom
    return x, y


def goto_frame(n):
    state["cap"].set(cv2.CAP_PROP_POS_FRAMES, n)
    ret, frame = state["cap"].read()
    if ret:
        state["frame"] = frame
        state["frame_number"] = n


def update_frame():
    ret, frame = state["cap"].read()
    if ret:
        state["frame"] = frame
        state["frame_number"] = int(state["cap"].get(cv2.CAP_PROP_POS_FRAMES)) - 1
        return True
    return False


def draw_status(frame):
    display = frame.copy()

    if state["mode"] == "calibration":
        idx = len(state["corner_points"])
        if idx < len(CALIBRATION_PROMPTS):
            prompt = CALIBRATION_PROMPTS[idx]
        else:
            prompt = "Calibration Complete - Press SPACE"

        cv2.rectangle(display, (0, 0), (display.shape[1], 60), (0, 0, 0), -1)
        cv2.putText(display, "Calibration", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)
        cv2.putText(display, prompt, (10, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 1)

        for pt in state["corner_points"]:
            cv2.circle(display, pt, 5, (0, 255, 0), -1)

        if state["target_pixel"] is not None:
            cv2.drawMarker(display, state["target_pixel"], (0, 0, 255),
                           cv2.MARKER_CROSS, 20, 2)

    elif state["mode"] == "annotation":
        total = state["frame_count"]
        fn = state["frame_number"]
        shot = state["shot"]
        playing = "Playing" if state["playing"] else "Paused"

        lines = [
            f"Mode: Annotation          {playing}",
            f"Shot: {shot}    Frame: {fn} / {total}",
            "SPACE: Play/Pause    A/D: Prev/Next Frame",
            "Left Click: Record Bounce    R: Undo    Q: Quit",
        ]

        cv2.rectangle(display, (0, 0), (display.shape[1], 80), (0, 0, 0), -1)
        for i, line in enumerate(lines):
            cv2.putText(display, line, (10, 18 + i * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)

    return display


def write_csv():
    try:
        with open(state["csv_path"], "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Shot", "Frame", "TargetX_cm", "TargetY_cm",
                             "LandingX_cm", "LandingY_cm"])
            for row in state["annotations"]:
                writer.writerow(row)
        print(f"CSV saved: {state['csv_path']}  ({len(state['annotations'])} rows)")
    except Exception as e:
        print(f"CSV write failed: {e}")


def save_annotation(px, py):
    lx, ly = pixel_to_cm(px, py, state["homography"])
    tx, ty = state["target_cm"]
    row = [state["shot"], state["frame_number"], tx, ty, lx, ly]
    state["annotations"].append(row)
    write_csv()
    state["shot"] += 1


def undo_annotation():
    if state["annotations"]:
        state["annotations"].pop()
        state["shot"] -= 1
        write_csv()


def mouse_callback(event, x, y, flags, param):
    if event != cv2.EVENT_LBUTTONDOWN:
        return

    if state["mode"] == "calibration":
        idx = len(state["corner_points"])
        if idx < 4:
            state["corner_points"].append((x, y))
            if len(state["corner_points"]) == 4:
                src = np.array(state["corner_points"], dtype=np.float32)
                state["homography"], _ = cv2.findHomography(src, REAL_WORLD_CORNERS)
        elif state["homography"] is not None and state["target_pixel"] is None:
            state["target_pixel"] = (x, y)
            tx, ty = pixel_to_cm(x, y, state["homography"])
            state["target_cm"] = (tx, ty)

    elif state["mode"] == "annotation":
        save_annotation(x, y)
        state["playing"] = False


def calibration_loop():
    cv2.namedWindow("Annotator", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Annotator", mouse_callback)

    while True:
        display = draw_status(state["frame"])
        cv2.imshow("Annotator", display)
        key = cv2.waitKey(30) & 0xFF

        n_pts = len(state["corner_points"])
        calibration_done = (n_pts >= 4 and state["target_pixel"] is not None)

        if calibration_done and key == ord(" "):
            break

        if key == ord("q"):
            cv2.destroyAllWindows()
            exit()


def annotation_loop():
    state["mode"] = "annotation"
    goto_frame(0)
    state["playing"] = False
    frame_duration = 1.0 / state["fps"]  # seconds per frame

    while True:
        loop_start = cv2.getTickCount()

        if state["playing"]:
            if not update_frame():
                state["playing"] = False

        display = draw_status(state["frame"])
        cv2.imshow("Annotator", display)

        if state["playing"]:
            # subtract time already spent this loop from the frame duration
            elapsed = (cv2.getTickCount() - loop_start) / cv2.getTickFrequency()
            wait_ms = max(1, int((frame_duration - elapsed) * 1000))
        else:
            wait_ms = 5

        raw = cv2.waitKey(wait_ms)
        key = raw & 0xFF

        if key == ord("q"):
            break

        elif key == ord(" "):
            state["playing"] = not state["playing"]

        elif key == ord("r"):
            undo_annotation()

        elif key == ord("a"):
            state["playing"] = False
            nf = max(0, state["frame_number"] - 1)
            goto_frame(nf)

        elif key == ord("d"):
            state["playing"] = False
            nf = min(state["frame_count"] - 1, state["frame_number"] + 1)
            goto_frame(nf)

        elif raw != -1:
            print(f"key={key}  raw={raw}")

    cv2.destroyAllWindows()


def main():
    video_path = pick_video()
    if not video_path:
        print("No video selected.")
        return

    state["video_path"] = video_path
    base = os.path.splitext(video_path)[0]
    state["csv_path"] = base + "_annotations.csv"
    print(f"CSV will be saved to: {state['csv_path']}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Failed to open video.")
        return

    state["cap"] = cap
    state["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    state["fps"] = cap.get(cv2.CAP_PROP_FPS) or 30.0

    ret, frame = cap.read()
    if not ret:
        print("Failed to read first frame.")
        return
    state["frame"] = frame
    state["frame_number"] = 0

    calibration_loop()
    annotation_loop()

    cap.release()


if __name__ == "__main__":
    main()
