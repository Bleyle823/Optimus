# Webots changes

- **Webots version:** R2025a (`#VRML_SIM R2025a` in [worlds/pick_and_place.wbt](../worlds/pick_and_place.wbt))
- **Robot:** KUKA Youbot pick-and-place benchmark
- **Unchanged:** [controllers/pick_and_place/pick_and_place.py](../controllers/pick_and_place/pick_and_place.py)
- **Added:** [controllers/optimus_robot/optimus_robot.py](../controllers/optimus_robot/optimus_robot.py) — same motion sequence with telemetry/decision hook

**Signals:** joint positions from arm sensors (real). `tempC`, `motorTempC`, `vibrationMmS` are **synthetic** (documented in README).

To demo: set the Youbot controller to `optimus_robot` in the world file or Webots UI.

**Logo:** `DEF LOGO` on the factory machine uses [worlds/textures/factory_logo.png](../worlds/textures/factory_logo.png) instead of the sample `webots://` ladybug texture. The PNG background is transparent. The plane size is `1.16 0.25`; translation is `-0.76 0.138 0.79`.

## Asset path (dark scene)

[worlds/pick_and_place.wbt](../worlds/pick_and_place.wbt) is the R2025a template and was not rewritten. It loads the Youbot, factory, floor, and textures through `webots://` URLs, which resolve only under `C:\Program Files\Webots\projects`. That install shipped without the project protos, so Webots skipped `Youbot`, `TexturedBackground`, `Floor`, and the factory nodes and the view stayed black.

The full assets are in `webots-master\projects`. Each missing `protos` folder (and `default\worlds` textures, meshes, and sounds, plus the pick-and-place world textures) is a directory junction from the install path to that tree. With those links in place, the Optimus world shows the factory sky, concrete floor, conveyor, and orange Youbot from the world's viewpoint (`exposure 1.5`). Creating the junctions needs an elevated shell; `mklink /J` into Program Files is denied otherwise.
