#!/usr/bin/env python3
"""
svg2plate.py - Turn a pixel-art SVG logo (made of <rect> elements) into a
laser-cuttable sheet-metal plate with the logo cut out (inverted), exported
as STEP (and optionally DXF).

The plate is built on the same pixel grid as the logo, so the margin and the
rounded corners are stepped ("pixelated") just like the logo itself.

Islands (e.g. the inside of an "O") would fall out when the logo is cut out
of the plate. By default they are held in place by small stencil bridges.

Usage:
    python3 svg2plate.py logo.svg --width 300 --thickness 2
    python3 svg2plate.py logo.svg --width 500 --thickness 3 --margin 3 \
        --corner-steps 3 --dxf -o sign

Requirements:
    pip install shapely ezdxf cadquery-ocp
"""
import argparse
import math
import sys
import xml.etree.ElementTree as ET

from shapely import affinity
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

SVG_NS = "{http://www.w3.org/2000/svg}"


# --------------------------------------------------------------------------
# SVG parsing
# --------------------------------------------------------------------------
def load_logo(svg_path):
    """Return (logo geometry, pixel width, pixel height) in SVG units, y up."""
    root = ET.parse(svg_path).getroot()
    if root.get("viewBox"):
        view_h = float(root.get("viewBox").split()[3])
    else:
        view_h = float(root.get("height", "0").rstrip("px"))

    rects = []
    for r in root.iter(SVG_NS + "rect"):
        if r.get("fill") == "none":
            continue
        x, y = float(r.get("x", 0)), float(r.get("y", 0))
        w, h = float(r.get("width")), float(r.get("height"))
        rects.append((x, view_h - y - h, w, h))  # flip y: SVG is y-down

    if not rects:
        sys.exit("No <rect> elements found - this script only handles pixel-art SVGs.")
    if any(next(root.iter(SVG_NS + tag), None) is not None
           for tag in ("path", "polygon", "circle", "ellipse")):
        print("Warning: SVG contains non-rect shapes; they are ignored.", file=sys.stderr)

    px = min(w for _, _, w, _ in rects)  # one grid cell
    py = min(h for _, _, _, h in rects)
    logo = unary_union([box(x, y, x + w, y + h) for x, y, w, h in rects])
    return logo, px, py


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
def pixel_corner_cells(steps):
    """Cells (col, row) counted from a corner that are removed to get a
    45-degree staircase of `steps` pixels - the same corner style the
    logo letters use."""
    return [(i, j) for i in range(steps) for j in range(steps) if i + j < steps]


def make_plate(logo, px, py, margin, steps):
    """Rectangular plate on the logo grid with stepped corners."""
    minx, miny, maxx, maxy = logo.bounds
    x0, y0 = minx - margin * px, miny - margin * py
    x1, y1 = maxx + margin * px, maxy + margin * py
    plate = box(x0, y0, x1, y1)

    cuts = []
    for i, j in pixel_corner_cells(steps):
        # bottom-left, bottom-right, top-left, top-right
        for cx, sx in ((x0, 1), (x1, -1)):
            for cy, sy in ((y0, 1), (y1, -1)):
                ax, ay = cx + sx * i * px, cy + sy * j * py
                cuts.append(box(min(ax, ax + sx * px), min(ay, ay + sy * py),
                                max(ax, ax + sx * px), max(ay, ay + sy * py)))
    return plate.difference(unary_union(cuts)) if cuts else plate


def as_list(geom):
    if geom.is_empty:
        return []
    return list(geom.geoms) if hasattr(geom, "geoms") else [geom]


def add_bridges(plate, islands, px, bridge_px):
    """Connect each island to the surrounding plate with the shorter of an
    upward or downward bridge, `bridge_px` grid cells wide, aligned to the grid."""
    holes = [Polygon(r) for r in plate.interiors]
    bridges = []
    for island in islands:
        hole = next((h for h in holes if h.contains(island)), None)
        if hole is None:
            continue
        cx, cy = island.centroid.x, island.centroid.y
        bw = bridge_px * px
        # grid-aligned strip through the island centre
        col0 = math.floor(cx / px - bridge_px / 2 + 0.5) * px
        hx0, hy0, hx1, hy1 = hole.bounds
        ix0, iy0, ix1, iy1 = island.bounds
        candidates = [
            box(col0, iy1, col0 + bw, hy1),  # up
            box(col0, hy0, col0 + bw, iy0),  # down
        ]
        best = None
        for strip in candidates:
            pieces = [p for p in as_list(strip.intersection(hole)) if p.touches(island) or p.intersects(island)]
            if not pieces:
                continue
            piece = min(pieces, key=lambda p: p.area)
            if best is None or piece.area < best.area:
                best = piece
        if best is not None:
            bridges.append(best)
    return bridges


