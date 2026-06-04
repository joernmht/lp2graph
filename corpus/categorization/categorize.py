#!/usr/bin/env python3
"""Deterministic two-axis categorizer for the extracted MILP corpus.

Design (confirmed with user, 2026-05-31):
  * Two-axis FACETED scheme. Each element carries a STRUCTURAL facet (derived
    deterministically from the formulation) and a DOMAIN facet (rules).
  * Variable-first: variables are categorized first; constraints then inherit
    signal from the domain-roles of the variables they reference, combined with
    their own structural form.
  * Rules only (no ML, no LLM). Output over the real corpus IS the gold seed
    set; where rules are uncertain a label is left as "unclassified" rather
    than guessed, so coverage is measurable and gaps are explicit.

This module is intentionally dependency-free and deterministic: same input ->
same output, no network, no randomness.
"""
from __future__ import annotations
import json, re, glob, os, collections

CORPUS_GLOB = os.path.join(os.path.dirname(__file__), "..", "*.json")

# ---------------------------------------------------------------------------
# Controlled vocabularies (source of truth; mirrored in TAXONOMY.md)
# ---------------------------------------------------------------------------
VAR_TYPES = ("binary", "integer", "continuous")

# Variable DOMAIN ROLE, priority-ordered (first match wins for the primary).
VAR_ROLE_RULES = [
    ("auxiliary_linearization", r"slack|auxiliar|\baux\b|indicator|big[- ]?m|wrap|modulo|excess|penalt|makespan|rosenberg|linear(iz|is)"),
    ("ordering_precedence",      r"preced|order|before|after|sequenc|overtak|\bcross|disjunct|meet"),
    ("routing_path_column",      r"rout|path|\barc\b|edge|leg\b|column|pairing|roster|tour|connection|turnaround"),
    ("timing",                   r"\btime\b|arrival|departure|\bstart|finish|potenti|dwell|durat|epoch|when |schedule time|event time|delay|deviation"),
    ("flow_quantity",            r"\bflow\b|amount|number of|quantity|\bload\b|count|frequenc|volume|passenger flow"),
    ("selection_assignment",     r"1 if|whether|select|assign|chosen|\bused\b|\bopen\b|install|cover|activ|build|hub|whether to|is .* used"),
]

# Constraint DOMAIN FUNCTION, priority-ordered for the PRIMARY label.
# (All matching labels are also kept as `secondary`.)
CON_DOMAIN_RULES = [
    ("periodic_modulo_pesp",          r"modulo|\bpesp\b|cyclic|period|wrap|\bmod\b"),
    ("subtour_connectivity",          r"subtour|\bsec\b|connectiv|\bmtz\b|eliminat|single[- ]?commodity|comb|hypotour|multistar"),
    ("headway_separation",            r"headway|separation|safety|conflict|spacing|min(imum)?[- ]?(time|gap|distance)|overtak|block"),
    ("flow_conservation",             r"conserv|\bbalance\b|flow conservation|in-?out|inflow|outflow|\bdegree\b|continuity"),
    ("capacity_resource",             r"capacit|resourc|\bfleet\b|vehicle count|charger|knapsack|\bload\b|number of (vehicles|trains)|\bcap\b"),
    ("precedence_ordering",           r"preced|order|sequenc|disjunct|before|after|overlap|non[- ]?overlap"),
    ("timing_window",                 r"time[- ]?window|dwell|stay|running time|travel time|arrival|departure|durat|\bwait|min(imum)? (passing|stay)"),
    ("assignment_covering",           r"cover|partition|assign|exactly one|at most one|at least one|\bselect|served by|each (customer|flight|node|duty|train).*(once|one)|=\s*1\b|visit"),
    ("coupling_linking_definition",   r"coupl|\blink|definit|equals|consistency|relat|set .* equal|defines|=\s*\\?omega|travel time ="),
    ("variable_bound_fix",            r"\bbound|domain|\bfix|=\s*0\b|>=\s*0\b|integrality|relax|always (available|=)|never used"),
    ("objective_defining",           r"objective|minim|maxim"),
]

PARAM_DOMAIN_RULES = [
    ("penalty_bigM",       r"big[- ]?m|penalt"),
    ("cost_weight",        r"\bcost\b|\bprice\b|\bweight\b|\bfare\b|coefficient|objective"),
    ("time_duration",      r"\btime\b|durat|processing|headway|travel|period|horizon|dwell|interval|deadline"),
    ("capacity",           r"capacit|\bfleet\b|\bcap\b|\bsize\b|\blimit\b|\bbudget\b|maximum number"),
    ("demand",             r"demand|passenger|\bflow\b|request|share|volume"),
    ("network_structure",  r"\barc\b|\bnode\b|\bedge\b|distance|adjacen|inciden|route|graph|station|stop|topology|set of"),
    ("count_limit",        r"number of|count|\bmax\b|\bmin\b|\bk\b|how many"),
]


