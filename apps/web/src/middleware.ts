import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtectedRoute = createRouteMatcher([
  "/incidents(.*)",
  "/chat(.*)",
  "/rag(.*)",
  "/api/incidents(.*)",
  "/api/chat(.*)",
  "/api/rag(.*)"
]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtectedRoute(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)", "/"]
};