def build_part(logo, px, py, margin, steps, islands_mode, bridge_px):
    plate = make_plate(logo, px, py, margin, steps)
    parts = sorted(as_list(plate.difference(logo)), key=lambda p: -p.area)
    main, islands = parts[0], parts[1:]

    if islands_mode == "bridge" and islands:
        bridges = add_bridges(main, islands, px, bridge_px)
        main = unary_union([main, *islands, *bridges])
        parts = sorted(as_list(main), key=lambda p: -p.area)
        main, islands = parts[0], parts[1:]
        if islands:
            print(f"Warning: {len(islands)} island(s) could not be bridged.", file=sys.stderr)

    if islands_mode == "drop":
        return [main]
    return [main, *islands]  # "keep": islands exported as separate bodies


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def export_step(polys, thickness, path):
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopoDS import TopoDS_Compound

    def make_wire(ring):
        mp = BRepBuilderAPI_MakePolygon()
        for x, y in list(ring.coords)[:-1]:
            mp.Add(gp_Pnt(x, y, 0.0))
        mp.Close()
        return mp.Wire()

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for poly in polys:
        poly = poly.normalize()  # outer ring CCW, holes CW
        face_maker = BRepBuilderAPI_MakeFace(make_wire(poly.exterior))
        for hole in poly.interiors:
            face_maker.Add(make_wire(hole))
        solid = BRepPrimAPI_MakePrism(face_maker.Face(), gp_Vec(0, 0, thickness)).Shape()
        builder.Add(compound, solid)

    Interface_Static.SetCVal_s("write.step.unit", "MM")
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    if writer.Write(path) != 1:
        sys.exit(f"STEP export failed: {path}")


def export_dxf(polys, path):
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("CUT", color=1)
    msp = doc.modelspace()
    for poly in polys:
        for ring in (poly.exterior, *poly.interiors):
            msp.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": "CUT"})
    doc.saveas(path)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Pixel-art SVG -> inverted sheet-metal plate (STEP).")
    ap.add_argument("svg", help="input SVG made of <rect> pixels")
    ap.add_argument("-w", "--width", type=float, required=True,
                    help="overall plate width in mm (height follows proportionally)")
    ap.add_argument("-t", "--thickness", type=float, required=True, help="sheet thickness in mm")
    ap.add_argument("-m", "--margin", type=int, default=2, help="border around the logo in pixels (default 2)")
    ap.add_argument("-c", "--corner-steps", type=int, default=2,
                    help="pixel steps per plate corner, 0 = sharp (default 2)")
    ap.add_argument("--islands", choices=("bridge", "keep", "drop"), default="bridge",
                    help="inner islands (e.g. inside of 'O'): bridge = hold with stencil bridges, "
                         "keep = separate bodies, drop = let them fall out (default bridge)")
    ap.add_argument("--bridge-width", type=int, default=1, help="bridge width in pixels (default 1)")
    ap.add_argument("-o", "--output", default=None, help="output base name (default: SVG name)")
    ap.add_argument("--dxf", action="store_true", help="also write a DXF for the laser shop")
    args = ap.parse_args()

    if args.corner_steps > args.margin + 1:
        print("Warning: corner steps larger than margin may cut into the logo.", file=sys.stderr)

    logo, px, py = load_logo(args.svg)
    polys = build_part(logo, px, py, args.margin, args.corner_steps, args.islands, args.bridge_width)

    # scale to target width, origin at bottom-left
    minx = min(p.bounds[0] for p in polys)
    miny = min(p.bounds[1] for p in polys)
    maxx = max(p.bounds[2] for p in polys)
    maxy = max(p.bounds[3] for p in polys)
    s = args.width / (maxx - minx)
    polys = [affinity.scale(affinity.translate(p, -minx, -miny), s, s, origin=(0, 0)).simplify(0)
             for p in polys]

    base = args.output or args.svg.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    step_path = f"{base}_{args.width:g}mm_t{args.thickness:g}.step"
    export_step(polys, args.thickness, step_path)
    if args.dxf:
        export_dxf(polys, step_path[:-5] + ".dxf")

    pixel_w, pixel_h = px * s, py * s
    print(f"Plate:       {args.width:.1f} x {(maxy - miny) * s:.1f} x {args.thickness:g} mm")
    print(f"Pixel size:  {pixel_w:.2f} x {pixel_h:.2f} mm")
    print(f"Bodies:      {len(polys)}")
    print(f"Cut length:  {sum(p.length for p in polys) / 1000:.2f} m")
    print(f"Written:     {step_path}" + (f", {step_path[:-5]}.dxf" if args.dxf else ""))
    if min(pixel_w, pixel_h) * args.bridge_width < args.thickness:
        print("Warning: bridge/feature width is smaller than sheet thickness - "
              "increase --width or --bridge-width, or use thinner sheet.", file=sys.stderr)


if __name__ == "__main__":
    main()
