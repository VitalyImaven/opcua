"""
One-step script to regenerate the VarMonitor variable registry.

After adding/removing variables in B&R Automation Studio .var/.typ files:
    python update_varmon.py                   # uses HILA_MR config
    python update_varmon.py --config Barak_MR # for a different config

This runs:
  1. plc_var_scanner.py  — scans global vars from packages in the active config
  2. plc_var_codegen.py  — generates VarMon_RegInit_*.st files for ProtoBufCom
  3. plc_registry_from_st.py — rebuilds the Python-side registry from the .st files
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
PROTOBUF_COM_DIR = Path(
    r"C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical\GlobalOps\ProtoBufCom"
)


def run(cmd: list[str]):
    print(f"\n{'='*60}")
    print(f"  Running: {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=str(HERE))
    if result.returncode != 0:
        print(f"FAILED with code {result.returncode}")
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description="Regenerate VarMonitor registry")
    parser.add_argument("--config", default="ALL",
                        help="B&R configuration name (default: ALL — scan everything)")
    args = parser.parse_args()

    # Step 1: Scan global variables for the specified config
    run([sys.executable, "plc_var_scanner.py", "--config", args.config])

    # Step 2: Generate PLC registration code
    run([
        sys.executable, "plc_var_codegen.py",
        "--registry", "plc_var_registry.json",
        "--outdir", str(PROTOBUF_COM_DIR),
        "--max", "100000",
    ])

    # Step 3: Rebuild Python-side registry from generated .st files
    run([sys.executable, "plc_registry_from_st.py"])

    print(f"\n{'='*60}")
    print(f"  Done! Config: {args.config}")
    print("  Rebuild the project in Automation Studio.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
