import { createContext, useContext } from "react"

// Every popover stays 8px inside the window and, under a CollisionBoundary (the chat panel), inside that panel too: it
// flips to the other side, slides along and shrinks to scroll when it doesn't fit.
export const CollisionBoundary = createContext<Element | null>(null)

export function useCollision() {
  const boundary = useContext(CollisionBoundary)
  return { collisionPadding: 8, collisionBoundary: boundary ? [boundary] : [], sticky: "always" as const }
}
