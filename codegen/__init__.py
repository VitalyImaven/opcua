"""
codegen — PLC variable registry code generation pipeline.

Modules:
    scanner          — Scan B&R project files to discover variables
    codegen          — Generate VarMon_RegInit_*.st PLC registration code
    registry_from_st — Rebuild plc_var_registry.json from generated PLC code
    gen_x2           — Generate test variable structures

Pipeline:
    1. scanner.py       → plc_var_registry.json (scan .var/.typ files)
    2. codegen.py       → VarMon_RegInit_*.st   (generate PLC code)
    3. registry_from_st → plc_var_registry.json  (sync from PLC code)
"""
