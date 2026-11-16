"""STEP partitioning, quadratic tetrahedra, surface selection and integration."""

from dataclasses import dataclass
from pathlib import Path
import numpy as np
from .model import Design

# CalculiX / Abaqus local node ordering (zero based).
EDGES = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]
FACES = [(0, 1, 2, 4, 5, 6), (0, 3, 1, 7, 8, 4),
         (1, 3, 2, 8, 9, 5), (2, 3, 0, 9, 7, 6)]


@dataclass
class Mesh:
    points: np.ndarray  # m; contiguous zero-based indexing
    tets: np.ndarray  # Abaqus / VTK order
    surface: np.ndarray  # tri6, matching exterior[] order
    exterior: list  # (one-based element, one-based CalculiX face)
    friction: np.ndarray  # indices into surface
    mount: np.ndarray  # zero-based node indices
    volume_weights: np.ndarray
    area_weights: np.ndarray
    friction_weights: np.ndarray
    unit_torque_loads: np.ndarray
    min_jacobian: float

    @property
    def volume(self):
        return float(self.volume_weights.sum())


def tet_shape(bary):
    """Quadratic tetrahedron N and dN/d(xi,eta,zeta)."""
    dl = np.array([[-1., -1., -1.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
    n = np.r_[bary * (2 * bary - 1), [4 * bary[a] * bary[b] for a, b in EDGES]]
    dn = np.vstack([(4 * bary - 1)[:, None] * dl,
                    [4 * (dl[a] * bary[b] + bary[a] * dl[b]) for a, b in EDGES]])
    return n, dn


def volume_integration(points, tets):
    """4×4×4 Duffy quadrature: curved volume and exact nodal volume integrals."""
    q, w = np.polynomial.legendre.leggauss(4)
    q, w = (q + 1) / 2, w / 2
    xyz = points[tets]
    weights = np.zeros(len(points))
    minimum = float("inf")
    for i, u in enumerate(q):
        for j, v in enumerate(q):
            for k, z in enumerate(q):
                x, y, zz = u, (1 - u) * v, (1 - u) * (1 - v) * z
                n, dn = tet_shape(np.array([1 - x - y - zz, x, y, zz]))
                jac = np.linalg.det(np.einsum("eni,nj->eij", xyz, dn))
                minimum = min(minimum, float(jac.min()))
                dv = jac * w[i] * w[j] * w[k] * (1 - u)**2 * (1 - v)
                np.add.at(weights, tets.ravel(), (dv[:, None] * n).ravel())
    if minimum <= 0:
        raise RuntimeError("Nonpositive quadratic element Jacobian")
    return weights, minimum


def surface_integration(points, triangles):
    """Duffy quadrature of curved tri6 area, nodal integrals and tangential traction."""
    q, w = np.polynomial.legendre.leggauss(4)
    q, w = (q + 1) / 2, w / 2
    xyz = points[triangles]
    weights = np.zeros(len(points))
    tangent = np.zeros((len(points), 3))
    dl = np.array([[-1., -1.], [1., 0.], [0., 1.]])
    for i, u in enumerate(q):
        for j, v in enumerate(q):
            x, y = u, (1 - u) * v
            bary = np.array([1-x-y, x, y])
            n = np.r_[bary * (2*bary-1), [4*bary[a]*bary[b] for a, b in EDGES[:3]]]
            dn = np.vstack([(4*bary-1)[:, None]*dl,
                            [4*(dl[a]*bary[b]+bary[a]*dl[b]) for a, b in EDGES[:3]]])
            jac = np.einsum("eni,nj->eij", xyz, dn)
            da = np.linalg.norm(np.cross(jac[:, :, 0], jac[:, :, 1]), axis=1)
            da *= w[i] * w[j] * (1-u)
            xx = np.einsum("eni,n->ei", xyz, n)
            tr = np.column_stack([-xx[:, 1], xx[:, 0], np.zeros(len(xx))])
            tr /= np.linalg.norm(xx[:, :2], axis=1)[:, None]
            np.add.at(weights, triangles.ravel(), (da[:, None] * n).ravel())
            for axis in range(3):
                np.add.at(tangent[:, axis], triangles.ravel(),
                          (da[:, None]*n*tr[:, axis, None]).ravel())
    return weights, tangent


def generate(step: Path, d: Design, size_mm: float, folder: Path):
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        gmsh.model.add(d.name)
        volumes = gmsh.model.occ.importShapes(str(step))
        # Partition only for mesh/load selection. Keep fragments of the original disc.
        cutter = gmsh.model.occ.addCylinder(0, 0, -1, 0, 0, d.thickness_mm+2,
                                          d.sweep_inner_radius_mm)
        out, mapping = gmsh.model.occ.fragment(volumes, [(3, cutter)])
        keep = set(tuple(t) for group in mapping[:len(volumes)] for t in group)
        gmsh.model.occ.remove([t for t in out if tuple(t) not in keep], recursive=True)
        gmsh.model.occ.synchronize()
        boundary = gmsh.model.getBoundary(sorted(keep), combined=True, oriented=False)
        ring_vols = [t for t in keep if gmsh.model.getBoundingBox(*t)[3]
                     > d.outer_diameter_mm/2 - 0.01]
        ring_boundary = set(gmsh.model.getBoundary(ring_vols, combined=True, oriented=False))
        friction_faces, mount_faces = [], []
        for dim, tag in boundary:
            box = gmsh.model.getBoundingBox(dim, tag)
            com = gmsh.model.occ.getCenterOfMass(dim, tag)
            if box[5] - box[2] < 1e-4 and (dim, tag) in ring_boundary:
                friction_faces.append(tag)
            if (box[5] - box[2] > d.thickness_mm - 1e-4 and
                abs(np.hypot(*com[:2]) - d.bolt_pcd_mm/2) < 1e-4 and
                max(box[3]-box[0], box[4]-box[1]) < d.bolt_diameter_mm+0.01):
                mount_faces.append(tag)
        if len(friction_faces) != 2 or len(mount_faces) != d.bolt_count:
            raise RuntimeError(f"Surface selection failed: friction={friction_faces}, mount={mount_faces}")
        for dim, entities, name in [(3, [t[1] for t in keep], "DISC"),
                                    (2, friction_faces, "FRICTION"), (2, mount_faces, "MOUNT")]:
            group = gmsh.model.addPhysicalGroup(dim, entities)
            gmsh.model.setPhysicalName(dim, group, name)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setNumber("Mesh.MeshSizeMin", min(size_mm, d.thickness_mm/2))
        gmsh.option.setNumber("Mesh.MeshSizeMax", size_mm)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 24)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)
        gmsh.model.mesh.generate(3)
        gmsh.write(str(folder / "mesh.msh"))
        tags, coordinates, _ = gmsh.model.mesh.getNodes()
        order = np.argsort(tags)
        tags, points = tags[order], coordinates.reshape(-1, 3)[order] * 1e-3
        lookup = {int(t): i for i, t in enumerate(tags)}

        def elements(dim, tag, expected):
            types, _, conn = gmsh.model.mesh.getElements(dim, tag)
            chunks = []
            for typ, rows in zip(types, conn):
                if typ != expected:
                    raise RuntimeError(f"Unexpected element type {typ}, expected {expected}")
                width = 10 if dim == 3 else 6
                chunks.append(np.array([lookup[int(n)] for n in rows]).reshape(-1, width))
            return np.vstack(chunks)

        tets = elements(3, -1, 11)[:, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]
        # Discard internal interfaces by cancellation of shared face corner keys.
        faces = {}
        for eid, tet in enumerate(tets, 1):
            for fid, loc in enumerate(FACES, 1):
                tri = tet[list(loc)]
                key = tuple(sorted(tri[:3]))
                if key in faces:
                    faces[key] = None
                else:
                    faces[key] = (eid, fid, tri)
        external = [v for v in faces.values() if v is not None]
        surface = np.array([v[2] for v in external])
        heated_keys = {tuple(sorted(tri[:3])) for tag in friction_faces
                       for tri in elements(2, tag, 9)}
        friction = np.array([i for i, tri in enumerate(surface)
                             if tuple(sorted(tri[:3])) in heated_keys])
        mount = np.unique([lookup[int(n)] for tag in mount_faces
                           for n in gmsh.model.mesh.getNodes(2, tag, includeBoundary=True)[0]])
        if not len(friction) or not len(mount):
            raise RuntimeError("Empty load or constraint node set")
        volume_weights, minimum = volume_integration(points, tets)
        area_weights, _ = surface_integration(points, surface)
        friction_weights, tangents = surface_integration(points, surface[friction])
        torque = np.sum(points[:, 0]*tangents[:, 1] - points[:, 1]*tangents[:, 0])
        mesh = Mesh(points, tets, surface, [(v[0], v[1]) for v in external], friction,
                    mount, volume_weights, area_weights, friction_weights,
                    tangents/torque, minimum)
        np.savez_compressed(folder / "mesh_data.npz", points=points, tets=tets,
                            surface=surface, mount=mount, friction=friction)
        return mesh
    finally:
        gmsh.finalize()
