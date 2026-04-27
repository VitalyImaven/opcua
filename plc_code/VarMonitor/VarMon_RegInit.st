(********************************************************************
 * VarMon Registry Init — AUTO-GENERATED EXAMPLE
 *
 * This file shows how to register PLC variables with the VarMonitor.
 * In your real project, run plc_var_codegen.py to generate this
 * from plc_var_registry.json.
 *
 * Each entry maps a var_id (index) to a PLC variable's memory address.
 ********************************************************************)
ACTION VarMon_RegInit:
    
    vmRegCount := 0;
    
    (* ── Example: Exit subsystem interface ── *)
    
    (* gExitCtrl.In.Cmd.FullMechInit *)
    vmRegistry[0].pAddress := ADR(gExitCtrl.In.Cmd.FullMechInit);
    vmRegistry[0].typeCode := 0;  (* BOOL *)
    vmRegistry[0].dataSize := 1;
    vmRegistry[0].name := 'gExitCtrl.In.Cmd.FullMechInit';
    
    (* gExitCtrl.In.Cmd.Stop *)
    vmRegistry[1].pAddress := ADR(gExitCtrl.In.Cmd.Stop);
    vmRegistry[1].typeCode := 0;  (* BOOL *)
    vmRegistry[1].dataSize := 1;
    vmRegistry[1].name := 'gExitCtrl.In.Cmd.Stop';
    
    (* gExitCtrl.Out.Status.AtReady *)
    vmRegistry[2].pAddress := ADR(gExitCtrl.Out.Status.AtReady);
    vmRegistry[2].typeCode := 0;  (* BOOL *)
    vmRegistry[2].dataSize := 1;
    vmRegistry[2].name := 'gExitCtrl.Out.Status.AtReady';
    
    (* gWHS_Ctrl.Input.Cmd.Print *)
    vmRegistry[3].pAddress := ADR(gWHS_Ctrl.Input.Cmd.Print);
    vmRegistry[3].typeCode := 0;  (* BOOL *)
    vmRegistry[3].dataSize := 1;
    vmRegistry[3].name := 'gWHS_Ctrl.Input.Cmd.Print';
    
    (* gWHS_Ctrl.Output.Status.AtPrint *)
    vmRegistry[4].pAddress := ADR(gWHS_Ctrl.Output.Status.AtPrint);
    vmRegistry[4].typeCode := 0;  (* BOOL *)
    vmRegistry[4].dataSize := 1;
    vmRegistry[4].name := 'gWHS_Ctrl.Output.Status.AtPrint';
    
    (* gPrintSpeed *)
    vmRegistry[5].pAddress := ADR(gPrintSpeed);
    vmRegistry[5].typeCode := 5;  (* REAL *)
    vmRegistry[5].dataSize := 4;
    vmRegistry[5].name := 'gPrintSpeed';
    
    (* ... continue for all variables you want to expose ... *)
    (* Run: python plc_var_codegen.py to generate the full list *)
    
    vmRegCount := 6;  (* Update with actual count *)
    
END_ACTION
