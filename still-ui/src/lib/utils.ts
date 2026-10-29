export { cn } from "cn"
/** Still for Mac runs the same UI in WebKit; copy and shortcut hints follow the platform. */
export const MAC = /Mac/.test(navigator.userAgent)
/** Chats scroll with no scrollbar; once scrolled, their top edge fades (App.css .is-scrolled). */
export const fadeTop = (e: { currentTarget: HTMLElement }) => e.currentTarget.classList.toggle("is-scrolled", e.currentTarget.scrollTop > 2)
