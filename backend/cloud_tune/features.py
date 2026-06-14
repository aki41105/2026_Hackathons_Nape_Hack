from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from . import FEATURE_VERSION


EPS = 1e-8
IMAGE_SIZE = 256
GRID_SIZE = 4


BASE_FEATURE_ORDER = [
    "brightness_mean",
    "brightness_std",
    "saturation_mean",
    "contrast",
    "blue_ratio",
    "warm_ratio",
    "pink_purple_ratio",
    "green_ratio",
    "white_ratio",
    "gray_ratio",
    "dark_ratio",
    "edge_density",
    "texture_score",
    "vertical_edge_ratio",
    "horizontal_edge_ratio",
    "diagonal_edge_ratio",
    "top_brightness",
    "middle_brightness",
    "bottom_brightness",
    "top_warm_ratio",
    "middle_warm_ratio",
    "bottom_warm_ratio",
    "top_blue_ratio",
    "middle_blue_ratio",
    "bottom_blue_ratio",
    "vertical_brightness_gradient",
    "vertical_warmth_gradient",
    "sky_blue",
    "sky_cloud",
    "sky_gray",
    "sky_warm",
    "sky_texture",
    "sky_clear",
]


GRID_FEATURE_NAMES = [
    f"grid_{row}_{col}_{name}"
    for row in range(GRID_SIZE)
    for col in range(GRID_SIZE)
    for name in ("brightness", "saturation", "warm", "blue", "edge")
]


FEATURE_ORDER = BASE_FEATURE_ORDER + GRID_FEATURE_NAMES


FEATURE_WEIGHTS = {
    "brightness_mean": 1.0,
    "brightness_std": 0.6,
    "saturation_mean": 0.9,
    "contrast": 0.9,
    "blue_ratio": 1.1,
    "warm_ratio": 1.25,
    "pink_purple_ratio": 0.9,
    "green_ratio": 0.65,
    "white_ratio": 0.65,
    "gray_ratio": 0.8,
    "dark_ratio": 1.1,
    "edge_density": 0.8,
    "texture_score": 0.8,
    "vertical_edge_ratio": 0.7,
    "horizontal_edge_ratio": 0.7,
    "diagonal_edge_ratio": 0.7,
    "top_brightness": 0.55,
    "middle_brightness": 0.55,
    "bottom_brightness": 0.55,
    "top_warm_ratio": 0.55,
    "middle_warm_ratio": 0.55,
    "bottom_warm_ratio": 0.55,
    "top_blue_ratio": 0.55,
    "middle_blue_ratio": 0.55,
    "bottom_blue_ratio": 0.55,
    "vertical_brightness_gradient": 0.75,
    "vertical_warmth_gradient": 0.75,
    "sky_blue": 1.2,
    "sky_cloud": 1.1,
    "sky_gray": 1.0,
    "sky_warm": 1.2,
    "sky_texture": 0.9,
    "sky_clear": 1.0,
}

for grid_name in GRID_FEATURE_NAMES:
    FEATURE_WEIGHTS[grid_name] = 0.18


EXPLANATION_FEATURES = [
    ("brightness_mean", "overall brightness"),
    ("saturation_mean", "color vividness"),
    ("warm_ratio", "warm color tone"),
    ("blue_ratio", "blue tone"),
    ("gray_ratio", "gray tone"),
    ("dark_ratio", "darkness"),
    ("contrast", "contrast"),
    ("edge_density", "visual roughness"),
    ("vertical_brightness_gradient", "top-bottom brightness balance"),
    ("vertical_warmth_gradient", "top-bottom warmth balance"),
    ("sky_blue", "sky blue"),
    ("sky_cloud", "cloudiness"),
    ("sky_warm", "sunset or warm sky tone"),
    ("sky_clear", "clear sky openness"),
]


@dataclass(frozen=True)
class ImageFeatures:
    version: str
    vector: list[float]
    raw: dict[str, Any]
    summary: dict[str, Any]


