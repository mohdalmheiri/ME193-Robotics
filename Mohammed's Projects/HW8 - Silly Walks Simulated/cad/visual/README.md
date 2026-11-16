# LEGO-looking parts (pictures only)

These meshes are for **pictures only** (Notion cover, slides). **The simulation does not use them:** `cad/robot.xml`, `sim/`, `train/` and `robot/` never read this folder.

## Where they come from

| File(s) | LDraw part | Author | License |
|---|---|---|---|
| `double_motor.stl`, `double_motor_<colour>.stl` | **118091p01**, Electric Bluetooth Double Motor with Dark Turquoise Bottom and Drive Hub (*unofficial* part, [library.ldraw.org/parts/47735](https://library.ldraw.org/parts/47735)) | Philippe Hurbain [Philo] | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `technic_brick_1x8_leg.stl` | **3702**, Technic Brick 1 x 8 with Holes (official part) | James Jessiman | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |

- **Other authors:** the subparts and primitives they use come from the LDraw library (library.ldraw.org), also CC BY 4.0, by their respective authors. Every file used, with its download address, is listed in `ldraw_sources.txt`, and each file's header names its author.
- **Converted** to STL by `ldraw_to_stl.py` (this folder). Its downloads are cached in `ldraw_cache/`, which git ignores.
- **Attribution for pictures:** "LEGO motor and brick models from the LDraw library (library.ldraw.org), CC BY 4.0: Double Motor by Philippe Hurbain, Technic brick by James Jessiman." LEGO® is a trademark of the LEGO Group, which does not sponsor or endorse this project.

## Units and axes

All files are in **millimetres** (LDraw: 1 LDU = 0.4 mm). They are already in **our robot's axes**, the same as `cad/robot.xml`:
- **x** = robot's right
- **y** = front (walking direction)
- **z** = up

Origins are chosen so that no rotating is needed:

| File | Origin and placement | Size |
|---|---|---|
| `double_motor.stl` | the middle of the motor axle, halfway between the two hub centres. The body sticks out behind the axle (−y), as on our robot | 64 × 80 × 30.4 mm (x −32…32, y −64…16, z −15.2…15.2) |
| `technic_brick_1x8_leg.stl` | **the centre of the 2nd hole** (the pivot). Hole axis along x, long arm pointing forward (+y, 48 mm), short arm behind (16 mm), studs up, centred on x = 0 | 8 mm thick (x ±4) |

**Hubs:** radius 11.6 mm. Their outer faces are at **x = ±32.0 mm**, the same as our CAD (hub faces at ±32 mm).

**Colour pieces:** the same motor split by LDraw colour, so each can get its own appearance:

| File | Colour | Hex |
|---|---|---|
| `double_motor_main.stl` | top body: LDraw "main colour"; the real motor is white | `#F2F2F2` |
| `double_motor_dark_turquoise.stl` | bottom | `#069D9F` |
| `double_motor_black.stl` | | `#1B2A34` |
| `double_motor_light_bluish_grey.stl` | | `#969696` |
| `double_motor_metallic_silver.stl` | | `#767676` |
| `double_motor_trans_medium_blue.stl` | the light window, transparent | `#559AB7` |

Use either the single `double_motor.stl` (one colour) or all six colour files together, not both.

**Differences from the simulated robot** (`cad/robot.xml`):
- The brick is 8.0 mm thick (CAD leg 7.8 mm).
- The LEGO hubs are 23.2 mm across (CAD 25 mm).
- The brick's hole sits 1.6 mm above the brick's middle.

None of this matters for pictures.

## Onshape: a NEW Part Studio and a NEW assembly

I could not test these steps in Onshape from here. They are the standard import route. If a feature is greyed out for mesh parts, use the fallback given.

**1. Import the STLs** (each one becomes its own tab):
- In the Onshape document, click **+** (bottom left) → **Import…**, then select `double_motor_*.stl` (the six colour files) and `technic_brick_1x8_leg.stl`.
- **Units: Millimeter.** STL files carry no units; with the wrong units the motor turns out 1000× too big.
- **Leave "Y axis is up" unticked.** These files are already Z-up.
- Each STL becomes a tab containing one **mesh part**.

**2. Create the new Part Studio:**
- **+** → **Create Part Studio**, and rename it `LEGO visual` (leave the robot's existing Part Studio alone).
- Bring in each imported part with **Derived** (toolbar → *Derived*, pick the import tab, select its part). Derived keeps each part's own origin, so the motor lands exactly on the origin with its axle along x.

**3. Place the two legs:** in `LEGO visual`, derive `technic_brick_1x8_leg` **twice**, then use **Transform → Translate by XYZ** on each:
- **Right leg:** X = **+36 mm**, Y = 0, Z = 0. That puts it on the right hub's outer face: the face is at 32 mm, plus half the brick's 8 mm.
- **Left leg:** X = **−36 mm**, Y = 0, Z = 0.
- **Pivot = the 2nd hole:** this is built into the leg file. Its origin is the centre of the 2nd hole, so after the move each leg turns about the motor axle through its 2nd hole, as on our robot.
- **Optional pose for the picture:** **Transform → Rotate** a leg about a line through (±36, 0, 0) along X. 0° = long arm forward, flat; +90° = long arm straight up. The left leg a quarter turn ahead of the right gives the "legs out of step" gait.
- **Appearance:** right-click each part → **Edit appearance**, and use the hex colours above. For the legs, a LEGO colour of your choice, e.g. red `#C91A09`.

**4. Create the new assembly:**
- **+** → **Create Assembly**, and rename it `LEGO visual assembly`. Leave Assembly 1 alone.
- **Insert** → choose the `LEGO visual` Part Studio → insert it **as a whole Part Studio** (one rigid group). Click the origin to place it, then right-click → **Fix**.
- **Rendering:** use **Render Studio** (or a screenshot with a white background) for the Notion cover.

**Fallback, if you want legs that can turn in the assembly instead of fixed in the Part Studio:**
- Insert the motor parts and the leg part separately.
- In the Part Studio, add a **Mate connector** at each part's **origin** (Owner part = that mesh part). For the motor, rotate its primary axis to X, so it lies along the axle.
- In the assembly, use a **Revolute mate** between the motor's connector, offset ±36 mm along X, and each leg's origin connector. Each leg then spins about its 2nd hole on the hub.
- If Onshape won't put a mate connector on a mesh part, keep the Part Studio placement from step 3 and just **Fix** the parts in the assembly.

## Remaking the files

From the HW8 folder:

```bash
../../.venv/bin/python cad/visual/ldraw_to_stl.py
```

- It downloads about 145 small files the first time. It pauses when the LDraw library asks it to slow down, so this takes a few minutes.
- Check the printed numbers: positive volume, hub faces at ±32.0 mm.
