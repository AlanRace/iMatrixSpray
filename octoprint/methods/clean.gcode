; starting cleaning procedure
; go to wash position
M82
G90
G1 Z-35.0 F200
G1 X0.0 Y-110.0 Z-35.0 F200
G1 Z-50.0
M106
G1 V0 F200
G4 S1
; emptying syringe
G1 P0 F100
; rinsing valve  steps 5 
;80 microliter each step
;step 1
G1 V1.5 F200
G4 S1
G1 P4.8 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step2
G1 V1.5 F200
G4 S1
G1 P4.8 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 3
G1 V1.5 F200
G4 S1
G1 P4.8 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 4
G1 V1.5 F200
G4 S1
G1 P4.8 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 5
G1 V1.5 F200
G4 S1
G1 P4.8 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
; rinsing spray
G1 V1.5 F200
G4 S1
G1 P4 F200
G4 S1
G1 V2 F200
G4 S2
G1 V1 F200
G4 S1
G1 F0.1
G1 P0
M106 S0
; rinsing capillary
G1 V1.5 F200
G4 S1
G1 P3 F200
G1 V2 F200
G4 S2
G1 V1 F200
G4 S1
G1 F0.1
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
G1 Z-35.0 F200
G1 X0 Y0 Z-35 F200
G1 Z16.5 F200
; motors off
M18