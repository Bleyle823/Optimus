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
| Open `worlds/kitchen.wbt` with `HOTEL_SKILL=fetch_honey` | TIAGo searches, grasps, lifts the honey jar; writes `settlement/outbox.json` |
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

Set `HOTEL_SKILL=fetch_honey` in the controller environment (Webots: robot `controllerArgs` or a shell env before launching Webots). Open `worlds/kitchen.wbt`, play.

**See:** TIAGo maps if needed, routes to the counter, grasps `honey jar`, lifts it, then writes `settlement/outbox.json` with GPS, compass, skill id, and a telemetry hash.

Leave `HOTEL_SKILL` unset to run the original full tree (baseline).

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
