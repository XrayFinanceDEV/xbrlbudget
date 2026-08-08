import { redirect } from "next/navigation";

/** La vecchia rotta del wizard infrannuale: ora è il percorso unico /pratica. */
export default function InfrannualeRedirect() {
  redirect("/pratica");
}
