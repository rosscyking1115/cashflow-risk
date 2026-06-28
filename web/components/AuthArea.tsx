"use client";

import { SignInButton, UserButton, useUser } from "@clerk/nextjs";

// Only rendered when Clerk is enabled (so a ClerkProvider is present).
export function AuthArea() {
  const { isLoaded, isSignedIn } = useUser();

  if (!isLoaded) return null;

  if (isSignedIn) return <UserButton />;

  return (
    <SignInButton mode="modal">
      <button className="rounded-md border border-accent px-3 py-1.5 text-sm font-medium text-accent transition-colors hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
        Sign in
      </button>
    </SignInButton>
  );
}
