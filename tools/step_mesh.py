"""Tessellate a STEP file into a trimesh, in metres.

SolidWorks writes STEP in millimetres; every URDF in assets/par6_description is
in metres, so the conversion happens here once rather than at each call site.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

MM_TO_M = 0.001

# Tessellation tolerances in millimetres / radians. Fine enough that bolt holes
# and bosses survive -- those features are what the registration pass in
# step_to_meshes.py aligns on, so smoothing them away would cost placement
# accuracy, not just looks.
LINEAR_DEFLECTION_MM = 0.1
ANGULAR_DEFLECTION_RAD = 0.2


def load_step(path: Path) -> trimesh.Trimesh:
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise ValueError(f"{path.name}: STEP reader returned {status}")
    reader.TransferRoots()
    shape = reader.OneShape()

    BRepMesh_IncrementalMesh(
        shape, LINEAR_DEFLECTION_MM, False, ANGULAR_DEFLECTION_RAD, True
    )

    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    offset = 0

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            explorer.Next()
            continue

        transform = location.Transformation()
        n_nodes = triangulation.NbNodes()
        face_vertices = np.empty((n_nodes, 3))
        for i in range(1, n_nodes + 1):
            point = triangulation.Node(i).Transformed(transform)
            face_vertices[i - 1] = (point.X(), point.Y(), point.Z())

        n_tris = triangulation.NbTriangles()
        face_faces = np.empty((n_tris, 3), dtype=np.int64)
        # A face tessellated on a reversed surface yields triangles wound the
        # wrong way; flipping them here keeps the merged mesh's normals
        # outward, which is what makes volume and watertightness meaningful.
        reversed_face = face.Orientation() == TopAbs_REVERSED
        for i in range(1, n_tris + 1):
            a, b, c = triangulation.Triangle(i).Get()
            face_faces[i - 1] = (a - 1, c - 1, b - 1) if reversed_face else (a - 1, b - 1, c - 1)

        vertices.append(face_vertices)
        faces.append(face_faces + offset)
        offset += n_nodes
        explorer.Next()

    if not vertices:
        raise ValueError(f"{path.name}: tessellated to zero faces")

    mesh = trimesh.Trimesh(
        vertices=np.vstack(vertices) * MM_TO_M,
        faces=np.vstack(faces),
        process=True,
    )
    mesh.merge_vertices()
    return mesh
