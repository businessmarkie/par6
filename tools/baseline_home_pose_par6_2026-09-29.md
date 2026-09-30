---
type: note
status: active
tags: [par6, waldo-commander, baseline, home-pose, wsl, phase-1]
relatedTo: [par6-build, par6-step-frame-convention]
---

# PAR6 home-pose baseline, 2026-09-29

`baseline_home_pose_par6_2026-09-29.jpg` is the 3D viewer of Waldo Commander driving the
PAR6 simulator in WSL2, captured right after boot. It is the **home pose**, not the park pose:

| Joint | Angle |
| --- | --- |
| Base | 90.0° |
| Shoulder | −144.2° |
| Elbow | 109.5° |
| Wrist 1 / 2 / 3 | 0.1° / −0.1° / 0.0° |

TCP readout: X 0.0, Y 193.9, Z 168.6 mm; Rx 73.6°, Ry −0.0°, Rz −89.9°. Tool: MSG small motor
150 mm rail. Stack: Waldo `feat/supervised-restart` (563e02b), waldoctl 0.14.0, par6 0.7.0 wheel,
Ubuntu 24.04 in WSL2. Meshes are the **stock** `par6_description` ones — this is the reference
every refreshed link is diffed against. Capture a park-pose image (`park_pose_rad` in
`par6/config/PAR6.toml`) the same way once a program moves the arm there.
