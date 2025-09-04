# video-upload-portal-130107-130116

This workspace contains the `video_upload_backend` FastAPI service that accepts video uploads with a maximum size of 500MB and stores them in the `./upload` directory relative to the service root.

How to run locally:
- Install dependencies:
  - `pip install -r video_upload_backend/requirements.txt`
- Start the server:
  - `uvicorn video_upload_backend.src.api.main:app --host 0.0.0.0 --port 3001`
- Open API docs:
  - Navigate to `http://localhost:3001/docs`

Endpoints:
- GET `/` Health check
- POST `/upload` Multipart upload field name: `file`