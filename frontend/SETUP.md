# Frontend Setup — Hedge Fund AI

This guide covers scaffolding the project from scratch if you're not using the bundled codebase.

---

## 1. Create the Next.js + shadcn/ui project

```bash
# Scaffold Next.js 15 with TypeScript + Tailwind + App Router
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir=false \
  --import-alias "@/*"

cd frontend

# Initialise shadcn/ui (creates components.json, sets up /components/ui)
npx shadcn@latest init
```

When shadcn asks:
- **Style**: Default
- **Base color**: Zinc  
- **CSS variables**: Yes

This creates the `/components/ui` folder. **This folder is required** — shadcn components are copied here via the CLI and imported with `@/components/ui/...`. Putting them anywhere else breaks the import aliases.

---

## 2. Install npm dependencies

```bash
# Core animation library (required for ContainerScroll)
npm install framer-motion

# Icons (used throughout the dashboard)
npm install lucide-react

# Charts (TechnicalCharts component)
npm install recharts

# Already installed by shadcn init, but verify:
npm install clsx tailwind-merge class-variance-authority
npm install tailwindcss-animate
```

---

## 3. Add shadcn components

```bash
npx shadcn@latest add tabs
npx shadcn@latest add scroll-area
npx shadcn@latest add tooltip
npx shadcn@latest add progress
npx shadcn@latest add separator
npx shadcn@latest add badge
```

---

## 4. Copy custom UI component

Copy `components/ui/container-scroll-animation.tsx` to your project's `/components/ui/` folder.

This component requires:
- `framer-motion` (installed above)
- Next.js `"use client"` directive (included)
- The component uses `useScroll`, `useTransform`, `motion` from framer-motion

---

## 5. Add fonts to `app/layout.tsx`

```tsx
import { Space_Mono, Syne } from "next/font/google";

const syne = Syne({ subsets: ["latin"], variable: "--font-display", weight: ["400","700","800"] });
const mono = Space_Mono({ subsets: ["latin"], variable: "--font-mono", weight: ["400","700"] });
```

---

## 6. Environment variables

```bash
cp .env.local.example .env.local
# Set NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 7. Run

```bash
npm run dev        # http://localhost:3000
```

---

## Why `/components/ui` matters

shadcn/ui is **not** a traditional npm package — components are copied directly into your project at `components/ui/`. The shadcn CLI, the `components.json` config, and all import paths in the codebase (`@/components/ui/...`) assume this exact path. Moving it breaks:

- The shadcn CLI (`npx shadcn add ...`)
- All existing component imports
- The TypeScript path alias resolution

Always use `/components/ui` as the shadcn component directory.
