# AmCAT4 Frontend

React-based web interface for the AmCAT text analysis platform.

## Tech Stack

- **React 19** + **TypeScript** — UI framework
- **Vite** — dev server and bundler
- **TanStack Router** — file-based routing (routes auto-generated into `routeTree.gen.ts`)
- **TanStack Query** — server state and data fetching
- **Axios** — HTTP client for API calls
- **React Hook Form** + **Zod** — form handling and validation
- **Radix UI** + **Tailwind CSS** — accessible UI primitives and styling
- **pnpm** — package manager

## Project Structure

```
src/
├── routes/       # TanStack Router pages (file-based, mirrors URL structure)
├── components/   # Feature-organized UI components
├── api/          # Axios API client functions (one file per resource)
├── lib/          # Shared utilities
├── interfaces.ts # Shared TypeScript types
└── schemas.ts    # Zod validation schemas
```

## Development

```bash
pnpm install
pnpm dev          # Start dev server (proxies /api/* to backend on :5000)
pnpm build        # Production build
pnpm lint         # ESLint
```

Requires the backend running on port 5000. See the root `docker-compose.yml` or `backend/README.md`.

## Linting & Formatting

```bash
pnpm lint                  # ESLint
npx prettier --write .     # Format with Prettier (+ tailwindcss plugin)
```

Configuration is in `eslint.config.js`, `tailwind.config.js`, and `tsconfig.json`.
