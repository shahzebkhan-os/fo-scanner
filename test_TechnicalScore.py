import asyncio
from backend.main import score_technical_endpoint

async def run():
    try:
        res = await score_technical_endpoint("NIFTY")
        print("Success:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(run())
