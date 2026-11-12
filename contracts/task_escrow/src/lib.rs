use near_sdk::borsh::{self, BorshDeserialize, BorshSerialize};
use near_sdk::collections::UnorderedMap;
use near_sdk::json_types::U128;
use near_sdk::serde::{Deserialize, Serialize};
use near_sdk::{
    env, ext_contract, log, near_bindgen, require, AccountId, BorshStorageKey, Gas, PanicOnDefault,
    Promise, PromiseOrValue, PublicKey,
};

const GAS_FOR_FT_TRANSFER: Gas = 10_000_000_000_000;
const YOCTO_1: u128 = 1;

#[derive(BorshDeserialize, BorshSerialize, Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
#[serde(crate = "near_sdk::serde")]
pub enum ClaimStatus {
    Created,
    Funded,
    Completed,
    SupplierPaid,
    Refunded,
}

#[derive(BorshDeserialize, BorshSerialize, Serialize, Deserialize, Clone)]
#[serde(crate = "near_sdk::serde")]
pub struct Claim {
    pub guest: AccountId,
    pub robot: AccountId,
    pub robot_pk: PublicKey,
    pub pantry: AccountId,
    pub skill_id: String,
    pub price: U128,
    pub pantry_bps: u16,
    pub deadline_ms: u64,
    pub token: AccountId,
    pub status: ClaimStatus,
    pub telemetry_hash: Option<String>,
    pub refused_quote: Option<String>,
}

#[derive(BorshStorageKey, BorshSerialize)]
enum Keys {
    Claims,
}

#[ext_contract(ext_ft)]
trait FungibleToken {
    fn ft_transfer(&mut self, receiver_id: AccountId, amount: U128, memo: Option<String>);
}

#[near_bindgen]
#[derive(BorshDeserialize, BorshSerialize, PanicOnDefault)]
pub struct Contract {
    pub owner: AccountId,
    pub claims: UnorderedMap<String, Claim>,
    pub next_id: u64,
}

fn now_ms() -> u64 {
    env::block_timestamp() / 1_000_000
}

#[near_bindgen]
impl Contract {
    #[init]
    pub fn new(owner: Option<AccountId>) -> Self {
        Self {
            owner: owner.unwrap_or_else(env::predecessor_account_id),
            claims: UnorderedMap::new(Keys::Claims),
            next_id: 1,
        }
    }

    pub fn get_claim(&self, claim_id: String) -> Option<Claim> {
        self.claims.get(&claim_id)
    }

    pub fn create_claim(
        &mut self,
        robot: AccountId,
        robot_pk: PublicKey,
        pantry: AccountId,
        skill_id: String,
        price: U128,
        pantry_bps: u16,
        deadline_ms: u64,
        token: AccountId,
        refused_quote: Option<String>,
    ) -> String {
        require!(pantry_bps <= 10_000, "pantry_bps must be <= 10000");
        require!(!skill_id.is_empty(), "skill_id required");
        require!(price.0 > 0, "price required");
        require!(deadline_ms > now_ms(), "deadline must be in the future");

        let id = format!("claim-{}", self.next_id);
        self.next_id += 1;

        let claim = Claim {
            guest: env::predecessor_account_id(),
            robot,
            robot_pk,
            pantry,
            skill_id,
            price,
            pantry_bps,
            deadline_ms,
            token,
            status: ClaimStatus::Created,
            telemetry_hash: None,
            refused_quote,
        };
        self.claims.insert(&id, &claim);
        log!("created {}", id);
        id
    }

    /// NEP-141 `ft_transfer_call` hook. `msg` is the claim id.
    pub fn ft_on_transfer(
        &mut self,
        sender_id: AccountId,
        amount: U128,
        msg: String,
    ) -> PromiseOrValue<U128> {
        let token = env::predecessor_account_id();
        let mut claim = self
            .claims
            .get(&msg)
            .unwrap_or_else(|| env::panic_str("unknown claim"));
        require!(
            matches!(claim.status, ClaimStatus::Created),
            "claim not awaiting funds"
        );
        require!(claim.guest == sender_id, "only guest can fund");
        require!(claim.token == token, "wrong token");
        require!(amount.0 == claim.price.0, "amount must equal price");
        claim.status = ClaimStatus::Funded;
        self.claims.insert(&msg, &claim);
        log!("funded {}", msg);
        PromiseOrValue::Value(U128(0))
    }

    pub fn complete(&mut self, claim_id: String, telemetry_hash: Option<String>) -> Promise {
        let predecessor = env::predecessor_account_id();
        let signer_pk = env::signer_account_pk();
        let now = now_ms();

        let mut claim = self
            .claims
            .get(&claim_id)
            .unwrap_or_else(|| env::panic_str("unknown claim"));
        require!(
            matches!(claim.status, ClaimStatus::Funded),
            "claim not funded"
        );
        require!(now <= claim.deadline_ms, "deadline passed");
        require!(predecessor == claim.robot, "only the robot account");
        require!(signer_pk == claim.robot_pk, "signer pk mismatch");
        let pantry_share = claim.price.0.saturating_mul(claim.pantry_bps as u128) / 10_000;
        let robot_share = claim.price.0.saturating_sub(pantry_share);
        require!(robot_share > 0, "robot share is zero");
        claim.status = ClaimStatus::Completed;
        claim.telemetry_hash = telemetry_hash;
        let robot = claim.robot.clone();
        let token = claim.token.clone();
        self.claims.insert(&claim_id, &claim);

        log!("complete {} robot_share {}", claim_id, robot_share);
        ext_ft::ft_transfer(
            robot,
            U128(robot_share),
            Some(format!("complete:{}", claim_id)),
            token,
            YOCTO_1,
            GAS_FOR_FT_TRANSFER,
        )
    }

