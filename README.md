# svg2plate

Turn a pixel-art SVG logo into a laser-cuttable sheet-metal plate. The logo is **cut out of the plate** (inverted), and the result is exported as a **STEP** solid (and optionally as a **DXF** cut contour).

https://github.com/user-attachments/assets/3920bcaa-afb0-46bb-9d64-8ea187e8ba35

## Features

- **Proportional scaling.** You set the overall plate width in mm, and the height follows automatically.
- **Sheet thickness** is a parameter.
- **Pixel-grid plate.** The margin and corners are built on the logo's own pixel grid, so the stepped corners match the style of the letters.
- **Island handling.** Islands are inner parts such as the inside of an `O`, `A` or `R`, which would otherwise fall out. By default they are held in place by small stencil bridges, so the result is a single part.
- **Clean geometry.** The output contains only straight lines, with no splines and no tiny segments. Collinear points are merged.
- **Plausibility warnings.** The script warns when a bridge is narrower than the sheet thickness.

## Requirements

- Python 3.9+
- [shapely](https://pypi.org/project/shapely/) for 2D geometry
- [ezdxf](https://pypi.org/project/ezdxf/) for DXF export
- [cadquery-ocp](https://pypi.org/project/cadquery-ocp/), the OpenCascade bindings used for STEP export

```bash
pip install -r requirements.txt
```

No FreeCAD installation is needed. The resulting STEP opens directly in FreeCAD, Fusion, SolidWorks and similar tools.

## Usage

```bash
python3 svg2plate.py logo.svg --width 300 --thickness 2
```

Output: `logo_300mm_t2.step`

```text
Plate:       300.0 x 79.6 x 2 mm
Pixel size:  3.53 x 3.46 mm
Bodies:      1
Cut length:  2.96 m
Written:     logo_300mm_t2.step
```

### More examples

```bash
# 500 mm wide, 3 mm sheet, wider bridges, also write a DXF for the laser shop
python3 svg2plate.py logo.svg -w 500 -t 3 --bridge-width 2 --dxf

# larger margin and rounder corners
python3 svg2plate.py logo.svg -w 400 -t 2 --margin 3 --corner-steps 3

# keep the islands as separate bodies (e.g. to glue onto a backing plate)
python3 svg2plate.py logo.svg -w 300 -t 2 --islands keep

# sharp corners, custom output name
python3 svg2plate.py logo.svg -w 300 -t 2 --corner-steps 0 -o sign
```

## Options

| Option | Default | Description |
|---|---|---|
| `-w`, `--width` | required | Overall plate width in mm. The height is scaled proportionally. |
| `-t`, `--thickness` | required | Sheet thickness in mm. |
| `-m`, `--margin` | `2` | Border around the logo, in pixels. |
| `-c`, `--corner-steps` | `2` | Pixel steps per plate corner (45° staircase). `0` gives sharp corners. |
| `--islands` | `bridge` | `bridge` holds islands with stencil bridges, `keep` exports them as separate bodies, and `drop` leaves them out. |
| `--bridge-width` | `1` | Bridge width in pixels. |
| `-o`, `--output` | SVG name | Base name for the output files. |
| `--dxf` | off | Also write a DXF (mm, layer `CUT`, closed polylines). |

## Input format

The script expects a **pixel-art SVG built from `<rect>` elements**. Many generated wordmarks and logos look like this:

```xml
<svg viewBox="0 0 4131 950">
  <rect x="867" y="0" width="153" height="50"/>
  <rect x="102" y="50" width="255" height="50"/>
  ...
</svg>
```

- The grid cell size is taken from the smallest rect width and height.
- Fill colours and gradients are ignored, and rects with `fill="none"` are skipped.
- Other shapes (`<path>`, `<circle>`, …) are ignored, and the script prints a warning.
- `transform` attributes are not supported.

## Manufacturing notes

- **Minimum feature size.** As a rule of thumb, the narrowest web or slot should be at least as wide as the sheet thickness. Check the printed `Pixel size`. If the bridges get too thin, increase `--width` or `--bridge-width`, or use thinner sheet.
- **DXF or STEP.** Most laser shops prefer a DXF, so add `--dxf` for them. Use the STEP for CAD assemblies, mounting design or press-brake work.
- **Kerf.** No kerf compensation is applied. This is normally done by the laser shop's CAM software.

## How it works

1. All `<rect>` elements are merged into one polygon on the pixel grid (y-axis flipped from SVG to CAD orientation).
2. A rectangular plate is built around it, expanded by `margin` cells, and staircase cells are removed at the corners.
3. The logo is subtracted from the plate. Any leftover islands are bridged, kept or dropped, depending on `--islands`.
4. The geometry is scaled to the target width with its origin at the bottom left.
5. Each polygon is turned into an OpenCascade face with holes, extruded by the sheet thickness, and written to STEP in mm.

## License

The code is released under MIT (adjust as needed). Logos you process remain subject to their own license or trademark terms.
