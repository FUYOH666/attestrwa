"""Process settings, read from the environment (and ``.env`` if present)."""

from __future__ import annotations

from functools import lru_cache

from attestrwa.eas import EAS_PREDEPLOY
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Chainalysis sanctions oracle on Base Sepolia. On Base mainnet it lives at
# 0x3A91A31cB3dC49b4db9Ce721F50a9D076c8D739B.
SANCTIONS_ORACLE_BASE_SEPOLIA = "0x40C57923924B5c5c5455c48D93317139ADDaC8fb"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ATTESTRWA_", extra="ignore", populate_by_name=True
    )

    # --- chain ---
    rpc_url: str = "http://127.0.0.1:8545"
    chain_id: int = 84532
    network: str = "anvil-fork"
    eas_address: str = EAS_PREDEPLOY
    escrow_address: str = ""
    sanctions_oracle: str = SANCTIONS_ORACLE_BASE_SEPOLIA

    # --- attester ---
    attester_private_key: str = Field(default="", repr=False)
    attestation_ttl_seconds: int = Field(default=86_400, ge=60)
    receipt_timeout_seconds: int = Field(default=60, ge=5)

    # --- policy inputs ---
    policy_file: str = "data/policies/settlement-demo-v2.yaml"
    registry_file: str = "data/registry/payees.json"
    records_dir: str = "records"

    # --- API ---
    # Comma-separated "name:key" pairs. The name is recorded as the origin of
    # every input the caller declares.
    api_keys: str = Field(default="", repr=False)
    cors_origins: str = ""
    api_version: str = "2.0.0"
    log_level: str = "INFO"

    def api_key_map(self) -> dict[str, str]:
        """Map of API key -> integrator name."""
        result: dict[str, str] = {}
        for pair in self.api_keys.split(","):
            pair = pair.strip()
            if not pair:
                continue
            name, _, key = pair.partition(":")
            if name.strip() and key.strip():
                result[key.strip()] = name.strip()
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()
