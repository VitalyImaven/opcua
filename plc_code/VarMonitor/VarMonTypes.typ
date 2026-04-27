(********************************************************************
 * VarMonitor — Type definitions
 ********************************************************************)
TYPE
    VM_States_enum : (
        VM_STATE_INIT := 0,
        VM_STATE_LISTEN,
        VM_STATE_RUNNING,
        VM_STATE_ERROR
    );
    
    (* Type codes for the wire protocol *)
    VM_TypeCode_enum : (
        VM_TYPE_BOOL   := 0,
        VM_TYPE_INT    := 1,
        VM_TYPE_UINT   := 2,
        VM_TYPE_DINT   := 3,
        VM_TYPE_UDINT  := 4,
        VM_TYPE_REAL   := 5,
        VM_TYPE_LREAL  := 6,
        VM_TYPE_STRING := 7,
        VM_TYPE_USINT  := 8,
        VM_TYPE_SINT   := 9
    );
    
    (* Variable registry entry — maps ID to memory address *)
    VM_VarEntry_typ : STRUCT
        pAddress : UDINT;       (* Memory address from ADR() *)
        typeCode : USINT;       (* VM_TypeCode_enum *)
        dataSize : USINT;       (* Bytes for this type (0 for STRING = variable) *)
        name     : STRING[120]; (* Full variable path — for registry response *)
    END_STRUCT;
    
END_TYPE
