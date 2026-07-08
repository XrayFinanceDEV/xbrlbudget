import { redirect } from "next/navigation";

// The Aziende page has merged into the home "Aziende & Pratiche" (Pratica C3).
export default function AziendePage() {
  redirect("/");
}
