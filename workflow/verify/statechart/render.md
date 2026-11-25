# Render a chart

`node <verify skill dir>/statechart/scripts/render.mjs CHART.mmd [--out FILE.svg]` renders a chart
with the npm package `pele@1.9.0` and writes the SVG next to the `.mmd` file by default. The first
run installs Pele into `$XDG_CACHE_HOME/cosmos/pele/1.9.0/` (default `~/.cache/...`; `PELE_DIR`
selects another directory), which needs network once. It passes
`{ limit: 1_000_000, outputLimit: 8_000_000, maxEdges: 10_000 }` to Pele's `render`, because Pele's
defaults are smaller than a chart of 500 states can be. On a `PeleError` it prints the message and
exits 1; show the user the Mermaid text and the error.

## Source stamp

The SVG carries `<!-- statechart-source sha256:<hex> -->`: the digest of the Mermaid text with blank
lines and trailing spaces removed. The spec review page shows `statechart.svg` only while this stamp
matches its `## 状态图` block, so re-render after every chart edit.

## Colors

Pele ignores Mermaid `theme` and `themeVariables`; the script puts a `<style>` element at the start
of the SVG that sets Pele's `--pele-*` variables on `.pele` (https://pele.run/theming) for light and
dark viewers. The command gives each state the color class of its group, such as `class sN teal`, and
marks bad states with `breaks` or `mayBreak`, states on the shortest bug path with `bugPath`, and
states a PROPERTY counterexample repeats forever with `repeats`. Pele writes each `classDef` color
as a `style` attribute, which beats a normal CSS rule, so the mark rules use `!important` and come
after the group colors. A bug mark sets the fill and the text; `bugPath` and `repeats` set the
border. The colors are those of the original pstack skill.
