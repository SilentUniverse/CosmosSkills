#!/usr/bin/env bash
# Mechanical gate for the ARTIFACT-FORMAT.md contract (.scratch/ artifacts).
# PowerShell twin: verify-artifacts.ps1 (canonical). Exit: 0 clean, 1 violations, 2 usage.
set -u
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then echo "verify-artifacts.sh needs bash >= 4" >&2; exit 2; fi

ROOT="${1:-$PWD}"
SCRATCH="$ROOT/.scratch"
if [ ! -d "$SCRATCH" ]; then
    echo "verify-artifacts: no .scratch/ under $ROOT - nothing to check, clean."
    exit 0
fi

viol=0
n_issues=0; n_prds=0; n_handoffs=0; n_sums=0

err() { echo "  $1"; viol=$((viol + 1)); }

# fm_parse <file> -> fills assoc FM (key -> value; lists space-joined), sets FM_PRESENT=1.
declare -A FM
FM_PRESENT=0
fm_parse() {
    local f="$1" out
    FM=(); FM_PRESENT=0
    out=$(awk '
        function trim(s) { gsub(/^[ \t\r]+|[ \t\r]+$/, "", s); return s }
        NR == 1 {
            sub(/^\357\273\277/, "")
            if ($0 ~ /^---[ \t\r]*$/) { infm = 1; next }
        }
        infm && /^---[ \t\r]*$/ { if (pend != "") print pend "\t" buf; print "\t__END__"; exit }
        infm {
            if (/^[ \t]*-[ \t]+/ && pend != "") {
                item = $0; sub(/^[ \t]*-[ \t\r]+/, "", item)
                buf = (buf == "" ? "" : buf " ") trim(item); next
            }
            if (pend != "") { print pend "\t" buf; pend = "" }
            if (/^[A-Za-z][A-Za-z0-9_-]*:/) {
                key = $0; sub(/:.*/, "", key)
                val = $0; sub(/^[^:]*:[ \t]*/, "", val)
                if (val ~ /^\[/) {
                    sub(/^\[/, "", val); sub(/\][ \t\r]*$/, "", val)
                    gsub(/,/, " ", val); gsub(/"/, "", val)
                    print key "\t" trim(val)
                }
                else if (trim(val) == "") { pend = key; buf = "" }
                else print key "\t" trim(val)
            }
        }' "$f")
    [ -n "$out" ] || return 0
    local IFS=$'\n' line k v
    while read -r line; do
        k="${line%%$'\t'*}"; v="${line#*$'\t'}"
        if [ "$k" = "" ] && [ "$v" = "__END__" ]; then FM_PRESENT=1; continue; fi
        v="${v//\"/}"; v="${v//\'/}"; v="${v//$'\r'/}"
        FM["$k"]="$v"
    done <<< "$out"
}

check_handoff() { # $1 path, $2 expected feature ('' = must be null/absent)
    local path="$1" ef="$2" feat
    n_handoffs=$((n_handoffs + 1))
    fm_parse "$path"
    [ "$FM_PRESENT" = 1 ] || { err "$path: no YAML frontmatter"; return; }
    [ "${FM[type]:-}" = "handoff" ] || err "$path: type '${FM[type]:-}' != handoff"
    feat="${FM[feature]:-}"
    if [ -z "$ef" ]; then
        if [ -n "$feat" ] && [ "$feat" != "null" ]; then err "$path: cross-feature handoff must have feature null, got '$feat'"; fi
    elif [ "$feat" != "$ef" ]; then
        err "$path: feature '$feat' != directory '$ef'"
    fi
    [ -n "${FM[git_base]:-}" ] || err "$path: git_base missing"
    case "${FM[status]:-}" in active|consumed) ;; *) err "$path: status '${FM[status]:-}' not in active|consumed";; esac
    [[ "${FM[date]:-}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || err "$path: date not ISO YYYY-MM-DD"
}

for fdir in "$SCRATCH"/*/; do
    [ -d "$fdir" ] || continue
    feat="$(basename "$fdir")"

    # --- PRD files ---
    prds=("$fdir"PRD*.md)
    if [ -e "${prds[0]}" ]; then
        declare -A superseded
        live=()
        for p in "${prds[@]}"; do
            n_prds=$((n_prds + 1))
            fm_parse "$p"
            if [ "$FM_PRESENT" != 1 ]; then err "$p: no YAML frontmatter"; continue; fi
            [ "${FM[type]:-}" = "prd" ] || err "$p: type '${FM[type]:-}' != prd"
            base="$(basename "$p")"
            if [ "$base" = "PRD.md" ]; then
                [ "${FM[version]:-}" = "1" ] || err "$p: PRD.md must carry version 1, got '${FM[version]:-}'"
            elif [[ "$base" =~ ^PRD-v([0-9]+)\.md$ ]]; then
                [ "${FM[version]:-}" = "${BASH_REMATCH[1]}" ] || err "$p: filename says v${BASH_REMATCH[1]} but version: ${FM[version]:-}"
            else
                err "$p: PRD filename must be PRD.md or PRD-vN.md"
            fi
            if [ -n "${FM[supersedes]:-}" ]; then
                sup="${FM[supersedes]}"
                [ -e "$fdir$sup" ] || err "$p: supersedes '$sup' not found in this directory"
                superseded["$sup"]=1
            fi
        done
        if [ "${#prds[@]}" -gt 1 ]; then
            for p in "${prds[@]}"; do
                [ -n "${superseded[$(basename "$p")]:-}" ] || live+=("$(basename "$p")")
            done
            [ "${#live[@]}" -eq 1 ] || err "$fdir: PRD chain must leave exactly one live head, found: ${live[*]:-none}"
        fi
        unset superseded
    fi

    # --- SUMMARY / handoff / issues ---
    if [ -f "$fdir/SUMMARY.md" ]; then
        n_sums=$((n_sums + 1))
        fm_parse "$fdir/SUMMARY.md"
        if [ "$FM_PRESENT" != 1 ]; then err "$fdir/SUMMARY.md: no YAML frontmatter"
        elif [ "${FM[type]:-}" != "summary" ]; then err "$fdir/SUMMARY.md: type '${FM[type]:-}' != summary"; fi
    fi
    [ -f "$fdir/handoff.md" ] && check_handoff "$fdir/handoff.md" "$feat"

    idir="$fdir/issues"
    if [ -d "$idir" ]; then
        files=("$idir"/*.md)
        if [ -e "${files[0]}" ]; then
            declare -A byslug nnseen graph
            for f in "${files[@]}"; do
                slug="$(basename "$f" .md)"
                byslug["$slug"]="$f"
                if [[ "$slug" =~ ^([0-9]{2,})- ]]; then
                    nn="${BASH_REMATCH[1]}"
                    if [ -n "${nnseen[$nn]:-}" ]; then err "$f: duplicate NN $nn (also ${nnseen[$nn]})"; else nnseen["$nn"]="$slug"; fi
                else
                    err "$f: filename not NN-slug"
                fi
            done
            for f in "${files[@]}"; do
                n_issues=$((n_issues + 1))
                fm_parse "$f"
                [ "$FM_PRESENT" = 1 ] || { err "$f: no YAML frontmatter"; continue; }
                [ "${FM[type]:-}" = "issue" ] || err "$f: type '${FM[type]:-}' != issue"
                [ "${FM[feature]:-}" = "$feat" ] || err "$f: feature '${FM[feature]:-}' != directory '$feat'"
                case "${FM[status]:-}" in
                    ready-for-agent|ready-for-human|done) ;;
                    *) err "$f: status '${FM[status]:-}' not in ready-for-agent|ready-for-human|done";;
                esac
                cat="${FM[category]:-}"
                case "$cat" in
                    enhancement|detail|redo|fix) ;;
                    *) err "$f: category '$cat' not in enhancement|detail|redo|fix";;
                esac
                deps=""
                for b in ${FM[blocked_by]:-}; do
                    [ -n "$b" ] || continue
                    if [ -z "${byslug[$b]:-}" ]; then err "$f: blocked_by '$b' resolves to no sibling file"
                    elif [ "$b" = "$(basename "$f" .md)" ]; then err "$f: blocked_by itself"
                    else deps="$deps $b"; fi
                done
                graph["$(basename "$f" .md)"]="$deps"
                case "$cat" in
                    detail|redo|fix)
                        ref="${FM[refines]:-}"
                        if [ -n "$ref" ]; then
                            [ -n "${byslug[$ref]:-}" ] || err "$f: refines '$ref' resolves to no sibling file"
                        else
                            err "$f: category '$cat' requires refines:"
                        fi ;;
                esac
                if [ -z "${FM[created]:-}" ]; then
                    err "$f: created missing"
                elif ! [[ "${FM[created]}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
                    err "$f: created not ISO YYYY-MM-DD"
                fi
            done
            # Kahn peeling: whatever survives is in (or feeds into) a blocked_by cycle.
            declare -A rem
            for k in "${!graph[@]}"; do
                rdeps=""
                for d in ${graph[$k]}; do [ -n "${graph[$d]:-}" ] && rdeps="$rdeps $d"; done
                rem["$k"]="$rdeps"
            done
            changed=1
            while [ "$changed" = 1 ]; do
                changed=0
                for k in "${!rem[@]}"; do
                    left=""
                    for d in ${rem[$k]}; do [ -n "${rem[$d]:-}" ] && left="$left $d"; done
                    if [ -z "$left" ]; then unset "rem[$k]"; changed=1; fi
                done
            done
            for c in "${!rem[@]}"; do err "${byslug[$c]}: in (or depends on) a blocked_by cycle"; done
            unset byslug nnseen graph rem
        fi
    fi
done

[ -f "$SCRATCH/handoff.md" ] && check_handoff "$SCRATCH/handoff.md" ""

if [ "$viol" -gt 0 ]; then
    echo "verify-artifacts: $viol violation(s)"
    exit 1
fi
echo "verify-artifacts: OK - checked $n_issues issue(s), $n_prds PRD(s), $n_handoffs handoff(s), $n_sums summary(s)."
exit 0