def extract_image_features(path: str | Path) -> ImageFeatures:
    image = Image.open(path).convert("RGB")
    image.thumbnail((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), (0, 0, 0))
    offset = ((IMAGE_SIZE - image.width) // 2, (IMAGE_SIZE - image.height) // 2)
    canvas.paste(image, offset)

    rgb = np.asarray(canvas).astype(np.float32) / 255.0
    mask = _content_mask(rgb)
    hsv = _rgb_to_hsv(rgb)
    gray = _rgb_to_gray(rgb)
    edge = _edge_map(gray)

    features: dict[str, float] = {}
    features.update(_global_features(hsv, edge, mask))
    features.update(_band_features(hsv, mask))
    features.update(_sky_condition_features(hsv, edge, mask))
    features.update(_grid_features(hsv, edge, mask))

    vector = [float(features.get(name, 0.0)) for name in FEATURE_ORDER]
    summary = {
        "feature_version": FEATURE_VERSION,
        "palette": _palette(rgb, mask),
        "bars": _summary_bars(features),
        "grid": _grid_summary(features),
        "content_coverage": float(mask.mean()),
    }
    return ImageFeatures(
        version=FEATURE_VERSION,
        vector=vector,
        raw={name: float(features.get(name, 0.0)) for name in FEATURE_ORDER},
        summary=summary,
    )


def feature_weights() -> list[float]:
    return [float(FEATURE_WEIGHTS.get(name, 1.0)) for name in FEATURE_ORDER]


def _content_mask(rgb: np.ndarray) -> np.ndarray:
    # Ignore black letterbox pixels added by square padding.
    return np.any(rgb > 0.01, axis=2)


def _rgb_to_gray(rgb: np.ndarray) -> np.ndarray:
    return rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114


def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    r = rgb[:, :, 0]
    g = rgb[:, :, 1]
    b = rgb[:, :, 2]
    maxc = np.max(rgb, axis=2)
    minc = np.min(rgb, axis=2)
    delta = maxc - minc

    h = np.zeros_like(maxc)
    nonzero = delta > EPS
    r_is_max = (maxc == r) & nonzero
    g_is_max = (maxc == g) & nonzero
    b_is_max = (maxc == b) & nonzero

    h[r_is_max] = ((g[r_is_max] - b[r_is_max]) / delta[r_is_max]) % 6.0
    h[g_is_max] = ((b[g_is_max] - r[g_is_max]) / delta[g_is_max]) + 2.0
    h[b_is_max] = ((r[b_is_max] - g[b_is_max]) / delta[b_is_max]) + 4.0
    h = h / 6.0

    s = np.zeros_like(maxc)
    s[maxc > EPS] = delta[maxc > EPS] / maxc[maxc > EPS]
    v = maxc
    return np.stack([h, s, v], axis=2)


def _edge_map(gray: np.ndarray) -> dict[str, np.ndarray]:
    gy, gx = np.gradient(gray)
    mag = np.sqrt(gx * gx + gy * gy)
    angle = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0
    return {"gx": gx, "gy": gy, "mag": mag, "angle": angle}


def _masked_mean(values: np.ndarray, mask: np.ndarray) -> float:
    valid = values[mask]
    if valid.size == 0:
        return 0.0
    return float(valid.mean())


def _masked_std(values: np.ndarray, mask: np.ndarray) -> float:
    valid = values[mask]
    if valid.size == 0:
        return 0.0
    return float(valid.std())


def _masked_ratio(values: np.ndarray, mask: np.ndarray) -> float:
    valid = values[mask]
    if valid.size == 0:
        return 0.0
    return float(valid.mean())


def _global_features(hsv: np.ndarray, edge: dict[str, np.ndarray], mask: np.ndarray) -> dict[str, float]:
    h = hsv[:, :, 0]
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]
    mag = edge["mag"]
    angle = edge["angle"]

    valid_v = v[mask]
    if valid_v.size == 0:
        valid_v = v.reshape(-1)

    strong_edge = mag > 0.08
    weighted = mag * mask
    total_edge = float(weighted.sum()) + EPS

    vertical = (((angle < 22.5) | (angle > 157.5)) * weighted).sum() / total_edge
    horizontal = (((angle > 67.5) & (angle < 112.5)) * weighted).sum() / total_edge
    diagonal = ((((angle >= 22.5) & (angle <= 67.5)) | ((angle >= 112.5) & (angle <= 157.5))) * weighted).sum() / total_edge

    blue = (h >= 0.52) & (h <= 0.72) & (s > 0.16) & (v > 0.18)
    warm = (((h <= 0.13) | (h >= 0.94)) & (s > 0.16) & (v > 0.18)) | ((h > 0.13) & (h <= 0.18) & (s > 0.18) & (v > 0.25))
    pink_purple = (h >= 0.74) & (h <= 0.93) & (s > 0.14) & (v > 0.16)
    green = (h >= 0.22) & (h <= 0.46) & (s > 0.18) & (v > 0.12)
    white = (s < 0.20) & (v > 0.72)
    gray = (s < 0.20) & (v >= 0.25) & (v <= 0.72)
    dark = v < 0.25

    return {
        "brightness_mean": _masked_mean(v, mask),
        "brightness_std": _masked_std(v, mask),
        "saturation_mean": _masked_mean(s, mask),
        "contrast": float(np.percentile(valid_v, 90) - np.percentile(valid_v, 10)),
        "blue_ratio": _masked_ratio(blue, mask),
        "warm_ratio": _masked_ratio(warm, mask),
        "pink_purple_ratio": _masked_ratio(pink_purple, mask),
        "green_ratio": _masked_ratio(green, mask),
        "white_ratio": _masked_ratio(white, mask),
        "gray_ratio": _masked_ratio(gray, mask),
        "dark_ratio": _masked_ratio(dark, mask),
        "edge_density": _masked_ratio(strong_edge, mask),
        "texture_score": _masked_mean(mag, mask),
        "vertical_edge_ratio": float(vertical),
        "horizontal_edge_ratio": float(horizontal),
        "diagonal_edge_ratio": float(diagonal),
    }