    pub fn pay_supplier(&mut self, claim_id: String) -> Promise {
        let predecessor = env::predecessor_account_id();
        let signer_pk = env::signer_account_pk();

        let mut claim = self
            .claims
            .get(&claim_id)
            .unwrap_or_else(|| env::panic_str("unknown claim"));
        require!(
            matches!(claim.status, ClaimStatus::Completed),
            "complete first"
        );
        require!(predecessor == claim.robot, "only the robot account");
        require!(signer_pk == claim.robot_pk, "signer pk mismatch");
        let share = claim.price.0.saturating_mul(claim.pantry_bps as u128) / 10_000;
        require!(share > 0, "pantry share is zero");
        claim.status = ClaimStatus::SupplierPaid;
        let pantry = claim.pantry.clone();
        let token = claim.token.clone();
        self.claims.insert(&claim_id, &claim);

        log!("pay_supplier {} share {}", claim_id, share);
        ext_ft::ft_transfer(
            pantry,
            U128(share),
            Some(format!("supplier:{}", claim_id)),
            token,
            YOCTO_1,
            GAS_FOR_FT_TRANSFER,
        )
    }

    pub fn refund(&mut self, claim_id: String) -> Promise {
        let now = now_ms();
        let mut claim = self
            .claims
            .get(&claim_id)
            .unwrap_or_else(|| env::panic_str("unknown claim"));
        require!(
            matches!(claim.status, ClaimStatus::Created | ClaimStatus::Funded),
            "not refundable"
        );
        if matches!(claim.status, ClaimStatus::Funded) {
            require!(now > claim.deadline_ms, "deadline not reached");
        } else {
            require!(
                env::predecessor_account_id() == claim.guest,
                "only guest cancels unfunded"
            );
        }
        require!(
            matches!(claim.status, ClaimStatus::Funded),
            "nothing to refund"
        );
        let price = claim.price.0;
        claim.status = ClaimStatus::Refunded;
        let guest = claim.guest.clone();
        let token = claim.token.clone();
        self.claims.insert(&claim_id, &claim);

        log!("refund {}", claim_id);
        ext_ft::ft_transfer(
            guest,
            U128(price),
            Some(format!("refund:{}", claim_id)),
            token,
            YOCTO_1,
            GAS_FOR_FT_TRANSFER,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use near_sdk::test_utils::{accounts, VMContextBuilder};
    use near_sdk::{testing_env, PublicKey};
    use std::str::FromStr;

    fn pk() -> PublicKey {
        PublicKey::from_str("ed25519:FtAVMi39s3hktJbRCsG2YU4VPM74EJEUe74W68JjFJhA").unwrap()
    }

    fn context(predecessor: AccountId) -> VMContextBuilder {
        let mut b = VMContextBuilder::new();
        b.predecessor_account_id(predecessor)
            .block_timestamp(1_000_000_000_000_000);
        b
    }

    #[test]
    fn create_then_fund_then_complete_then_supplier() {
        let mut c = Contract::new(Some(accounts(0)));
        testing_env!(context(accounts(1)).signer_account_pk(pk()).build());
        let id = c.create_claim(
            accounts(2),
            pk(),
            accounts(3),
            "fetch_honey".into(),
            U128(100),
            4000,
            2_000_000_000,
            accounts(4),
            Some("courier:80".into()),
        );
        testing_env!(context(accounts(4)).build());
        let unused = c.ft_on_transfer(accounts(1), U128(100), id.clone());
        match unused {
            PromiseOrValue::Value(v) => assert_eq!(v.0, 0),
            _ => panic!("expected leftover 0"),
        }
        testing_env!(context(accounts(2)).signer_account_pk(pk()).build());
        let _ = c.complete(id.clone(), Some("abc".into()));
        let claim = c.get_claim(id.clone()).unwrap();
        assert_eq!(claim.status, ClaimStatus::Completed);
        let _ = c.pay_supplier(id.clone());
        let claim = c.get_claim(id).unwrap();
        assert_eq!(claim.status, ClaimStatus::SupplierPaid);
        assert_eq!(claim.refused_quote.as_deref(), Some("courier:80"));
    }

    #[test]
    #[should_panic(expected = "signer pk mismatch")]
    fn complete_rejects_wrong_pk() {
        let mut c = Contract::new(Some(accounts(0)));
        testing_env!(context(accounts(1)).signer_account_pk(pk()).build());
        let id = c.create_claim(
            accounts(2),
            pk(),
            accounts(3),
            "fetch_honey".into(),
            U128(100),
            4000,
            2_000_000_000,
            accounts(4),
            None,
        );
        testing_env!(context(accounts(4)).build());
        let _ = c.ft_on_transfer(accounts(1), U128(100), id.clone());
        let other =
            PublicKey::from_str("ed25519:CbrHgW72Ng5Hav1MLhCnVPwknosDnw3F9wTBVJnG3n8C").unwrap();
        testing_env!(context(accounts(2)).signer_account_pk(other).build());
        let _ = c.complete(id, None);
    }
}
