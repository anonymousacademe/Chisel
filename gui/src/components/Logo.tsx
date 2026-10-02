import logoUrl from "../assets/logo.svg";

/** The LoreWriter mark (an open book and a quill; source of the packaging icons). */
export function Logo({ size = 24 }: { size?: number }) {
  return <img className="lw-logo" src={logoUrl} width={size} height={size} alt="LoreWriter" draggable={false} />;
}
