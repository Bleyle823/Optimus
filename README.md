# Hotel Robot-as-a-Service on NEAR

Pay-per-skill room service in a Webots kitchen. A guest funds a **NEAR task escrow**. TIAGo fetches a jar. The robot account calls `complete`, then `pay_supplier` so the pantry machine gets the wholesale share. Intents is the USDT exit. peaq on Solana is the machine name and credit file.

Full argument: [docs/hotel-raas.md](docs/hotel-raas.md).

**Tracks:** `agents` (primary), `business`, `realworld`, `swarms`, `open`.

**Open-track primitive:** one NEAR escrow for a machine whose identity lives on another chain, with the robot as both seller and buyer.

**Idea / X post:** Software agents on NEAR already move value across 35+ chains. The next wave of agents will be physical AI (robots). Hotels should pay for the delivery, not the month. The robot should pay the pantry for the jar, not file an invoice.

This repository already contained a working Webots kitchen (`worlds/kitchen.wbt`, controller `mission_control`). That world is the **baseline**. Everything under `contracts/`, `hotel/`, `config/`, and `docs/` is the hackathon settlement layer.

License: [MIT](LICENSE).

## What you will see

| You do | You see |
| --- | --- |
| `python -m hotel.cli derive-key --role robot` | One Ed25519 key, Solana address, NEAR implicit account (same 32-byte pubkey) |
| `python -m hotel.cli quotes` | Pantry path accepted; `courier.testnet` quote refused; reason on a receipt |
| Guest funds a claim (testnet) | `wrap.testnet` balance locked on the escrow; explorer link |
| Open `worlds/kitchen.wbt` with `HOTEL_SKILL=fetch_honey` (or world `controllerArgs`) | TIAGo drives to the counter, grasps and lifts the honey jar; HUD shows the NEAR receipt; `settlement/outbox.json` |
| Dispatcher watches the outbox | Robot `complete` tx, robot balance up |
| Same key `pay_supplier` | Pantry balance up; robot keeps the spread (pantry_bps in config) |
| Print receipt | Claim id, both tx hashes, refused courier quote, Webots success |
| `python -m hotel.cli intents-quote --dry` | 1Click quote toward USDT. No spend |
| `python -m hotel.cli peaq-dry` | `peaqos activate --chain solana --dry-run` (no bond) |

## Requirements

- Webots R2023+ with Python **3.9** for the controller (`controllers/mission_control/runtime.ini` already pins it)
- Python **3.10+** for `hotel/` (NEAR RPC, 1Click, peaq dry-run)
- `pip install -r requirements.txt`
- Optional: Rust + `cargo` to build [`contracts/task_escrow`](contracts/task_escrow)
- Optional: `peaq-os-cli[solana,ows]` **0.0.19+** for the identity dry-run
- Optional: NEAR testnet named accounts (`tiago.testnet`, `pantry.testnet`, `guest.testnet`, `courier.testnet`) and a small `wrap.testnet` balance

Copy `.env.example` to `.env`. Never commit keys. `keys/` is gitignored.

## Run end-to-end (Webots + settlement)

Webots uses Python **3.9** (`controllers/mission_control/runtime.ini`). `hotel/` needs Python **3.10+**. The controller never imports `hotel`; it writes `settlement/outbox.json` and overlays the receipt with `Supervisor.setLabel`.

`worlds/kitchen.wbt` ships TIAGo with `controllerArgs` `fetch_honey`. Settlement mode is `HOTEL_SETTLE` (`offline` default, `live`, or `none`). If the 3.10 binary is not `py -3.10`, set `HOTEL_PYTHON` to that interpreter.

### A. Offline (no testnet; proves drive + HUD)

