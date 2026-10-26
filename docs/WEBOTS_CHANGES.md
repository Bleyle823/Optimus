# Webots changes

- **Webots version:** R2025a (`#VRML_SIM R2025a` in [worlds/pick_and_place.wbt](../worlds/pick_and_place.wbt))
- **Robot:** KUKA Youbot pick-and-place benchmark
- **Unchanged:** [controllers/pick_and_place/pick_and_place.py](../controllers/pick_and_place/pick_and_place.py)
- **Added:** [controllers/optimus_robot/optimus_robot.py](../controllers/optimus_robot/optimus_robot.py) — same motion sequence with telemetry/decision hook

**Signals:** joint positions from arm sensors (real). `tempC`, `motorTempC`, `vibrationMmS` are **synthetic** (documented in README).

To demo: set the Youbot controller to `optimus_robot` in the world file or Webots UI.
