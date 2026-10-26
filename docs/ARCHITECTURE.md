# Architecture

Three phases: **Setup (online)**, **Operation (offline LAN)**, **Settlement (online)**.

See the root README and `.cursor/plans/optimus_hackathon_build_791d7123.plan.md` for sequence diagrams.

Offline path: Webots `optimus_robot` → machine-agent → gateway → QVAC. No peaq/RPC/WDK broadcast on that path.
