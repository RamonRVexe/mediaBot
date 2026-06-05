from telethon import TelegramClient

from config import API_ID, API_HASH

client = TelegramClient(
    "user_session",
    API_ID,
    API_HASH
)


async def main():
    await client.start()
    print("✅ Cuenta conectada")

    me = await client.get_me()
    print(me.username)

    await client.disconnect()


with client:
    client.loop.run_until_complete(main())
