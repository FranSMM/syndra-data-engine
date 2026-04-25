"""
CLI to provision B2B API Keys for Syndra.

Usage:
  Permanent key:   python -m app.scripts.provision_client "Client_Name"
  Trial key (7d):  python -m app.scripts.provision_client "Client_Name" --trial 7
"""
import asyncio
import argparse
from datetime import datetime, timedelta, timezone

from app.db.session import AsyncSessionLocal
from app.models.api_key import APIKey
from app.core.security import generate_raw_api_key, get_api_key_hash


async def provision(client_name: str, trial_days: int | None = None) -> None:

    raw_key = generate_raw_api_key()
    hashed_key = get_api_key_hash(raw_key)

    expires_at = None
    if trial_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=trial_days)

    async with AsyncSessionLocal() as session:
        new_key = APIKey(
            hashed_key=hashed_key,
            client_name=client_name,
            expires_at=expires_at,
        )
        session.add(new_key)
        await session.commit()

    key_type = "TRIAL" if expires_at else "PERMANENT"
    print(f"\n ✓ {key_type} API KEY CREATED SUCCESSFULLY")
    print(f"==========================================================")
    print(f"CLIENT:     {client_name}")
    print(f"RAW KEY:    {raw_key}")
    print(f"TYPE:       {key_type}")
    if expires_at:
        print(f"EXPIRES AT: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f" -- This key will NOT be shown again. Store it securely. --")
    print(f"==========================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Provision a new B2B API Key for Syndra."
    )
    parser.add_argument(
        "client_name",
        type=str,
        help="Client identifier (e.g. 'Goldman_Sachs')",
    )
    parser.add_argument(
        "--trial",
        type=int,
        default=None,
        metavar="DAYS",
        help="Create a trial key that auto-expires after N days (e.g. --trial 7).",
    )
    args = parser.parse_args()
    asyncio.run(provision(args.client_name, args.trial))
