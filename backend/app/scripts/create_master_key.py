import asyncio
import argparse
from app.db.session import AsyncSessionLocal
from app.models.api_key import APIKey
from app.core.security import generate_raw_api_key, get_api_key_hash

async def create_key(client_name: str):

    raw_key = generate_raw_api_key()

    hashed_key = get_api_key_hash(raw_key)

    async with AsyncSessionLocal() as session:
        new_key = APIKey(
            hashed_key=hashed_key,
            client_name=client_name
        )

        session.add(new_key)
        await session.commit()

    print(f"\n ✓ API KEY CREATED SUCCESSFULLY")
    print(f"==========================================================")
    print(f"CLIENT: {new_key.client_name}")
    print(f"RAW KEY: {raw_key}")
    print(f" -- This key will NOT be shown again. Store it securely. --")
    print(f"==========================================================\n")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provision a new B2B API Key for Syndra.")
    parser.add_argument(
        "client_name",
        type=str,
        help="Client name (e.g. 'Goldman_Sachs')"
    )
    args = parser.parse_args()
    asyncio.run(create_key(args.client_name))
