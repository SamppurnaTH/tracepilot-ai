# TracePilot AI: frontend

A Next.js page that shows an investigation as it happens: the flight log of every check the agent runs, its hypotheses being confirmed or rejected, the test gauge going from failing to passing, the patch, and the final findings.

It has two modes:

- **Replay** (always available): plays real recorded runs from `public/recordings/`. A static deploy with no backend works this way.
- **Live**: when the backend is reachable at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`), the page can start new investigations and stream their events.

```bash
npm install
npm run dev                                          # http://localhost:3000
NEXT_PUBLIC_API_URL=https://your-backend npm run build
```

To refresh the recordings from the latest verified runs in `runs/`:

```bash
.venv/Scripts/python backend/scripts/export_recordings.py   # from the repo root
```
