import asyncio
from app.db.session import AsyncSessionLocal
from app.models.api_key import APIKey
from app.core.security import generate_raw_api_key, get_api_key_hash

async def create_key():

    raw_key = generate_raw_api_key()

    hashed_key = get_api_key_hash(raw_key)

    async with AsyncSessionLocal() as session:
        new_key = APIKey(
            hashed_key=hashed_key,
            client_name="Syndra_Admin_Test"
        )

        session.add(new_key)
        await session.commit()

    print(f"\n ✓ MASTER KEY CREATED SUCCESSFULLY")
    print(f"==========================================================")
    print(f"CLIENT: {new_key.client_name}")
    print(f"RAW KEY: {raw_key}")
    print(f" -- SAVE THIS KEY IN A SECURE LOCATION. It's only on screen, not stored in DB. --")
    print(f"==========================================================\n")
    

if __name__ == "__main__":
    asyncio.run(create_key())
