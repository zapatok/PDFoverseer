import asyncio
import websockets

async def test_ws():
    uri = "ws://127.0.0.1:8000/ws?session_id=1234"
    try:
        print("Connecting with Origin...")
        async with websockets.connect(uri, origin="http://localhost:5173") as websocket:
            print("Connected!")
            await websocket.send("Hello")
            print("Sent hello.")
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