1. `pip install -r requirements.txt` on Python 3.10+.
2. `python -m hotel.cli derive-key --role robot` (and `pantry`, `guest`, `courier`) if `keys/` is empty.
3. `python -m hotel.cli create-claim --skill fetch_honey --offline`
4. In Webots: **File → Reload World**, then Play. Optional env: `HOTEL_SETTLE=offline`.
5. **See:** TIAGo starts at `(0, 0.25)` (the reference kitchen pose), follows the mapped path, grasps the honey jar, then a HUD: claim id, `complete` / `pay_supplier` `offline`, refused courier quote.

### B. Live NEAR testnet (fill these; do not invent accounts)

Copy `.env.example` to `.env`. Paste values you control:

| Field | Where | What you put |
| --- | --- | --- |
| `NEAR_ESCROW_ACCOUNT` | `.env` and `config/hotel.json` `escrow_account` | Named testnet account that will hold the wasm |
| `NEAR_GUEST_ACCOUNT` / `NEAR_ROBOT_ACCOUNT` / `NEAR_PANTRY_ACCOUNT` / `NEAR_COURIER_ACCOUNT` | `.env` (defaults `guest.testnet`, `tiago.testnet`, `pantry.testnet`, `courier.testnet`) | Accounts you created; full-access keys for guest/robot/pantry |
| `NEAR_FT_CONTRACT` | `.env` | `wrap.testnet` |
| `ROBOT_KEYFILE` / `GUEST_KEYFILE` / `PANTRY_KEYFILE` | `.env` | `keys/robot.json` (and guest/pantry) from `derive-key` |
| wrap.testnet balance | guest account | Enough for `fetch_honey` (`price_yocto` `5e22` in config) |
| wasm | `contracts/task_escrow` | `cargo build --target wasm32-unknown-unknown --release` then `python -m hotel.cli deploy-escrow --wasm ...` and `init-escrow` |
| function-call key | robot | `python -m hotel.cli add-function-call-key` after `escrow_account` is set |

Then:

```bash
python -m hotel.cli create-claim --skill fetch_honey
python -m hotel.cli fund-claim --claim <id>
```

Play with `HOTEL_SKILL=fetch_honey` (or the world `controllerArgs`) and `HOTEL_SETTLE=live`. In another terminal:

```bash
python -m hotel.cli watch --once
```

**See:** HUD claim id, real `complete` / `pay_supplier` hashes, explorer URL. Leave `INTENTS_LIVE=0` and `PEAQ_LIVE=0`. Dry extras: `python -m hotel.cli intents-quote --dry`, `python -m hotel.cli peaq-dry`.

## 1. Derive the one-key model

```bash
python -m hotel.cli derive-key --role robot
python -m hotel.cli derive-key --role pantry
python -m hotel.cli derive-key --role guest
python -m hotel.cli derive-key --role courier
```

Each run prints:

- NEAR implicit account = lowercase hex of the 32-byte public key
- Solana address = base58 of that same public key (robot only: peaq owner)

Create named testnet accounts that add the robot/pantry full-access keys, then add a **function-call key** on the robot:

```bash
python -m hotel.cli add-function-call-key
```

That key may call only `complete` and `pay_supplier` on the escrow. Delete it to kill the controller.

## 2. Deploy the task escrow (NEAR testnet)

```bash
cd contracts/task_escrow
cargo build --target wasm32-unknown-unknown --release
python -m hotel.cli deploy-escrow --wasm target/wasm32-unknown-unknown/release/task_escrow.wasm
python -m hotel.cli init-escrow
```

Paste the contract account into `config/hotel.json` (`escrow_account`) and `.env`. The named account must already exist on testnet with a key you control.

## 3. Fund one skill (do X, see Y)

```bash
python -m hotel.cli create-claim --skill fetch_honey
python -m hotel.cli fund-claim --claim <id>
```

**See:** explorer link for `ft_transfer_call`; claim status `Funded`.

If `procurement.kill_switch` is true in config, both commands refuse to run.

## 4. Run the skill in Webots

The world already passes `controllerArgs` `fetch_honey`. Override with `HOTEL_SKILL` in the controller environment if needed. Open `worlds/kitchen.wbt`, play.