def _first_match(text, rules, default="unclassified"):
    t = (text or "").lower()
    for label, rx in rules:
        if re.search(rx, t):
            return label
    return default


def _all_matches(text, rules):
    t = (text or "").lower()
    return [label for label, rx in rules if re.search(rx, t)]


# ---------------------------------------------------------------------------
# Structural facet (deterministic) for constraints
# ---------------------------------------------------------------------------
def constraint_structural(c):
    latex = c.get("expression_latex") or ""
    plain = (c.get("expression_plain") or "")
    blob = latex + " " + plain
    low = blob.lower()
    # relation
    if re.search(r"\\leq|\\le\b|<=|\\geq|\\ge\b|>=|\\lneq|\\gneq|≤|≥", latex):
        relation = "inequality"
    elif re.search(r"(?<![<>!])=(?![<>])|\\?=", latex):
        relation = "equality"
    else:
        relation = "unknown"
    flags = []
    if re.search(r"\bm\s*\(|\bm\s*\\?left|\b-?\s*m\b|big[- ]?m|\\,m\\,|m\s*\(1", low) or re.search(r"M\s*\(|M\s*\\left|-\s*M|\+\s*M", latex):
        flags.append("has_big_m")
    if re.search(r"\\sum|\bsum\b|Σ|∑", blob):
        flags.append("aggregation_sum")
    if re.search(r"\\max|\bmax\b", blob):
        flags.append("aggregation_max")
    if re.search(r"\\min|\bmin\b", blob):
        flags.append("aggregation_min")
    if re.search(r"\bmod\b|modulo|\\bmod|period|cyclic", low):
        flags.append("periodic_modulo")
    if re.search(r"indicator|1 if|\\mathbb\{1\}", low):
        flags.append("indicator")
    if relation == "equality" and re.search(r"definit|equals|defines|consistency|:=|travel time =|= \\omega", low):
        flags.append("definitional")
    return {"relation": relation, "flags": sorted(set(flags))}


# ---------------------------------------------------------------------------
# Variable-informed signal: which decision variables a constraint references
# ---------------------------------------------------------------------------
def _var_base(name):
    # "x_{i,j}" -> "x"; "t^F_i" -> "t"; strip subscripts/superscripts/braces
    m = re.match(r"\\?([A-Za-z][A-Za-z0-9]*)", name.strip().lstrip("\\"))
    return m.group(1).lower() if m else name.lower()


def referenced_var_roles(c, var_roles):
    """var_roles: dict base_symbol -> domain_role. Return roles referenced in latex."""
    latex = (c.get("expression_latex") or "")
    found = []
    for base, role in var_roles.items():
        # match the base symbol as a token (e.g. x, y, t) at a word-ish boundary
        if re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(base), latex):
            found.append(role)
    return sorted(set(found))


# Map a set of referenced variable-roles -> a domain hint (variable-informed prior)
ROLE_TO_DOMAIN_HINT = {
    "ordering_precedence": "precedence_ordering",
    "routing_path_column": "assignment_covering",
    "timing": "timing_window",
    "flow_quantity": "flow_conservation",
    "selection_assignment": "assignment_covering",
    "auxiliary_linearization": "coupling_linking_definition",
}


