; purge
G28XYZ
G28P
M82
; rinsing valve  steps 10 
;100 microliter each step
;step 1
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step2
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 3
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 4
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 5
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 6
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 7
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 8
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 9
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;step 10
G1 V1.5 F200
G4 S1
G1 P10.6 F200
G1 V2 F200
G4 S2
G1 V0 F200
G4 S1
G1 P0 F100
;syringe down
G1 V1 F200
G4 S1
G1 P50 F200
; motors off
M18