**See:** TIAGo follows the reference kitchen path, grasps `honey jar`, lifts it, writes `settlement/outbox.json`, then overlays claim / tx lines (unless `HOTEL_SETTLE=none`).

Clear `controllerArgs` and leave `HOTEL_SKILL` unset to run the original full tree (baseline).

## 5. Machine-to-machine settlement

```bash
python -m hotel.cli watch --once
```

**See:**

1. Courier quote refused (price in `config/hotel.json` `courier_quote`)
2. `complete` from the robot function-call key → robot FT balance up
3. `pay_supplier` → pantry FT balance up, robot keeps `10000 - pantry_bps` bps
4. `settlement/receipts/<claim>.json`

Offline rehearsal (no RPC, no Webots):

```bash
python -m hotel.cli simulate-skill --skill fetch_honey
python -m hotel.cli create-claim --skill fetch_honey --offline
python -m hotel.cli watch --once --offline
```

## 6. Intents exit (dry, then optional tiny mainnet)

```bash
python -m hotel.cli intents-quote --dry
```

**See:** JSON quote from `https://1click.chaindefuser.com/v0`. There is no Intents testnet.

A live fill requires `INTENTS_LIVE=1` in `.env` **and** a human confirmation prompt. Do not set that for the screening pass. Q-006: without a partner JWT the fee is 0.2%.

## 7. peaq identity (dry-run, then funded only after the video)

```bash
python -m hotel.cli peaq-dry
```

**See:** CLI version check (≥ 0.0.19) and `peaqos activate --chain solana --dry-run` quoting a bond. That quote is a **bond lock**, not the NEAR task escrow.

`--live` spends mainnet SOL/PEAQ. Do not run it until the testnet loop is recorded. Then:

```bash
python -m hotel.cli peaq-event --receipt settlement/receipts/<claim>.json
```

Skill prices in config are under the $10 revenue floor, so this submits an **activity** event only (NEAR hashes in `rawData`, trust level 0).

## 8. Agent Market listing

```bash
export NEAR_AI_API_KEY=...   # never commit
python -m hotel.cli agent-market --poll
```

A hire returns markdown: claim id, NEAR tx, skill id, Webots success. Hiring your own listing does not build reputation.

## Procurement (business track)

[`config/hotel.json`](config/hotel.json):

- `procurement.max_price_yocto` — dispatcher will not create a claim above this
- `procurement.pantry_bps` — wholesale share paid to the pantry (4000 = 40%)
- `procurement.kill_switch` — blocks create/fund/complete from this machine

## Contract methods (task escrow)

| Method | Who | Effect |
| --- | --- | --- |
| `create_claim` | guest | Stores skill, robot pk, pantry, price, deadline |
| `ft_on_transfer` | FT contract via guest `ft_transfer_call` | Funds the claim |
| `complete` | robot (function-call key) | Pays the robot if signer pk matches and deadline is live |
| `pay_supplier` | robot | Sends pantry bps; robot keeps the spread |
| `refund` | anyone after deadline | Returns funds to the guest if not completed |

`complete` plus `pay_supplier` is the release: the robot share leaves first, then the pantry share. The escrow never sends the full price to one account.

## Limits (read before judging)

The robot reports its own success. Intents and peaq events are mainnet-only; the repeatable loop is NEAR testnet. peaq Scale is paused, so dispatch is local. This is one TIAGo in a kitchen, not a live hotel fleet. Details in [docs/hotel-raas.md](docs/hotel-raas.md#honest-limits).

## Demo script (two minutes)

1. Explorer: guest funds `fetch_honey`.
2. Webots: jar leaves the counter.
3. Explorer: robot balance up (`complete`).
4. Explorer: pantry balance up (`pay_supplier`); robot holds the spread.
5. Receipt: refused courier quote + Webots hash.
6. Optional: 1Click dry quote; peaq `--dry-run`.