def categorize_model(d, m):
    # --- variables first ---
    var_roles = {}
    vars_out = []
    for v in m.get("decision_variables", []):
        vtype_raw = (v.get("type") or "").lower()
        vtype = next((t for t in VAR_TYPES if t in vtype_raw), "unknown")
        text = (v.get("name", "") + " " + (v.get("meaning") or ""))
        role = _first_match(text, VAR_ROLE_RULES)
        base = _var_base(v.get("name", ""))
        if base not in var_roles and role != "unclassified":
            var_roles[base] = role
        vars_out.append({"name": v.get("name"), "algebraic_type": vtype, "domain_role": role})

    # --- constraints (variable-informed) ---
    cons_out = []
    for c in m.get("constraints", []):
        struct = constraint_structural(c)
        text = (c.get("name", "") + " " + (c.get("expression_plain") or ""))
        domain_primary = _first_match(text, CON_DOMAIN_RULES)
        domain_secondary = _all_matches(text, CON_DOMAIN_RULES)
        linked_roles = referenced_var_roles(c, var_roles)
        # variable-informed fallback: if name/plain rules failed, infer from linked roles
        if domain_primary == "unclassified" and linked_roles:
            hints = [ROLE_TO_DOMAIN_HINT[r] for r in linked_roles if r in ROLE_TO_DOMAIN_HINT]
            if hints:
                domain_primary = collections.Counter(hints).most_common(1)[0][0]
                domain_secondary = sorted(set(domain_secondary + hints))
        cons_out.append({
            "name": c.get("name"),
            "structural": struct,
            "domain_primary": domain_primary,
            "domain_secondary": sorted(set(domain_secondary)),
            "linked_variable_roles": linked_roles,
        })

    # --- parameters ---
    params_out = []
    for p in m.get("parameters", []):
        text = (p.get("name", "") + " " + (p.get("meaning") or ""))
        kind = p.get("kind")  # lp2graph structural kind if present
        if not kind:
            if re.search(r"big[- ]?m", text.lower()):
                kind = "big_m"
            elif re.search(r"toler", text.lower()):
                kind = "tolerance"
            else:
                kind = "scalar_or_indexed"
        params_out.append({
            "name": p.get("name"),
            "structural_kind": kind,
            "domain_class": _first_match(text, PARAM_DOMAIN_RULES),
        })

    return {
        "model_id": m.get("model_id"),
        "objective_sense": (m.get("objective") or {}).get("sense"),
        "variables": vars_out,
        "constraints": cons_out,
        "parameters": params_out,
    }


def main():
    out = {"repos": []}
    cov = collections.Counter()
    tally = {"var_role": collections.Counter(), "con_domain": collections.Counter(),
             "con_relation": collections.Counter(), "con_flags": collections.Counter(),
             "param_domain": collections.Counter()}
    for jf in sorted(glob.glob(CORPUS_GLOB)):
        if os.path.basename(jf) in ("INDEX.md",):
            continue
        d = json.load(open(jf))
        rec = {"repo": d.get("repo"), "file": os.path.basename(jf), "models": []}
        for m in d.get("models", []):
            cm = categorize_model(d, m)
            rec["models"].append(cm)
            for v in cm["variables"]:
                tally["var_role"][v["domain_role"]] += 1
                cov["vars_total"] += 1
                cov["vars_classified"] += (v["domain_role"] != "unclassified")
            for c in cm["constraints"]:
                tally["con_domain"][c["domain_primary"]] += 1
                tally["con_relation"][c["structural"]["relation"]] += 1
                for f in c["structural"]["flags"]:
                    tally["con_flags"][f] += 1
                cov["cons_total"] += 1
                cov["cons_classified"] += (c["domain_primary"] != "unclassified")
            for p in cm["parameters"]:
                tally["param_domain"][p["domain_class"]] += 1
                cov["params_total"] += 1
                cov["params_classified"] += (p["domain_class"] != "unclassified")
        out["repos"].append(rec)

    outpath = os.path.join(os.path.dirname(__file__), "categorized_corpus.json")
    json.dump(out, open(outpath, "w"), indent=2)

    # coverage report
    def pct(a, b):
        return f"{100*a/b:.1f}%" if b else "n/a"
    print("== COVERAGE (classified / total) ==")
    print(f"  variables   {cov['vars_classified']}/{cov['vars_total']}  {pct(cov['vars_classified'],cov['vars_total'])}")
    print(f"  constraints {cov['cons_classified']}/{cov['cons_total']}  {pct(cov['cons_classified'],cov['cons_total'])}")
    print(f"  parameters  {cov['params_classified']}/{cov['params_total']}  {pct(cov['params_classified'],cov['params_total'])}")
    print("\n== VARIABLE domain_role ==")
    for k, n in tally["var_role"].most_common():
        print(f"  {n:4d}  {k}")
    print("\n== CONSTRAINT domain_primary ==")
    for k, n in tally["con_domain"].most_common():
        print(f"  {n:4d}  {k}")
    print("\n== CONSTRAINT structural relation ==")
    for k, n in tally["con_relation"].most_common():
        print(f"  {n:4d}  {k}")
    print("\n== CONSTRAINT structural flags ==")
    for k, n in tally["con_flags"].most_common():
        print(f"  {n:4d}  {k}")
    print("\n== PARAMETER domain_class ==")
    for k, n in tally["param_domain"].most_common():
        print(f"  {n:4d}  {k}")
    print(f"\nwrote {outpath}")


if __name__ == "__main__":
    main()
