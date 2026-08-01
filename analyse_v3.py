import csv
import math
import os
import tkinter as tk
from tkinter import filedialog

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

TARGET_RADIUS_CM = 25.0
TABLE_WIDTH_CM   = 152.5
TABLE_HALF_CM    = 137.0


# ── File picker ──────────────────────────────────────────────────────────────

def pick_csv():
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Select annotations CSV",
        filetypes=[("CSV files", "*.csv")]
    )
    root.destroy()
    return path


# ── Load data ─────────────────────────────────────────────────────────────────

def load_csv(path):
    shots = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            shots.append({
                "shot":      int(row["Shot"]),
                "frame":     int(row["Frame"]),
                "target_x":  float(row["TargetX_cm"]),
                "target_y":  float(row["TargetY_cm"]),
                "landing_x": float(row["LandingX_cm"]),
                "landing_y": float(row["LandingY_cm"]),
            })
    return shots


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(shots):
    tx = shots[0]["target_x"]
    ty = shots[0]["target_y"]

    lx = np.array([s["landing_x"] for s in shots])
    ly = np.array([s["landing_y"] for s in shots])

    errors = np.sqrt((lx - tx)**2 + (ly - ty)**2)

    mean_x   = float(np.mean(lx))
    mean_y   = float(np.mean(ly))
    sigma_x  = float(np.std(lx))
    sigma_y  = float(np.std(ly))
    mean_err = float(np.mean(errors))

    # CEP50 — radius containing 50% of shots
    sorted_err = np.sort(errors)
    cep50 = float(sorted_err[int(math.ceil(len(sorted_err) * 0.50)) - 1])

    # shots within target radius
    within = int(np.sum(errors <= TARGET_RADIUS_CM))

    return {
        "tx": tx, "ty": ty,
        "lx": lx, "ly": ly,
        "errors": errors,
        "mean_x": mean_x, "mean_y": mean_y,
        "sigma_x": sigma_x, "sigma_y": sigma_y,
        "mean_err": mean_err,
        "cep50": cep50,
        "within": within,
        "n": len(shots),
    }


# ── Scatter plot ──────────────────────────────────────────────────────────────

def plot_scatter(m, title, out_path):
    fig, ax = plt.subplots(figsize=(8, 6))

    # Table half outline
    table_rect = patches.Rectangle(
        (0, 0), TABLE_WIDTH_CM, TABLE_HALF_CM,
        linewidth=1.5, edgecolor="#333333", facecolor="#2a7dbf", alpha=0.15, zorder=0
    )
    ax.add_patch(table_rect)

    # Target circle
    circle = plt.Circle(
        (m["tx"], m["ty"]), TARGET_RADIUS_CM,
        color="red", alpha=0.12, zorder=1
    )
    ax.add_patch(circle)
    circle_edge = plt.Circle(
        (m["tx"], m["ty"]), TARGET_RADIUS_CM,
        color="red", fill=False, linewidth=1.2, alpha=0.5, zorder=2
    )
    ax.add_patch(circle_edge)

    # Landing positions
    ax.scatter(m["lx"], m["ly"],
               marker="x", color="#1f77b4", s=20, linewidths=0.8,
               label="Landing positions", zorder=5)

    # Target centre
    ax.scatter(m["tx"], m["ty"],
               marker="o", color="red", s=80, zorder=6, label="Target centre")

    # Stats box — top left
    pct = 100.0 * m["within"] / m["n"]
    stats_text = (
        f"Within {TARGET_RADIUS_CM:.0f} cm radius: {m['within']}/{m['n']} ({pct:.1f}%)\n"
        f"Mean error: {m['mean_err']:.1f} cm\n"
        f"CEP50: {m['cep50']:.1f} cm\n"
        f"\u03c3x: {m['sigma_x']:.1f} cm     \u03c3y: {m['sigma_y']:.1f} cm"
    )
    ax.text(0.02, 0.98, stats_text,
            transform=ax.transAxes,
            fontsize=8.5, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.8))

    ax.set_xlim(-5, TABLE_WIDTH_CM + 5)
    ax.set_ylim(-5, TABLE_HALF_CM + 5)
    ax.set_xlabel("x-position (cm)")
    ax.set_ylabel("y-position (cm)")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_aspect("equal")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Scatter plot saved: {out_path}")


