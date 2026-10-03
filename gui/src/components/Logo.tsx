import logoUrl from "../assets/logo.svg";

/** The Chisel app icon (a stone-and-page book with a chisel; docs/brand holds the vector sources). */
export function Logo({ size = 24 }: { size?: number }) {
  return <img className="lw-logo" src={logoUrl} width={size} height={size} alt="Chisel" draggable={false} />;
}
