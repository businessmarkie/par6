"""Recover the rigid transform that places a STEP part into a URDF link frame.

The STEP exports and the vendored link meshes describe the same hardware in
different frames, so placement is a registration problem rather than a modelling
one. Two things make a plain ICP untrustworthy here and are handled explicitly:

* PAR6 parts are close to mirror-symmetric, and an unconstrained fit happily
  returns a reflection that scores as well as the truth. Only proper rotations
  (det = +1) are accepted.
* ICP finds the nearest local minimum, so it is seeded from all 24 axis-aligned
  orientations and the seeds are ranked by the fit they actually reach.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

# Fits are judged on surface distance in metres. A part placed correctly sits
# within tessellation noise of the reference; anything past this is reported
# rather than silently accepted.
GOOD_FIT_RMS_M = 0.0015

SAMPLE_POINTS = 4000


def _proper_axis_rotations() -> list[np.ndarray]:
    """The 24 rotations mapping the axis frame onto itself, reflections excluded."""
    rotations = []
    for perm in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)):
        for signs in np.ndindex(2, 2, 2):
            matrix = np.zeros((3, 3))
            for row, (axis, sign) in enumerate(zip(perm, signs)):
                matrix[row, axis] = 1.0 - 2.0 * sign
            if np.linalg.det(matrix) > 0:
                rotations.append(matrix)
    return rotations


AXIS_ROTATIONS = _proper_axis_rotations()


@dataclass(frozen=True)
class Fit:
    transform: np.ndarray
    rms_m: float
    max_m: float
    covered: float  # fraction of sampled points within GOOD_FIT_RMS_M of the reference

    @property
    def is_good(self) -> bool:
        return self.rms_m <= GOOD_FIT_RMS_M


def _residuals(mesh: trimesh.Trimesh, reference: trimesh.Trimesh, points: np.ndarray) -> np.ndarray:
    _closest, distance, _face = reference.nearest.on_surface(points)
    return distance


def _seed_transform(mesh: trimesh.Trimesh, reference: trimesh.Trimesh, rotation: np.ndarray) -> np.ndarray:
    """Place the rotated part so its centroid lands on the reference centroid."""
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = reference.centroid - rotation @ mesh.centroid
    return transform


def fit_to_reference(
    mesh: trimesh.Trimesh,
    reference: trimesh.Trimesh,
    *,
    seeds: int = 6,
) -> Fit:
    """Best proper-rigid placement of `mesh` onto `reference`.

    All 24 axis-aligned orientations are scored cheaply by centroid alignment;
    the most promising `seeds` of them are then refined with ICP and the winner
    is whichever refined fit has the lowest RMS surface distance.
    """
    points = mesh.sample(SAMPLE_POINTS)
    homogeneous = np.hstack([points, np.ones((len(points), 1))])

    scored = []
    for rotation in AXIS_ROTATIONS:
        transform = _seed_transform(mesh, reference, rotation)
        moved = (homogeneous @ transform.T)[:, :3]
        scored.append((float(np.mean(_residuals(mesh, reference, moved))), transform))
    scored.sort(key=lambda item: item[0])

    best: Fit | None = None
    for _score, seed in scored[:seeds]:
        moved = (homogeneous @ seed.T)[:, :3]
        refined, _transformed, _cost = trimesh.registration.icp(
            moved, reference, initial=np.eye(4), max_iterations=100, scale=False
        )
        transform = refined @ seed
        if np.linalg.det(transform[:3, :3]) < 0:
            continue  # a reflection is never the right answer for a real part
        final = (homogeneous @ transform.T)[:, :3]
        distance = _residuals(mesh, reference, final)
        candidate = Fit(
            transform=transform,
            rms_m=float(np.sqrt(np.mean(distance**2))),
            max_m=float(np.max(distance)),
            covered=float(np.mean(distance <= GOOD_FIT_RMS_M)),
        )
        if best is None or candidate.rms_m < best.rms_m:
            best = candidate

    if best is None:
        raise RuntimeError("every ICP seed collapsed to a reflection")
    return best
