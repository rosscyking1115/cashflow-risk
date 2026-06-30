import { clerkMiddleware } from "@clerk/nextjs/server";
import { type NextFetchEvent, type NextRequest, NextResponse } from "next/server";

// Next.js 16 renamed the middleware convention to proxy.ts; Clerk's handshake
// location check expects this filename on Next 16+. No-op when Clerk isn't
// configured, so the demo deploy runs without keys.
const passthrough = (_req: NextRequest, _ev: NextFetchEvent) => NextResponse.next();

export default process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  ? clerkMiddleware()
  : passthrough;

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
