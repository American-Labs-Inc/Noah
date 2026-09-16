# 3D models

`NOAH_Terminal.blend` is the Blender source (millimeter scene, 1 unit = 1 mm).
The STLs are exported print-ready in real-world millimeters.

## Parts

| File | Part | Material |
|---|---|---|
| `STL/NOAH_Shell.stl` | Main clamshell body (print whole on ≥300 mm beds) | PETG |
| `Shell_Cuts/ShellV_*, ShellH_*, ShellQ_*` | The same shell, pre-cut into halves or quarters for smaller printers. Pick ONE scheme | PETG |
| `STL/NOAH_FrontPlate.stl` | Front plate with keyboard bay | PETG |
| `STL/NOAH_Visor.stl` | Screen visor (magnet-mounted) | PETG |
| `STL/NOAH_ScreenRetainer.stl` | Clamps the e-ink panel | PETG |
| `STL/NOAH_BasePlate.stl` | Bottom closure | PETG |
| `STL/NOAH_SidePlate_L.stl` / `_R.stl` | Side plates. **Different designs, not mirrors** (L = camo, R = louver vents) | PETG |
| `STL/NOAH_RuggedTrim.stl` | Edge trim (prints as 2 grip strips) | PETG |
| `STL/NOAH_LED_Lens.stl` | LED light pipe | Clear PETG/PLA |
| `STL/NOAH_Bumper_*`, `STL/NOAH_RubberBumpers.stl` | Corner/edge/drop bumpers | **TPU** |
| `STL/NOAH_SolarTabLock_L/R.stl` | Solar panel retainers | PETG |
| `STL/NOAH_FitCoupon_*.stl` | Tolerance test pieces. **Print these first** | any |

## Print settings (starting points)

- PETG: 0.2 mm layers, 4 perimeters, 25 to 40 % infill on structural parts.
- TPU bumpers: 0.2 mm, 2 perimeters, 15 % gyroid, slow.
- The shell prints without supports in its designed orientation; the visor
  face-down for a clean window edge.
- Run the fit coupons and tune horizontal expansion before the big parts:
  magnet pockets and the screen slot are tolerance-critical.

## Editing the source

The `.blend` targets Blender 4/5. The scene is unit-true (mm); part names
match the STL names. If you regenerate STLs, export with selection-only and
global scale 1.0.
