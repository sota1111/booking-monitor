import os

import uvicorn

from booking_monitor.web import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
