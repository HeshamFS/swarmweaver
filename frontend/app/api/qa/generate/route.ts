import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

/**
 * Next.js API route that proxies QA generation to the backend.
 *
 * The default Next.js rewrite proxy drops connections for slow responses.
 * The SDK warm pool typically responds in 2-5s, but the first call or
 * fallback path may take longer. This route takes priority over the rewrite rule.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90_000); // 90s — SDK warm pool is 2-5s, but first call can take 60s+

    const res = await fetch(`${BACKEND_URL}/api/qa/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    clearTimeout(timeout);

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return NextResponse.json(
        { questions: [], skip_reason: "Q&A generation timed out. Proceeding directly." },
        { status: 200 }
      );
    }
    // Connection refused, backend down, etc — skip QA gracefully
    return NextResponse.json(
      { questions: [], skip_reason: "Could not reach backend. Proceeding directly." },
      { status: 200 }
    );
  }
}