def _band_features(hsv: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    height = hsv.shape[0]
    bands = {
        "top": slice(0, height // 3),
        "middle": slice(height // 3, 2 * height // 3),
        "bottom": slice(2 * height // 3, height),
    }
    out: dict[str, float] = {}
    for name, row_slice in bands.items():
        band_hsv = hsv[row_slice, :, :]
        band_mask = mask[row_slice, :]
        h = band_hsv[:, :, 0]
        s = band_hsv[:, :, 1]
        v = band_hsv[:, :, 2]
        warm = (((h <= 0.13) | (h >= 0.94)) & (s > 0.16) & (v > 0.18)) | ((h > 0.13) & (h <= 0.18) & (s > 0.18) & (v > 0.25))
        blue = (h >= 0.52) & (h <= 0.72) & (s > 0.16) & (v > 0.18)
        out[f"{name}_brightness"] = _masked_mean(v, band_mask)
        out[f"{name}_warm_ratio"] = _masked_ratio(warm, band_mask)
        out[f"{name}_blue_ratio"] = _masked_ratio(blue, band_mask)

    out["vertical_brightness_gradient"] = out["bottom_brightness"] - out["top_brightness"]
    out["vertical_warmth_gradient"] = out["bottom_warm_ratio"] - out["top_warm_ratio"]
    return out


def _sky_condition_features(hsv: np.ndarray, edge: dict[str, np.ndarray], mask: np.ndarray) -> dict[str, float]:
    top_end = max(1, hsv.shape[0] // 3)
    top_hsv = hsv[:top_end, :, :]
    top_mask = mask[:top_end, :]
    top_edge = edge["mag"][:top_end, :]

    h = top_hsv[:, :, 0]
    s = top_hsv[:, :, 1]
    v = top_hsv[:, :, 2]

    blue = (h >= 0.52) & (h <= 0.72) & (s > 0.16) & (v > 0.18)
    white_cloud = (s < 0.22) & (v > 0.68)
    gray_cloud = (s < 0.25) & (v >= 0.30) & (v <= 0.72)
    warm = ((((h <= 0.13) | (h >= 0.94)) & (s > 0.16) & (v > 0.18)) | ((h > 0.13) & (h <= 0.18) & (s > 0.18) & (v > 0.25)))

    sky_blue = _masked_ratio(blue, top_mask)
    sky_cloud = _masked_ratio(white_cloud | gray_cloud, top_mask)
    sky_gray = _masked_ratio(gray_cloud, top_mask)
    sky_warm = _masked_ratio(warm, top_mask)
    raw_texture = _masked_mean(top_edge, top_mask)
    sky_texture = float(np.clip(raw_texture * 6.0, 0.0, 1.0))
    sky_clear = float(np.clip(0.50 * sky_blue + 0.30 * (1.0 - sky_cloud) + 0.20 * (1.0 - sky_texture), 0.0, 1.0))

    return {
        "sky_blue": sky_blue,
        "sky_cloud": sky_cloud,
        "sky_gray": sky_gray,
        "sky_warm": sky_warm,
        "sky_texture": sky_texture,
        "sky_clear": sky_clear,
    }


def _grid_features(hsv: np.ndarray, edge: dict[str, np.ndarray], mask: np.ndarray) -> dict[str, float]:
    out: dict[str, float] = {}
    height, width = hsv.shape[:2]
    mag = edge["mag"]
    for row in range(GRID_SIZE):
        r0 = row * height // GRID_SIZE
        r1 = (row + 1) * height // GRID_SIZE
        for col in range(GRID_SIZE):
            c0 = col * width // GRID_SIZE
            c1 = (col + 1) * width // GRID_SIZE
            cell_hsv = hsv[r0:r1, c0:c1, :]
            cell_mask = mask[r0:r1, c0:c1]
            h = cell_hsv[:, :, 0]
            s = cell_hsv[:, :, 1]
            v = cell_hsv[:, :, 2]
            warm = (((h <= 0.13) | (h >= 0.94)) & (s > 0.16) & (v > 0.18)) | ((h > 0.13) & (h <= 0.18) & (s > 0.18) & (v > 0.25))
            blue = (h >= 0.52) & (h <= 0.72) & (s > 0.16) & (v > 0.18)
            prefix = f"grid_{row}_{col}"
            out[f"{prefix}_brightness"] = _masked_mean(v, cell_mask)
            out[f"{prefix}_saturation"] = _masked_mean(s, cell_mask)
            out[f"{prefix}_warm"] = _masked_ratio(warm, cell_mask)
            out[f"{prefix}_blue"] = _masked_ratio(blue, cell_mask)
            out[f"{prefix}_edge"] = _masked_mean(mag[r0:r1, c0:c1], cell_mask)
    return out


def _palette(rgb: np.ndarray, mask: np.ndarray, colors: int = 5) -> list[dict[str, Any]]:
    pixels = rgb[mask]
    if pixels.size == 0:
        return []
    quantized = np.floor(pixels * 8).astype(np.int16)
    keys, counts = np.unique(quantized, axis=0, return_counts=True)
    order = np.argsort(counts)[::-1][:colors]
    total = float(counts.sum())
    palette = []
    for idx in order:
        center = np.clip((keys[idx] + 0.5) / 8.0, 0.0, 1.0)
        rgb255 = np.round(center * 255).astype(int)
        palette.append(
            {
                "hex": "#{:02x}{:02x}{:02x}".format(int(rgb255[0]), int(rgb255[1]), int(rgb255[2])),
                "ratio": float(counts[idx] / total),
            }
        )
    return palette


def _summary_bars(features: dict[str, float]) -> list[dict[str, Any]]:
    pairs = [
        ("brightness", "brightness_mean"),
        ("vividness", "saturation_mean"),
        ("warmth", "warm_ratio"),
        ("blue", "blue_ratio"),
        ("gray", "gray_ratio"),
        ("darkness", "dark_ratio"),
        ("contrast", "contrast"),
        ("roughness", "edge_density"),
    ]
    return [{"name": label, "value": float(np.clip(features.get(key, 0.0), 0.0, 1.0))} for label, key in pairs]


def _grid_summary(features: dict[str, float]) -> list[list[dict[str, float]]]:
    rows = []
    for row in range(GRID_SIZE):
        cells = []
        for col in range(GRID_SIZE):
            prefix = f"grid_{row}_{col}"
            cells.append(
                {
                    "brightness": float(features.get(f"{prefix}_brightness", 0.0)),
                    "warm": float(features.get(f"{prefix}_warm", 0.0)),
                    "blue": float(features.get(f"{prefix}_blue", 0.0)),
                    "edge": float(features.get(f"{prefix}_edge", 0.0)),
                }
            )
        rows.append(cells)
    return rows
