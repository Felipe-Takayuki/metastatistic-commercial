import { sql } from "@codemirror/lang-sql";
import { Prec } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import CodeMirror from "@uiw/react-codemirror";
import { useMemo } from "react";
import { useResolvedTheme } from "../lib/theme";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onRun: () => void;
  height?: string;
  onCreate?: (view: EditorView) => void;
}

/** Editor SQL (CodeMirror). Ctrl/⌘+Enter executa. */
export function SqlEditor({ value, onChange, onRun, height = "120px", onCreate }: Props) {
  const theme = useResolvedTheme();
  const extensions = useMemo(
    () => [sql(), EditorView.lineWrapping, Prec.highest(keymap.of([{ key: "Mod-Enter", run: () => (onRun(), true) }]))],
    [onRun],
  );
  return (
    <div className="cm-wrap">
      <CodeMirror
        value={value}
        onChange={onChange}
        onCreateEditor={onCreate}
        extensions={extensions}
        theme={theme}
        height={height}
        basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: false }}
        aria-label="Editor SQL"
      />
    </div>
  );
}
