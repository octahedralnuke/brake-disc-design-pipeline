"""Parametric CadQuery model, STEP export and dimensioned SVG drawing."""

import math
from pathlib import Path
from .model import Design


def hole_centers(pcd, count):
    return [(pcd / 2 * math.cos(2 * math.pi * i / count),
             pcd / 2 * math.sin(2 * math.pi * i / count)) for i in range(count)]


def build(d: Design, folder: Path):
    import cadquery as cq

    disc = cq.Workplane("XY").circle(d.outer_diameter_mm / 2).circle(
        d.bore_diameter_mm / 2).extrude(d.thickness_mm)
    disc = disc.faces(">Z").workplane().pushPoints(hole_centers(d.bolt_pcd_mm, d.bolt_count)).hole(
        d.bolt_diameter_mm)
    if d.drill_count:
        disc = disc.faces(">Z").workplane().pushPoints(
            hole_centers(d.drill_pcd_mm, d.drill_count)).hole(d.drill_diameter_mm)
    if not disc.val().isValid() or len(disc.solids().vals()) != 1:
        raise RuntimeError("CadQuery did not create one valid solid")
    volume = disc.val().Volume() * 1e-9
    if abs(volume / d.analytical_volume_m3 - 1) > 1e-7:
        raise RuntimeError("CAD and analytical volumes disagree")
    cq.exporters.export(disc, str(folder / "disc.step"))
    cq.exporters.exportDXF(disc.faces(">Z").wires(), str(folder / "profile.dxf"))
    drawing(d, folder / "drawing.svg")
    return volume


def drawing(d: Design, path: Path):
    """Drawing uses model dimensions directly; evaluation drawing, no invented tolerances."""
    scale, cx, cy = 1.7, 245, 255
    ro, ri = d.outer_diameter_mm / 2 * scale, d.bore_diameter_mm / 2 * scale
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="650" viewBox="0 0 1000 650">',
             '<rect width="1000" height="650" fill="white"/>',
             '<style>text{font-family:Arial,sans-serif;fill:#142639} .edge{fill:none;stroke:#142639;stroke-width:1.8} .dim{fill:none;stroke:#52718b;stroke-width:1} .dash{stroke-dasharray:7 5}</style>',
             '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto-start-reverse"><path d="M8 0L0 4L8 8" fill="none" stroke="#52718b"/></marker></defs>',
             f'<text x="45" y="42" font-size="25" font-weight="bold">BRAKE DISC / {d.name.upper()}</text>',
             '<text x="45" y="65" font-size="13">Dimensioned evaluation drawing · dimensions in mm · do not scale</text>']

    def circle(x, y, r, cls="edge"):
        parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" class="{cls}"/>')

    circle(cx, cy, ro)
    circle(cx, cy, ri)
    circle(cx, cy, d.bolt_pcd_mm / 2 * scale, "dim dash")
    circle(cx, cy, d.sweep_inner_radius_mm * scale, "dim dash")
    for pcd, count, dia in [(d.bolt_pcd_mm, d.bolt_count, d.bolt_diameter_mm),
                             (d.drill_pcd_mm, d.drill_count, d.drill_diameter_mm)]:
        for x, y in hole_centers(pcd, count):
            circle(cx + x * scale, cy - y * scale, dia / 2 * scale)
    parts += [f'<path d="M{cx-ro-16} {cy}H{cx+ro+16}M{cx} {cy-ro-16}V{cy+ro+16}" class="dim dash"/>']

    def dim(x1, y1, x2, y2, label, tx, ty):
        parts.append(f'<path d="M{x1} {y1}L{x2} {y2}" class="dim" marker-start="url(#arrow)" marker-end="url(#arrow)"/>')
        parts.append(f'<text x="{tx}" y="{ty}" font-size="14" text-anchor="middle">{label}</text>')

    dim(cx-ro, 455, cx+ro, 455, f'Ø{d.outer_diameter_mm:g}', cx, 477)
    parts.append(f'<path d="M{cx-ro} {cy}V462M{cx+ro} {cy}V462" class="dim"/>')
    dim(cx-ri, cy+8, cx+ri, cy+8, f'Ø{d.bore_diameter_mm:g} THRU', cx, cy-8)
    parts.append(f'<rect x="560" y="{cy-ro}" width="{max(d.thickness_mm*scale,3)}" height="{2*ro}" class="edge"/>')
    dim(560, 455, 560+d.thickness_mm*scale, 455, f'{d.thickness_mm:g}', 565, 477)
    notes = ["FRONT VIEW", f"{d.bolt_count} × Ø{d.bolt_diameter_mm:g} THRU, EQ SP ON Ø{d.bolt_pcd_mm:g} PCD",
             f"Swept annulus: R{d.sweep_inner_radius_mm:g} to R{d.outer_diameter_mm/2:g}",
             "SIDE VIEW", "Material: generic steel (see configuration)",
             "Nominal geometry; manufacturing tolerances not assigned.",
             "Bolt holes constrain the idealized FEA mount."]
    if d.drill_count:
        notes.insert(3, f"{d.drill_count} × Ø{d.drill_diameter_mm:g} THRU, EQ SP ON Ø{d.drill_pcd_mm:g} PCD")
    for i, note in enumerate(notes):
        parts.append(f'<text x="620" y="{130+i*31}" font-size="13">{note}</text>')
    parts += ['<rect x="35" y="525" width="930" height="90" class="edge"/>',
              '<text x="50" y="550" font-size="17" font-weight="bold">BRAKE DISC DESIGN PIPELINE</text>',
              f'<text x="50" y="575" font-size="14">Part: {d.name} | Revision: configuration-controlled | Sheet 1 / 1</text>',
              '<text x="50" y="598" font-size="12">Generated from the same parameters as the STEP model. Educational analysis model.</text>', '</svg>']
    path.write_text("\n".join(parts))
