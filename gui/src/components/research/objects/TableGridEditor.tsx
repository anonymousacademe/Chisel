import { ALIGNS, addCol, addRow, gridHints, parseTsv, pasteGrid, removeCol, removeRow, setAlign, withCell, type Grid } from "../../../data/objects";
import type { TableAlign } from "../../../data/research";
import "../../../styles/objects.css";

/** An editable table: the first row is the header; add or remove rows and columns, set each column's alignment, and
 *  paste tab-separated text (copied from a spreadsheet) into any cell to fill the grid from there. */
export function TableGridEditor({ grid, onChange, readOnly = false }: { grid: Grid; onChange: (g: Grid) => void; readOnly?: boolean }) {
  const hints = gridHints(grid);
  const onPaste = (e: React.ClipboardEvent<HTMLInputElement>, r: number, c: number) => {
    const rows = parseTsv(e.clipboardData.getData("text/plain"));
    if (!rows) return;               // plain text: the cell takes it as usual
    e.preventDefault();
    onChange(pasteGrid(grid, r, c, rows));
  };
  return (
    <div className="lw-grid">
      <div className="lw-grid__scroll">
        <table aria-label="Table cells">
          <thead>
            <tr>
              <th aria-hidden className="lw-grid__corner" />
              {grid.align.map((a, c) => (
                <th key={c} scope="col">
                  <div className="lw-grid__colhead">
                    <select aria-label={`Alignment of column ${c + 1}`} value={a} disabled={readOnly}
                      onChange={(e) => onChange(setAlign(grid, c, e.target.value as TableAlign))}>
                      {ALIGNS.map((x) => <option key={x} value={x}>{x === "default" ? "Align: default" : `Align: ${x}`}</option>)}
                    </select>
                    {!readOnly && (
                      <button type="button" className="lw-link" aria-label={`Remove column ${c + 1}`} disabled={grid.align.length <= 1}
                        onClick={() => onChange(removeCol(grid, c))}>Remove</button>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.cells.map((row, r) => (
              <tr key={r} className={r === 0 ? "is-header" : undefined}>
                <th scope="row" className="lw-grid__rowhead">
                  {r === 0 ? <span className="lw-faint">Header</span> : (
                    !readOnly && <button type="button" className="lw-link" aria-label={`Remove row ${r}`} disabled={grid.cells.length <= 2}
                      onClick={() => onChange(removeRow(grid, r))}>Remove</button>
                  )}
                </th>
                {row.map((v, c) => (
                  <td key={c}>
                    <input value={v} readOnly={readOnly} style={{ textAlign: grid.align[c] === "default" ? undefined : grid.align[c] }}
                      aria-label={r === 0 ? `Header, column ${c + 1}` : `Row ${r}, column ${c + 1}`}
                      onChange={(e) => onChange(withCell(grid, r, c, e.target.value))} onPaste={(e) => onPaste(e, r, c)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!readOnly && (
        <div className="lw-row lw-gap-8">
          <button type="button" className="lw-btn" onClick={() => onChange(addRow(grid))}>Add row</button>
          <button type="button" className="lw-btn" onClick={() => onChange(addCol(grid))}>Add column</button>
          <span className="lw-faint lw-grid__hint">Paste copied spreadsheet cells into any cell to fill the grid from there.</span>
        </div>
      )}
      {hints.map((h) => <p key={h} className="lw-faint lw-grid__hint">{h}</p>)}
    </div>
  );
}
