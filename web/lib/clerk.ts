// Clerk is optional: the app runs as the public demo until the publishable key
// is present, then sign-in + authenticated uploads activate. The key is inlined
// at build time, so this is a constant.
export const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
