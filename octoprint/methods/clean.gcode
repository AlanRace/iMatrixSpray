; starting cleaning procedure
; go to wash position
G1 X0.0 Y-110.0 Z-30.0 F200
G1 Z-50.0
M106
G1 V0 F200
G4 S1
; emptying syringe
G1 P0 F200
G1 V2 F200
G4 S1
G1 P10 F200
G1 V0 F200
G4 S1
; rinsing valve
G1 P0 F200
G1 V2 F200
G4 S1
G1 P4 F200
G1 V1 F200
G4 S1
; rinsing spray
G1 F0.3
G1 P0
M106 S0
G1 V2 F200
G4 S1
G1 P3 F200
G1 V1 F200
G4 S1
; rinsing capillary
G1 F0.2
G1 P0
G1 P1
; drying
M106
G1 P0
G4 S2
G4 S2
G4 S2
G4 S2
M106 S0
; parking spray
G1 X0 Y0 Z0 F200
; motors off
M18