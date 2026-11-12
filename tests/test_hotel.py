import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hotel.dispatcher import quotes, simulate_skill, settle_outbox, create_claim
from hotel.keys import derive
from hotel.agent_market import receipt_markdown
from hotel.config import RECEIPTS_DIR, load


class HotelRaaSTests(unittest.TestCase):
    def test_quotes_refuse_courier(self):
        q = quotes(load())
        self.assertTrue(q["accepted"]["accepted"])
        self.assertFalse(q["refused"]["accepted"])
        self.assertIn("courier", q["refused"]["account"])

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
        md = receipt_markdown(receipt)
        self.assertIn(receipt["claim_id"], md)
        self.assertIn("fetch_honey", md)


if __name__ == "__main__":
    unittest.main()
