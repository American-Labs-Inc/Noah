# Assembly notes

The enclosure is a printed clamshell: main shell, front plate, screen visor,
base plate, two side plates, and TPU bumpers. Fit is based on magnets and rails,
with no glue on the main joints.

## Before printing everything

Print the **fit coupons first** (`3d-models/STL/NOAH_FitCoupon_*.stl`):
screen, keyboard, magnet and rail coupons. They are small test pieces that
verify your printer's tolerances against the real hardware before you spend
a spool on the shell. Adjust horizontal expansion until the coupons fit
snugly.

## Order of assembly

1. **Dry-fit the electronics** outside the shell first: wire the panel per
   [wiring.md](wiring.md), boot, and confirm the display works. Debugging
   through an assembled shell is misery.
2. **Screen + visor**: the panel sits in the front opening, held by
   `NOAH_ScreenRetainer.stl`; the visor (`NOAH_Visor.stl`) carries the
   window and clicks onto the shell with the 7 magnets (pockets in both
   parts: glue the magnets with CA, mind the polarity, and check twice before
   the glue sets).
3. **Jetson + driver board** mount inside the main shell (`NOAH_Shell.stl`)
   on the printed rails/bosses. The IT8951 driver board sits behind the
   panel; keep the panel FPC gentle, with no sharp folds.
4. **Keyboard bay**: the BB Q10 module drops into the keyboard bay in the
   front plate (`NOAH_FrontPlate.stl`). It is wireless, so only its charging
   lead needs routing.
5. **Button + LEDs**: the momentary button mounts in its shell hole and wires
   to the J14 header; the two LEDs sit behind `NOAH_LED_Lens.stl`.
6. **Side plates** (`NOAH_SidePlate_L/R.stl`). Note that they are DIFFERENT
   designs, not mirrors: the left is the camo plate, and the right carries the
   louver vents. They close the sides after the harness is in.
7. **Base plate** (`NOAH_BasePlate.stl`) closes the bottom.
8. **Bumpers**: TPU corner/edge bumpers (`STL/NOAH_Bumper_*.stl`) press
   onto the shell. Print them last. They hide the
   layer seams and take the drops.
9. *(Optional)* **Solar**: thin panel into the back recess, held by
   `NOAH_SolarTabLock_L/R.stl`.

## Shell print variants

`Shell_Cuts/` contains the shell pre-cut for smaller printers: vertical
halves (`ShellV_*`), horizontal halves (`ShellH_*`), or quarters
(`ShellQ_*`). Pick ONE scheme; the cuts have alignment features. On a
300 mm-class bed, print `NOAH_Shell.stl` whole.

## The cable rule

Whatever harness you build: label the known-good power cable, and keep the
20 V warning from [wiring.md](wiring.md) taped to the battery.
