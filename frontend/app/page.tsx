// Phase 21 — the root path now redirects to /characters because the
// operator's workflow is: pick character → see videos → create video.
// The old dashboard tab was removed per operator request because it
// duplicated the Video-uri list verbatim.
//
// Server-side redirect so the browser never paints a flicker frame.
import { redirect } from "next/navigation";

export default function RootRedirect(): never {
  redirect("/characters");
}
