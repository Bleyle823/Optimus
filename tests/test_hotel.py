import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hotel.dispatcher import quotes, simulate_skill, settle_outbox, create_claim, _open_claim_for_skill
from hotel.keys import derive
from hotel.agent_market import receipt_markdown
from hotel.config import PEAQ_STATUS, RECEIPTS_DIR, load


class HotelRaaSTests(unittest.TestCase):
    def test_quotes_refuse_courier(self):
        cfg = load()
        q = quotes(cfg)
        self.assertTrue(q["accepted"]["accepted"])
        self.assertFalse(q["refused"]["accepted"])
        self.assertEqual(q["refused"]["account"], cfg["accounts"]["courier"])

    def test_one_key_derivation(self):
        rec = derive("robot")
        self.assertEqual(len(rec["public_key_hex"]), 64)
        self.assertEqual(rec["near_implicit"], rec["public_key_hex"])
        self.assertTrue(rec["solana_address"])
        self.assertTrue(rec["near_public_key"].startswith("ed25519:"))

    def test_offline_m2m_loop(self):
        derive("guest")
        derive("robot")
        derive("pantry")
        derive("courier")
        simulate_skill("fetch_honey")
        created = create_claim("fetch_honey", offline=True)
        self.assertTrue(created["claim_id"].startswith("offline-"))
        receipt = settle_outbox(once=True, offline=True)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["skill_id"], "fetch_honey")
        self.assertTrue(receipt["webots_success"])
        self.assertFalse(receipt["refused_quote"]["accepted"])
        self.assertTrue(receipt.get("solana_address"))
        self.assertTrue(receipt.get("near_implicit"))
        self.assertEqual(receipt["peaq"]["home_chain"], 5)
        self.assertFalse(receipt["peaq"]["submitted"])
        self.assertEqual(receipt["peaq"]["activity"]["trustLevel"], 0)
        self.assertTrue(PEAQ_STATUS.exists())
        peaq_status = json.loads(PEAQ_STATUS.read_text(encoding="utf-8"))
        self.assertEqual(peaq_status["solana_address"], receipt["solana_address"])
        self.assertFalse(peaq_status["live"])
        md = receipt_markdown(receipt)
        self.assertIn(receipt["claim_id"], md)
        self.assertIn("fetch_honey", md)

    def test_open_claim_matches_skill_not_latest_file(self):
        honey = create_claim("fetch_honey", offline=True)
        jam = create_claim("fetch_jam", offline=True)
        claim_id, stored = _open_claim_for_skill("fetch_jam")
        self.assertEqual(claim_id, jam["claim_id"])
        self.assertNotEqual(claim_id, honey["claim_id"])
        self.assertEqual((stored.get("args") or {}).get("skill_id"), "fetch_jam")


if __name__ == "__main__":
    unittest.main()
