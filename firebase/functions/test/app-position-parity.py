"""Compare the deployed JavaScript state machine with app.py's real implementation."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[3]
APP_PATH = REPO_ROOT / "app.py"
FUNCTIONS_DIR = Path(__file__).resolve().parents[1]


def load_app_strategy_functions():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    wanted_assignments = {
        "BASE_MA",
        "FAST_MA",
        "MID_MA",
        "SLOW_MA",
        "SIGNAL_MAS",
        "BUY_TARGETS",
        "SELL_LIMITS",
    }
    wanted_functions = {"initial_position_from_state", "calculate_event_position"}
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & wanted_assignments:
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            selected.append(node)
    module = ast.Module(body=selected, type_ignores=[])
    namespace = {"pd": pd}
    exec(compile(ast.fix_missing_locations(module), str(APP_PATH), "exec"), namespace)
    return namespace["calculate_event_position"]


def app_positions():
    rows = []
    for prices, crossing in [
        ((99, 99, 99), None),
        ((101, 99, 99), ("up", 5)),
        ((101, 101, 99), ("up", 20)),
        ((101, 101, 101), ("up", 65)),
        ((99, 101, 101), ("down", 5)),
        ((99, 99, 101), ("down", 20)),
        ((99, 99, 99), ("down", 65)),
    ]:
        row = {"ma5": prices[0], "ma20": prices[1], "ma65": prices[2], "ma120": 100}
        for period in (5, 20, 65):
            row[f"cross_up_{period}"] = crossing == ("up", period)
            row[f"cross_down_{period}"] = crossing == ("down", period)
        rows.append(row)
    calculate = load_app_strategy_functions()
    return calculate(pd.DataFrame(rows), sell_mode="partial", buffer_pct=0).tolist()


def javascript_positions():
    script = """
const { applyPositionEvents } = require('./signal-engine');
let p = 0;
const out = [p];
for (const [period, direction] of [[5,true],[20,true],[65,true],[5,false],[20,false],[65,false]]) {
  p = applyPositionEvents(p, [{ period, direction }]);
  out.push(p);
}
process.stdout.write(JSON.stringify(out));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=FUNCTIONS_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


if __name__ == "__main__":
    expected = app_positions()
    actual = javascript_positions()
    assert actual == expected, f"Firebase {actual} != app.py {expected}"
    print(f"app.py parity OK: {actual}")