# ── Heatmap ───────────────────────────────────────────────────────────────────

def plot_heatmap(m, title, out_path):
    fig, ax = plt.subplots(figsize=(8, 6))

    # KDE-style heatmap using 2D histogram with Gaussian smoothing
    from scipy.ndimage import gaussian_filter

    bins_x = np.linspace(0, TABLE_WIDTH_CM, 60)
    bins_y = np.linspace(0, TABLE_HALF_CM, 60)
    h, xedges, yedges = np.histogram2d(m["lx"], m["ly"], bins=[bins_x, bins_y])
    h = gaussian_filter(h, sigma=2.5)
    h_norm = h / h.max() if h.max() > 0 else h

    ax.imshow(
        h_norm.T,
        origin="lower",
        extent=[0, TABLE_WIDTH_CM, 0, TABLE_HALF_CM],
        cmap="hot",
        aspect="auto",
        vmin=0, vmax=1,
        zorder=1
    )

    # Table outline
    for spine in ax.spines.values():
        spine.set_visible(True)

    # Centre line
    ax.axvline(TABLE_WIDTH_CM / 2, color="white", linewidth=1,
               linestyle="--", alpha=0.5, zorder=2)

    # Target marker
    ax.scatter(m["tx"], m["ty"], marker="x", color="red",
               s=120, linewidths=2.5, zorder=3, label="Target")

    cb = fig.colorbar(
        plt.cm.ScalarMappable(cmap="hot",
                              norm=plt.Normalize(vmin=0, vmax=1)),
        ax=ax, fraction=0.03, pad=0.02
    )
    cb.set_label("Normalised Ball Frequency")

    ax.set_xlim(0, TABLE_WIDTH_CM)
    ax.set_ylim(0, TABLE_HALF_CM)
    ax.set_xlabel("x-position (cm)")
    ax.set_ylabel("y-position (cm)")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Heatmap saved: {out_path}")


# ── Summary stats text file ───────────────────────────────────────────────────

def save_stats(m, out_path):
    pct = 100.0 * m["within"] / m["n"]
    lines = [
        "=" * 44,
        "  Accuracy & Precision Analysis",
        "=" * 44,
        f"  Total shots          : {m['n']}",
        f"  Target (x, y)        : ({m['tx']:.1f}, {m['ty']:.1f}) cm",
        f"  Mean landing (x, y)  : ({m['mean_x']:.1f}, {m['mean_y']:.1f}) cm",
        f"  Offset from target   : ({m['mean_x']-m['tx']:.1f}, {m['mean_y']-m['ty']:.1f}) cm",
        f"  Sigma x              : {m['sigma_x']:.1f} cm",
        f"  Sigma y              : {m['sigma_y']:.1f} cm",
        f"  Mean radial error    : {m['mean_err']:.1f} cm",
        f"  CEP50                : {m['cep50']:.1f} cm",
        f"  Within {TARGET_RADIUS_CM:.0f} cm radius  : {m['within']}/{m['n']} ({pct:.1f}%)",
        "=" * 44,
    ]
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Stats saved: {out_path}")
    print("\n".join(lines))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    csv_path = pick_csv()
    if not csv_path:
        print("No file selected.")
        return

    shots = load_csv(csv_path)
    if not shots:
        print("CSV is empty.")
        return

    print(f"Loaded {len(shots)} shots from {csv_path}")

    m = compute_metrics(shots)

    base = os.path.splitext(csv_path)[0]
    video_name = os.path.basename(base)
    title = video_name.replace("_annotations", "").replace("_", " ")

    plot_scatter(m, f"Ball Landing Scatter — {title}", base + "_scatter.png")
    plot_heatmap(m, f"Ball Landing Heatmap — {title}", base + "_heatmap.png")
    save_stats(m, base + "_stats.txt")

    print("\nDone. All outputs saved next to the CSV file.")


if __name__ == "__main__":
    main()
