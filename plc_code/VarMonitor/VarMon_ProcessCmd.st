(********************************************************************
 * VarMon_ProcessCommand — Parse incoming TCP subscription command
 *
 * TCP Command format:
 *   [CMD:1 byte][COUNT:2 bytes LE][PAYLOAD: COUNT x 2 bytes LE]
 ********************************************************************)
ACTION VarMon_ProcessCommand:
    
    vmCmdByte := vmTcpRxBuf[0];
    vmCmdCount := USINT_TO_UINT(vmTcpRxBuf[1]) + USINT_TO_UINT(vmTcpRxBuf[2]) * 256;
    
    CASE vmCmdByte OF
        
        (* 0x01: SET — replace entire subscription list *)
        1:
            vmSubCount := 0;
            FOR vmIdx := 0 TO vmCmdCount - 1 DO
                IF vmIdx < VM_MAX_SUBSCRIPTIONS THEN
                    vmSubscription[vmIdx] := USINT_TO_UINT(vmTcpRxBuf[3 + vmIdx * 2]) + 
                                             USINT_TO_UINT(vmTcpRxBuf[4 + vmIdx * 2]) * 256;
                    vmSubCount := vmSubCount + 1;
                END_IF;
            END_FOR;
            
            (* Send ACK back *)
            vmTcpTxBuf[0] := 16#01;  (* ACK *)
            vmTcpTxBuf[1] := UINT_TO_USINT(vmSubCount MOD 256);
            vmTcpTxBuf[2] := UINT_TO_USINT(vmSubCount / 256);
            vmTcpSend.enable := TRUE;
            vmTcpSend.ident := vmTcpClientIdent;
            vmTcpSend.pData := ADR(vmTcpTxBuf);
            vmTcpSend.datalen := 3;
            vmTcpSend.flags := 0;
            vmTcpSend();
            
        (* 0x02: ADD — add variables to subscription *)
        2:
            FOR vmIdx := 0 TO vmCmdCount - 1 DO
                IF vmSubCount < VM_MAX_SUBSCRIPTIONS THEN
                    vmSubscription[vmSubCount] := 
                        USINT_TO_UINT(vmTcpRxBuf[3 + vmIdx * 2]) + 
                        USINT_TO_UINT(vmTcpRxBuf[4 + vmIdx * 2]) * 256;
                    vmSubCount := vmSubCount + 1;
                END_IF;
            END_FOR;
            
        (* 0x03: REMOVE — remove variables from subscription *)
        3:
            (* Simple: mark and compact *)
            FOR vmIdx := 0 TO vmCmdCount - 1 DO
                vmVarId := USINT_TO_UINT(vmTcpRxBuf[3 + vmIdx * 2]) + 
                           USINT_TO_UINT(vmTcpRxBuf[4 + vmIdx * 2]) * 256;
                FOR vmIdx2 := 0 TO vmSubCount - 1 DO
                    IF vmSubscription[vmIdx2] = vmVarId THEN
                        (* Shift rest down *)
                        FOR vmIdx3 := vmIdx2 TO vmSubCount - 2 DO
                            vmSubscription[vmIdx3] := vmSubscription[vmIdx3 + 1];
                        END_FOR;
                        vmSubCount := vmSubCount - 1;
                    END_IF;
                END_FOR;
            END_FOR;
            
        (* 0x04: SET INTERVAL — set send rate *)
        4:
            vmSendIntervalMs := vmCmdCount;  (* Reuse count field as interval *)
            
        (* 0xFF: HEARTBEAT / STATUS *)
        255:
            vmTcpTxBuf[0] := 16#FF;
            vmTcpTxBuf[1] := UINT_TO_USINT(vmSubCount MOD 256);
            vmTcpTxBuf[2] := UINT_TO_USINT(vmSubCount / 256);
            vmTcpTxBuf[3] := UINT_TO_USINT(vmRegCount MOD 256);
            vmTcpTxBuf[4] := UINT_TO_USINT(vmRegCount / 256);
            vmTcpSend.enable := TRUE;
            vmTcpSend.ident := vmTcpClientIdent;
            vmTcpSend.pData := ADR(vmTcpTxBuf);
            vmTcpSend.datalen := 5;
            vmTcpSend.flags := 0;
            vmTcpSend();
            
    END_CASE;
    
END_ACTION
