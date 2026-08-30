import { useAuth } from "./auth/AuthContext";

/** The signed-in person's first name.
 *
 *  Both the dashboard and the session header were showing `student.firstName`
 *  from lib/data — "Arjun", hardcoded — so everyone who signed in was greeted
 *  as somebody else. Shared rather than duplicated because it was wrong in two
 *  places and fixing one of them is how it stays wrong in the other.
 *
 *  Google supplies a displayName. The fallback is the email's local part with
 *  trailing digits stripped ("arnav.prasad999918" -> "Arnav"), and "there" is
 *  the last resort so a greeting is never left dangling on a comma. */
export function firstNameOf(
  displayName: string | null | undefined,
  email: string | null | undefined,
): string {
  const display = (displayName ?? "").trim();
  if (display) return display.split(/\s+/)[0]!;
  const local = (email ?? "").split("@")[0] ?? "";
  if (!local) return "there";
  const word = local.split(/[._-]/)[0]!.replace(/[0-9]+$/, "");
  return word ? word.charAt(0).toUpperCase() + word.slice(1) : "there";
}

export function useFirstName(): string {
  const { user } = useAuth();
  return firstNameOf(user?.displayName, user?.email);
}
