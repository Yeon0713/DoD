"""도나 v0.2.0 백엔드 목업을 켠다. 주소: http://localhost:8100"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8100")), reload=False)
