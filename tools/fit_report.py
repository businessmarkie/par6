"""Per-link placement report: each folder's main structural part against the
shipped link mesh it corresponds to.

Judged by reference coverage -- how much of the shipped link's surface has new
geometry within tolerance -- because a single part's interior faces are never
on the merged link's surface and would make source-to-reference distance read
as a bad fit for a correct placement.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).parent))
from register import AXIS_ROTATIONS, GOOD_FIT_RMS_M, SAMPLE_POINTS, _seed_transform  # noqa: E402
from step_mesh import load_step  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
STEP_ROOT = ROOT / "step_src" / "STEP"
REF_ROOT = ROOT / "par6" / "assets" / "par6_description" / "assets"

# URDF link -> the one part in its STEP folder that is exported in the
# assembly frame (the printable lids and covers are laid out flat instead).
MAIN_PARTS = {
    "base_link": "A6_Base/Base.STEP",
    "shoulder": "A5_Shoulder/Turret.STEP",
    "upper_arm": "A4_Upper_arm/Upper_arm.STEP",
    "elbow": "A3_Elbow/Elbow_part.STEP",
    "lower_arm": "A2_Lower_arm/J5_part.STEP",
    "wrist": "A1_Wrist/Wrist.STEP",
    "gripper_flange": "A0_End_effector/PAR6_flange.STEP",
}


def reference_coverage(placed: trimesh.Trimesh, reference: trimesh.Trimesh, ref_points: np.ndarray) -> dict:
    _c, distance, _f = placed.nearest.on_surface(ref_points)
    return {
        "ref_rms_mm": float(np.sqrt(np.mean(distance**2)) * 1000),
        "ref_median_mm": float(np.median(distance) * 1000),
        "ref_covered_1p5mm": float(np.mean(distance <= GOOD_FIT_RMS_M)),
    }


def fit_link(link: str, rel: str) -> dict:
    started = time.time()
    part = load_step(STEP_ROOT / rel)
    reference = trimesh.load(REF_ROOT / f"{link}.STL")
    ref_points = reference.sample(SAMPLE_POINTS)
    src_points = part.sample(SAMPLE_POINTS)
    homogeneous = np.hstack([src_points, np.ones((len(src_points), 1))])

    # Rank all 24 proper axis orientations by reference coverage, refine the top few.
    seeds = []
    for rotation in AXIS_ROTATIONS:
        transform = _seed_transform(part, reference, rotation)
        placed = part.copy()
        placed.apply_transform(transform)
        score = reference_coverage(placed, reference, ref_points)["ref_rms_mm"]
        seeds.append((score, transform))
    seeds.sort(key=lambda item: item[0])

    best = None
    for _score, seed in seeds[:4]:
        moved = (homogeneous @ seed.T)[:, :3]
        refined, _t, _c = trimesh.registration.icp(
            moved, reference, initial=np.eye(4), max_iterations=100, scale=False
        )
        transform = refined @ seed
        if np.linalg.det(transform[:3, :3]) < 0:
            continue
        placed = part.copy()
        placed.apply_transform(transform)
        metrics = reference_coverage(placed, reference, ref_points)
        if best is None or metrics["ref_rms_mm"] < best["metrics"]["ref_rms_mm"]:
            rotation = transform[:3, :3]
            best = {
                "metrics": metrics,
                "transform": transform.tolist(),
                "rot_z_deg": float(np.degrees(np.arctan2(rotation[1, 0], rotation[0, 0]))),
                "placed_bounds_m": placed.bounds.tolist(),
            }

    return {
        "link": link,
        "part": rel,
        "part_tris": int(len(part.faces)),
        "part_extent_mm": (part.extents * 1000).round(1).tolist(),
        "ref_tris": int(len(reference.faces)),
        "ref_extent_mm": (reference.extents * 1000).round(1).tolist(),
        "seconds": round(time.time() - started, 1),
        **(best or {"metrics": None, "transform": None}),
    }


def main() -> None:
    report = []
    for link, rel in MAIN_PARTS.items():
        result = fit_link(link, rel)
        report.append(result)
        m = result["metrics"]
        print(
            f"{link:15} {Path(rel).name:20} ref-cov={m['ref_covered_1p5mm']:6.1%} "
            f"ref-rms={m['ref_rms_mm']:6.2f}mm median={m['ref_median_mm']:5.2f}mm "
            f"rotz={result['rot_z_deg']:7.1f}  ({result['seconds']}s)",
            flush=True,
        )
    out = Path(__file__).parent / "fit_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
