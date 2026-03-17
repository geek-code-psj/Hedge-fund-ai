// frontend/app/api/analyse/route.ts
// SSE proxy route — forwards requests to FastAPI backend and streams the response.
// This avoids CORS issues when the frontend and backend are on different domains.

import { NextRequest } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";
export const runtime = "edge"; // Edge runtime for true streaming

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const ticker = searchParams.get("ticker") ?? "";
  const query = searchParams.get("query") ?? "Provide a comprehensive investment analysis.";
  const sessionId = searchParams.get("session_id");

  const params = new URLSearchParams({ ticker, query });
  if (sessionId) params.set("session_id", sessionId);

  const backendUrl = `${BACKEND}/api/v1/analyse?${params}`;

  const backendRes = await fetch(backendUrl, {
    headers: {
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    },
  });

  if (!backendRes.ok) {
    return new Response(
      `event: error\ndata: {"message":"Backend error ${backendRes.status}"}\n\n`,
      {
        status: backendRes.status,
        headers: { "Content-Type": "text/event-stream" },
      }
    );
  }

  // Pass the SSE stream through transparently
  return new Response(backendRes.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
      "Connection": "keep-alive",
    },
  });
}
