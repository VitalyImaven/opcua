(********************************************************************
 * VarMon_SendUpdate — Pack subscribed variable values into UDP packet
 *
 * Packet format:
 *   [MAGIC:2B = 0xAB01][SEQ:4B][TIMESTAMP:4B][COUNT:2B]
 *   For each var: [VAR_ID:2B][TYPE:1B][VALUE: variable]
 ********************************************************************)
ACTION VarMon_SendUpdate:
    
    vmBufPos := 0;
    
    (* ── Header ── *)
    (* Magic *)
    vmUdpBuf[0] := 16#01;  (* Low byte of 0xAB01 *)
    vmUdpBuf[1] := 16#AB;  (* High byte *)
    vmBufPos := 2;
    
    (* Sequence number — 4 bytes LE *)
    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), ADR(vmSeqNum), 4);
    vmBufPos := vmBufPos + 4;
    
    (* Timestamp — 4 bytes LE (ms since boot) *)
    vmTempUdint := clock_ms();
    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), ADR(vmTempUdint), 4);
    vmBufPos := vmBufPos + 4;
    
    (* Count placeholder — fill after packing *)
    vmCountPos := vmBufPos;
    vmBufPos := vmBufPos + 2;
    
    (* ── Pack each subscribed variable ── *)
    vmPackedCount := 0;
    
    FOR vmIdx := 0 TO vmSubCount - 1 DO
        vmVarId := vmSubscription[vmIdx];
        
        (* Bounds check *)
        IF vmVarId >= vmRegCount THEN
            (* Skip invalid var_id *)
            (* Continue loop *)
        ELSIF vmBufPos > (VM_UDP_BUF_SIZE - 12) THEN
            (* Buffer nearly full — send what we have, rest in next packet *)
            (* Exit loop *)
            EXIT;
        ELSE
            (* Pack var_id — 2 bytes LE *)
            vmUdpBuf[vmBufPos] := UINT_TO_USINT(vmVarId MOD 256);
            vmUdpBuf[vmBufPos + 1] := UINT_TO_USINT(vmVarId / 256);
            vmBufPos := vmBufPos + 2;
            
            (* Pack type code — 1 byte *)
            vmUdpBuf[vmBufPos] := vmRegistry[vmVarId].typeCode;
            vmBufPos := vmBufPos + 1;
            
            (* Pack value based on type *)
            CASE vmRegistry[vmVarId].typeCode OF
                
                0: (* BOOL — 1 byte *)
                    brsmemcpy(ADR(vmTempBool), vmRegistry[vmVarId].pAddress, 1);
                    IF vmTempBool THEN
                        vmUdpBuf[vmBufPos] := 1;
                    ELSE
                        vmUdpBuf[vmBufPos] := 0;
                    END_IF;
                    vmBufPos := vmBufPos + 1;
                    
                1: (* INT — 2 bytes LE *)
                    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), vmRegistry[vmVarId].pAddress, 2);
                    vmBufPos := vmBufPos + 2;
                    
                2: (* UINT — 2 bytes LE *)
                    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), vmRegistry[vmVarId].pAddress, 2);
                    vmBufPos := vmBufPos + 2;
                    
                3: (* DINT — 4 bytes LE *)
                    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), vmRegistry[vmVarId].pAddress, 4);
                    vmBufPos := vmBufPos + 4;
                    
                4: (* UDINT — 4 bytes LE *)
                    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), vmRegistry[vmVarId].pAddress, 4);
                    vmBufPos := vmBufPos + 4;
                    
                5: (* REAL — 4 bytes LE (IEEE 754) *)
                    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), vmRegistry[vmVarId].pAddress, 4);
                    vmBufPos := vmBufPos + 4;
                    
                6: (* LREAL — 8 bytes LE *)
                    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), vmRegistry[vmVarId].pAddress, 8);
                    vmBufPos := vmBufPos + 8;
                    
                7: (* STRING — 1 byte length + chars *)
                    brsmemcpy(ADR(vmTempString), vmRegistry[vmVarId].pAddress, 81);
                    vmTempStrLen := UDINT_TO_USINT(brsstrlen(ADR(vmTempString)));
                    IF vmTempStrLen > 80 THEN
                        vmTempStrLen := 80;
                    END_IF;
                    vmUdpBuf[vmBufPos] := vmTempStrLen;
                    vmBufPos := vmBufPos + 1;
                    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), ADR(vmTempString), vmTempStrLen);
                    vmBufPos := vmBufPos + vmTempStrLen;
                    
                8: (* USINT — 1 byte *)
                    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), vmRegistry[vmVarId].pAddress, 1);
                    vmBufPos := vmBufPos + 1;
                    
                9: (* SINT — 1 byte *)
                    brsmemcpy(ADR(vmUdpBuf[vmBufPos]), vmRegistry[vmVarId].pAddress, 1);
                    vmBufPos := vmBufPos + 1;
                    
            END_CASE;
            
            vmPackedCount := vmPackedCount + 1;
        END_IF;
    END_FOR;
    
    (* Fill in the count field *)
    vmUdpBuf[vmCountPos] := UINT_TO_USINT(vmPackedCount MOD 256);
    vmUdpBuf[vmCountPos + 1] := UINT_TO_USINT(vmPackedCount / 256);
    
    (* ── Send UDP packet ── *)
    vmUdpSend.enable := TRUE;
    vmUdpSend.ident := vmUdpIdent;
    vmUdpSend.pHost := ADR(vmClientIpAddr);
    vmUdpSend.port := vmClientPort;
    vmUdpSend.pData := ADR(vmUdpBuf);
    vmUdpSend.datalen := vmBufPos;
    vmUdpSend.flags := 0;
    vmUdpSend();
    
    vmSeqNum := vmSeqNum + 1;
    
END_ACTION
