import { api } from "../../backend/api";

/** The journal's guide link (opened through the app's external-link path) and the date its rules were read. */
export function SourceLine({ source, readOn }: { source: string; readOn: string }) {
  return (
    <p className="lw-dialog__message">
      {source && (
        <>Source: <a href={source} onClick={(e) => { e.preventDefault(); void api.openExternal(source); }}>{source}</a>. </>
      )}
      {readOn && <>Rules read on {readOn}; check the journal's live guide before you submit.</>}
    </p>
  );
}
