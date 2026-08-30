# Nityam — landing page

The public marketing site: hero, the problem Nityam solves, how it works, who
it's for, and a waitlist form. Next.js (App Router), deployed to Vercel as
`nityam-landing`. Not the product itself — see `../backend/` and
`../frontend/` for that.

## Structure

Single-page composition in `app/page.tsx`, built from the sections in
`app/components/`: `Header`, `Hero`, `ProblemStats`, `HowItWorks`,
`AudienceSplit`, `Beliefs`, `Mission`, `Waitlist`, `Footer`.

`app/lib/config.ts` exports `APP_URL` — where the "Sign in" / "Start
learning" CTAs point. Defaults to `http://localhost:5173` (the frontend dev
server); set via `NEXT_PUBLIC_APP_URL` in production.

## Running it

```bash
npm install
npm run dev       # http://localhost:3000
```

Or as part of the full stack — `cd ../backend && ./run.sh` starts this
alongside the backend, frontend, and Observatory (see `backend/run.sh`'s own
header comment for the `--no-landing` flag and port layout).

## Deploying

Linked to Vercel project `nityam-landing` (`.vercel/project.json`). Push to
the connected branch, or `vercel deploy` from this directory.
