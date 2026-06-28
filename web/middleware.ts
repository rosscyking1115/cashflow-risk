import { clerkMiddleware } from "@clerk/nextjs/server";
import { type NextFetchEvent, type NextRequest, NextResponse } from "next/server";

// No-op when Clerk isn't configured, so the demo deploy runs without keys.
const passthrough = (_req: NextRequest, _ev: NextFetchEvent) => NextResponse.next();

export default process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  ? clerkMiddleware()
  : passthrough;

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
